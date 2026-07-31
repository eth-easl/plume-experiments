package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"github.com/sirupsen/logrus"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"system-runner/util"
	"time"
)

var (
	configPath  = flag.String("config", "config_default.json", "Path to the configuration file")
	storagePath = flag.String("storagePath", "storage", "Path where the data is stored")
)

type clientConfig struct {
	Host      string `json:"host"`
	Port      string `json:"port"`
	Verbosity string `json:"verbosity"`
	TracePath string `json:"tracePath"`
}

func getLocalIP() string {
	cmd := exec.Command("bash", "-c", "/usr/bin/netstat -ie | grep -B1 '10.0.1' | sed -n 2p | tr -s ' ' | cut -d ' ' -f 3")
	stdout, err := cmd.Output()

	if err != nil {
		logrus.Fatal(err)
	}

	ip := string(stdout)
	ip = ip[0 : len(ip)-1]

	return ip
}

func loadConfig(path *string) *clientConfig {
	jsonFile, err := os.ReadFile(*path)
	if err != nil {
		logrus.Fatalf("Failed to read client config file: %v", err)
	}

	var config clientConfig
	err = json.Unmarshal(jsonFile, &config)
	if err != nil {
		logrus.Fatalf("Failed to unmarshal client config file: %v", err)
	}

	// resolve dynamic host
	if config.Host == "dynamic" {
		config.Host = getLocalIP()
	}

	return &config
}

type tracer struct {
	outFile   *os.File
	startTime time.Time
}

func newTracer(outPath string) *tracer {
	t := &tracer{}

	var err error
	directory := filepath.Dir(outPath)
	if _, err = os.Stat(directory); os.IsNotExist(err) {
		if err = os.Mkdir(directory, 0777); err != nil {
			logrus.Fatalf("Got error writing traces: %v", err)
		}
	}
	_ = os.Remove(outPath)
	t.outFile, err = os.Create(outPath)
	if err != nil {
		logrus.Fatalf("Got error writing traces: %v", err)
	}

	_, err = t.outFile.WriteString("method,resource,start_offset_ms,duration_ms\n")
	if err != nil {
		logrus.Fatalf("Got error writing traces: %v", err)
	}

	t.startTime = time.Now()
	return t
}

func (t *tracer) add(method string, res string, tsStart time.Time, tsEnd time.Time) {
	_, err := t.outFile.WriteString(fmt.Sprintf("%s,%s,%d,%d\n", method, res, tsStart.Sub(t.startTime).Microseconds(), tsEnd.Sub(tsStart).Microseconds()))
	if err != nil {
		logrus.Fatalf("Got error writing traces: %v", err)
	}
}

func (t *tracer) Close() {
	if t.outFile != nil {
		err := t.outFile.Close()
		if err != nil {
			logrus.Errorf("Failed to close the trace file!")
		}
	}
}

func storeData(filePath string, data []byte) error {
	osPath := path.Join(*storagePath, filePath)
	err := os.MkdirAll(path.Dir(osPath), os.ModePerm)
	if err != nil {
		logrus.Errorf("Failed to create directories for path '%s': %v", osPath, err)
	}

	fileInfo, err := os.Stat(osPath)
	if err != nil {
		if !os.IsNotExist(err) {
			logrus.Errorf("StoreData failed: %v", err)
			return err
		}
	} else {
		if fileInfo.IsDir() {
			logrus.Errorf("StoreData failed - target path is a directory")
			return fmt.Errorf("target path is a directory")
		} else {
			logrus.Warnf("Overwriting existing file '%s'", filePath)
		}
	}

	err = os.WriteFile(osPath, data, os.ModePerm)
	if err != nil {
		logrus.Errorf("Failed to write data to '%s': %v", osPath, err)
		return err
	}

	logrus.Debugf("Wrote data to '%s' (size=%d)", osPath, len(data))
	return nil
}

// fetchData reads a file from the storage path. When rng is nil the whole file
// is returned; otherwise the resolved (already clamped to the file size) byte
// range is returned.
func fetchData(filePath string, rng *httpRange) ([]byte, error) {
	osPath := path.Join(*storagePath, filePath)

	if rng == nil {
		data, err := os.ReadFile(osPath)
		if err != nil {
			logrus.Errorf("Failed to read data from '%s': %v", osPath, err)
			return nil, err
		}

		logrus.Debugf("Fetched data from '%s' (size=%d)", osPath, len(data))
		return data, nil
	}

	f, err := os.Open(osPath)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	if _, err = f.Seek(rng.start, io.SeekStart); err != nil {
		return nil, err
	}

	buffer := make([]byte, rng.length)
	// The range is clamped to the file size before we get here, so a short read
	// only happens if the file shrank concurrently; tolerate EOF in that case.
	n, err := io.ReadFull(f, buffer)
	if err != nil && err != io.EOF && err != io.ErrUnexpectedEOF {
		return nil, err
	}

	logrus.Debugf("Fetched data from '%s' (offset=%d size=%d)", osPath, rng.start, n)
	return buffer[:n], nil
}

// httpRange is a byte range resolved against the actual file size: it always
// describes bytes [start, start+length) that exist within the file.
type httpRange struct {
	start  int64
	length int64
}

// errUnsatisfiable is returned by parseRange for a syntactically valid Range
// that cannot be satisfied for the given file (HTTP 416).
var errUnsatisfiable = errors.New("requested range not satisfiable")

// parseRange parses an HTTP Range header (RFC 7233) against a file of size
// total, following S3's semantics:
//   - No Range header, or a syntactically invalid one, returns (nil, nil): the
//     whole file should be served (S3 ignores ranges it cannot parse).
//   - A valid but unsatisfiable range (e.g. start beyond EOF, or a suffix of a
//     zero-length file) returns errUnsatisfiable.
//   - Otherwise the range is clamped to the file size and returned. A suffix
//     range larger than the file ("bytes=-N" with N >= total) yields the whole
//     file.
//
// Only a single byte range is supported; multi-range requests are ignored and
// the whole file is served, as S3 does.
func parseRange(header string, total int64) (*httpRange, error) {
	const prefix = "bytes="
	if !strings.HasPrefix(header, prefix) {
		return nil, nil
	}

	spec := strings.TrimSpace(strings.TrimPrefix(header, prefix))
	if spec == "" || strings.Contains(spec, ",") {
		return nil, nil
	}

	dash := strings.IndexByte(spec, '-')
	if dash < 0 {
		return nil, nil
	}
	startStr := strings.TrimSpace(spec[:dash])
	endStr := strings.TrimSpace(spec[dash+1:])

	// Suffix range: "bytes=-N" -> the last N bytes of the file.
	if startStr == "" {
		n, err := strconv.ParseInt(endStr, 10, 64)
		if err != nil || n < 0 {
			return nil, nil
		}
		if n == 0 || total == 0 {
			return nil, errUnsatisfiable
		}
		if n >= total {
			return &httpRange{start: 0, length: total}, nil
		}
		return &httpRange{start: total - n, length: n}, nil
	}

	start, err := strconv.ParseInt(startStr, 10, 64)
	if err != nil || start < 0 {
		return nil, nil
	}
	if start >= total {
		return nil, errUnsatisfiable
	}

	end := total - 1
	if endStr != "" {
		end, err = strconv.ParseInt(endStr, 10, 64)
		if err != nil || end < start {
			return nil, nil
		}
		if end >= total {
			end = total - 1
		}
	}
	return &httpRange{start: start, length: end - start + 1}, nil
}

func getRequestHandler(t *tracer) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		logrus.Tracef("Handling request from %s for %s (%s) (%v)", r.RemoteAddr, r.URL, r.Method, r.Header)
		timeStart := time.Now()
		switch r.Method {
		case "HEAD":
			filePath := strings.TrimPrefix(r.URL.Path, "/")
			osPath := path.Join(*storagePath, filePath)
			fileInfo, err := os.Stat(osPath)
			if err != nil {
				w.WriteHeader(http.StatusNotFound)
				return
			}
			if fileInfo.IsDir() {
				w.WriteHeader(http.StatusForbidden)
				return
			}
			w.Header().Set("Accept-Ranges", "bytes")
			w.Header().Set("Content-Length", fmt.Sprintf("%d", fileInfo.Size()))
			w.WriteHeader(http.StatusOK)

		case "GET":
			filePath := strings.TrimPrefix(r.URL.Path, "/")
			osPath := path.Join(*storagePath, filePath)
			fileInfo, err := os.Stat(osPath)
			if err != nil {
				if os.IsNotExist(err) {
					http.Error(w, err.Error(), http.StatusNotFound)
				} else {
					logrus.Errorf("GET request for '%s' failed: %v", filePath, err)
					http.Error(w, err.Error(), http.StatusInternalServerError)
				}
				return
			}
			if fileInfo.IsDir() {
				http.Error(w, "target path is a directory", http.StatusForbidden)
				return
			}
			total := fileInfo.Size()

			w.Header().Set("Accept-Ranges", "bytes")

			rng, err := parseRange(r.Header.Get("Range"), total)
			if err != nil {
				// The only error parseRange returns is an unsatisfiable range.
				w.Header().Set("Content-Range", fmt.Sprintf("bytes */%d", total))
				http.Error(w, err.Error(), http.StatusRequestedRangeNotSatisfiable)
				return
			}

			data, err := fetchData(filePath, rng)
			if err != nil {
				logrus.Errorf("GET request for '%s' failed: %v", filePath, err)
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}

			w.Header().Set("Content-Length", fmt.Sprintf("%d", len(data)))
			if rng != nil {
				w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", rng.start, rng.start+rng.length-1, total))
				w.WriteHeader(http.StatusPartialContent)
			}
			_, err = w.Write(data)
			if err != nil {
				logrus.Errorf("Failed to write data to http response: %v", err)
				return
			}

		case "POST":
			filePath := strings.TrimPrefix(r.URL.Path, "/")
			data, err := io.ReadAll(r.Body)
			if err != nil {
				logrus.Errorf("Failed to read PUT request body for '%s': %v", filePath, err)
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}

			err = storeData(filePath, data)
			if err != nil {
				logrus.Errorf("Failed to store data for '%s': %v", filePath, err)
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}

			w.WriteHeader(http.StatusOK)
		}
		timeEnd := time.Now()
		if t != nil {
			t.add(r.Method, r.URL.Path, timeStart, timeEnd)
		}
	}

}

func main() {
	flag.Parse()

	cfg := loadConfig(configPath)
	util.SetupLogger(cfg.Verbosity)
	logrus.Infof("Using storage path '%s'", *storagePath)

	serverAddress := net.JoinHostPort(cfg.Host, cfg.Port)
	logrus.Infof("Creating a server at %s", serverAddress)

	var t *tracer
	if len(cfg.TracePath) > 0 {
		logrus.Infof("Using tracer with output: %s", cfg.TracePath)
		t = newTracer(cfg.TracePath)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", getRequestHandler(t))

	err := http.ListenAndServe(serverAddress, mux)
	if err != nil {
		if errors.Is(err, http.ErrServerClosed) {
			logrus.Infof("Server closed\n")
		} else if err != nil {
			logrus.Fatalf("Failed to start server: %s\n", err)
		}
	}
}
