#!/bin/bash

SCALE_FACTOR=1000

if [ $# -eq 0 ]; then
    echo "no file supplied"
    exit
fi

if [ -z "$1" ]; then
    echo "empty filename"
    exit
fi

while IFS="" read -r ID || [ -n "$ID" ]; do
    if [ -z "$ID" ]; then
        continue
    fi
    echo $ID
    QUERY_DATA=$(aws athena get-query-runtime-statistics --query-execution-id "$ID")
    # echo "performance: $QUERY_DATA"
    echo "$QUERY_DATA," >> statistics_sf$SCALE_FACTOR.json
done < "$1"

