#!/bin/bash
set -euo pipefail

readonly base_dir="$HOME/data"
readonly download_parallelism=8

url() {
    local sf=$1
    echo "https://tpc-h-sf-${sf}-ireland.s3.eu-west-1.amazonaws.com"
}

download() {
    local target=$1
    local base_url=$2
    shift 2
    local pairs=("$@")

    echo "Fetching data from '$base_url' to '$target'..."
    mkdir -p "$target"
    (
        cd "$target"

        local -a urls=()
        for pair in "${pairs[@]}"; do
            local table="${pair%%=*}"
            local n="${pair#*=}"
            
            echo "Downloading ${table} into ${table}/..."
            mkdir -p "$table"

            if ! [[ "$n" =~ ^[0-9]+$ ]]; then
                echo "Warning: Invalid 'n' value ($n) for table ${table}. Skipping." >&2
                continue
            fi

            if (( n == 0 )); then
                # single file
                urls+=("${base_url}/${table}/${table}.parquet" "-o" "${table}/${table}.parquet")
            else
                # multiple files
                for (( i=1; i<=n; i++ )); do
                    local filename="${table}.${i}.parquet"
                    urls+=("${base_url}/${table}/${filename}" "-o" "${table}/${filename}")
                done
            fi
        done

        if (( ${#urls[@]} > 0 )); then
            curl -fsSL --retry 3 --retry-connrefused --parallel --parallel-max "$download_parallelism" "${urls[@]}"
        fi
    )

    echo "'$target' downloads completed successfully!"
}

# scale factor 1
download "${base_dir}/tpch1" "$(url "1")" \
    customer=0 lineitem=1 nation=0 orders=1 part=0 partsupp=1 region=0 supplier=0

# scale factor 10
download "${base_dir}/tpch10" "$(url "10")" \
    customer=0 lineitem=2 nation=0 orders=2 part=0 partsupp=2 region=0 supplier=0

echo "All downloads completed successfully!"
