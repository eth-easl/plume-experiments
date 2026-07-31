#!/bin/bash

SCALE_FACTOR=1000
REPETITIONS=3

for ((REPETITION=1; REPETITION < REPETITIONS; REPETITION++)); do
for ((QUERY=1; QUERY <= 22; QUERY++)); do
    echo "running query $QUERY in iteration $REPETITION"
    QUERY_STRING=$(sed "s/\`DATASET.\([a-z]*\)\`/\1/g" "../queries/q$QUERY.sql" | tr '\n' ' ' | tr -s ' ')
    # echo $QUERY_STRING
    QUERY_RESPONSE=$(aws athena start-query-execution \
        --query-string "$QUERY_STRING" \
        --query-execution-context Database=tpch_sf"$SCALE_FACTOR" \
        --result-configuration OutputLocation=s3://test-athena-bucket-t)
    QUERY_ID=$(echo "$QUERY_RESPONSE" | tr -d '\n' | tr -s ' ' | sed "s/{ \"\([A-Z|a-z]*\)\": \"\([a-z|0-9|-]*\)\"}/\2/g")
    echo query id: "$QUERY_ID"
    echo "$QUERY_ID" >> query_ids_sf"$SCALE_FACTOR".txt
    # QUERY_DATA=$(aws athena get-query-execution --query-execution-id "$QUERY_ID")
    # echo "performance: $QUERY_DATA"
    # echo "$QUERY_DATA," >> results_sf$SCALE_FACTOR.json
    sleep 1m
done
done