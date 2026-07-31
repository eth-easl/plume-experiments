#!/bin/bash

# Run all queries on the scale factor 10 times
export SCALE_FACTOR=1000
export REPETITIONS=10
export LOCATION=storage
for ((REPETITION=0; REPETITION < REPETITIONS; REPETITION++)); do
for ((QUERY=1; QUERY <= 22; QUERY++)); do
    echo "running query $QUERY in iteration $REPETITION"
    # sed "s/DATASET/sf_$SCALE_FACTOR/g" "q$QUERY.sql" | bq query --use_legacy_sql=false --label test:true 
    sed "s/DATASET/sf_"$SCALE_FACTOR"/g" "../queries/q$QUERY.sql" | bq query \
    --nouse_cache \
    --use_legacy_sql=false \
    --label scale:"$SCALE_FACTOR" \
    --label location:"$STORAGE" \
    --label query:"$QUERY"
done
done