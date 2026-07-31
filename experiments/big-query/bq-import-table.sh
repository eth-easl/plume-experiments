#!/bin/bash

export SCALE_FACTOR=1000
export BUCKET="gs://tpc-h-bucket/sf-$SCALE_FACTOR"

bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.customer $BUCKET/customer.parquet
bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.nation $BUCKET/nation.parquet
bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.part $BUCKET/part.parquet
bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.region $BUCKET/region.parquet
bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.supplier $BUCKET/supplier.parquet
bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.lineitem $BUCKET/lineitem/lineitem.*.parquet
bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.orders $BUCKET/orders/orders.*.parquet
bq load --source_format=PARQUET --autodetect=true serverless-scheduling:sf_"$SCALE_FACTOR"_loaded.partsupp $BUCKET/partsupp/partsupp.*.parquet