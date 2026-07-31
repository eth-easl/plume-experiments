#!/bin/bash

export SCALE_FACTOR=1000
export BUCKET="gs://tpc-h-bucket/sf-$SCALE_FACTOR"

bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/customer.parquet > sf-$SCALE_FACTOR-customer
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-customer serverless-scheduling:sf_$SCALE_FACTOR.customer
echo "customer table added"
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/nation.parquet > sf-$SCALE_FACTOR-nation
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-nation serverless-scheduling:sf_$SCALE_FACTOR.nation
echo "nation table added"
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/part.parquet > sf-$SCALE_FACTOR-part
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-part serverless-scheduling:sf_$SCALE_FACTOR.part
echo "part table added"
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/region.parquet > sf-$SCALE_FACTOR-region
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-region serverless-scheduling:sf_$SCALE_FACTOR.region
echo "region table added"
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/supplier.parquet > sf-$SCALE_FACTOR-supplier
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-supplier serverless-scheduling:sf_$SCALE_FACTOR.supplier
echo "supplier table added"
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/lineitem/lineitem.*.parquet > sf-$SCALE_FACTOR-lineitem
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-lineitem serverless-scheduling:sf_$SCALE_FACTOR.lineitem
echo "lineitem table added"
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/orders/orders.*.parquet > sf-$SCALE_FACTOR-orders
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-orders serverless-scheduling:sf_$SCALE_FACTOR.orders
echo "order table added"
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/partsupp/partsupp.*.parquet > sf-$SCALE_FACTOR-partsupp
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-partsupp serverless-scheduling:sf_$SCALE_FACTOR.partsupp
echo "partsupp table added"