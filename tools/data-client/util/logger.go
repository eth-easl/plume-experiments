package util

import "github.com/sirupsen/logrus"

func SetupLogger(level string) {
	switch level {
	case "trace":
		logrus.SetLevel(logrus.TraceLevel)
	case "debug":
		logrus.SetLevel(logrus.DebugLevel)
	case "info":
		logrus.SetLevel(logrus.InfoLevel)
	case "warn":
		logrus.SetLevel(logrus.WarnLevel)
	case "error":
		logrus.SetLevel(logrus.ErrorLevel)
	case "fatal":
		logrus.SetLevel(logrus.FatalLevel)
	case "":
		logrus.SetLevel(logrus.InfoLevel) // default if unspecified
	default:
		logrus.Fatalf("Failed to resolve logging level!")
	}
}
