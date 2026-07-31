#!/bin/bash
set -euo pipefail

readonly URL="https://tpc-h-sf-10.s3.eu-north-1.amazonaws.com"

declare -A TABLES=(
    ["customer"]=0
    ["lineitem"]=2
    ["nation"]=0
    ["orders"]=2
    ["part"]=0
    ["partsupp"]=2
    ["region"]=0
    ["supplier"]=0
)

# Loop through the keys (table names) of the associative array
for table in "${!TABLES[@]}"; do
    n=${TABLES[$table]}
    
    echo "Downloading ${table} into ${table}/..."
    mkdir -p "$table"

    if (( n == 0 )); then
        # single file
        curl -fsSL "${URL}/${table}/${table}.parquet" -o "${table}/${table}.parquet"
    elif (( n > 0 )); then
        # multiple files
        for (( i=1; i<=n; i++ )); do
            filename="${table}.${i}.parquet"
            curl -fsSL "${URL}/${table}/${filename}" -o "${table}/${filename}"
        done
    else
        echo "Warning: Invalid 'n' value ($n) for table ${table}. Skipping."
    fi
done

echo "All downloads completed successfully!"
