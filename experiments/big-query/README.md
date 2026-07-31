# Generating the results
To generate the results we first need the data available in datasets.
For generating the data see the tpch-generator instructions.

## Upload gcloud
Install gcloud CLI, then use it for upload (https://docs.cloud.google.com/storage/docs/uploading-objects#upload-object-cli)
```
gcloud storage cp --recursive $OUT_DIR gs://DESTINATION_BUCKET_NAME
```

## Create dataset with tables
Create the dataset in the web GUI.
After that we can add the tables stored in our bucket using the following commands or with the script bq-external-table-adding.sh.

Command example for adding 1 table
```
bq mkdef --source_format=PARQUET --autodetect=true gs://tpc-h-bucket/sf-1/part.parquet > sf-1-part
bq mk --table --external_table_definition=sf-1-part serverless-scheduling:sf_1.part
```

To create all tables for a given scale factor:
```
export SCALE_FACTOR=1
export BUCKET="gs://tpc-h-bucket/sf-$SCALE_FACTOR"

bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/customer.parquet > sf-$SCALE_FACTOR-customer
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-customer serverless-scheduling:sf_$SCALE_FACTOR.customer
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/nation.parquet > sf-$SCALE_FACTOR-nation
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-nation serverless-scheduling:sf_$SCALE_FACTOR.nation
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/part.parquet > sf-$SCALE_FACTOR-part
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-part serverless-scheduling:sf_$SCALE_FACTOR.part
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/region.parquet > sf-$SCALE_FACTOR-region
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-region serverless-scheduling:sf_$SCALE_FACTOR.region
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/supplier.parquet > sf-$SCALE_FACTOR-supplier
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-supplier serverless-scheduling:sf_$SCALE_FACTOR.supplier
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/lineitem/lineitem.*.parquet > sf-$SCALE_FACTOR-lineitem
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-lineitem serverless-scheduling:sf_$SCALE_FACTOR.lineitem
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/orders/orders.*.parquet > sf-$SCALE_FACTOR-orders
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-orders serverless-scheduling:sf_$SCALE_FACTOR.orders
bq mkdef --source_format=PARQUET --autodetect=true $BUCKET/partsupp/partsupp.*.parquet > sf-$SCALE_FACTOR-partsupp
bq mk --table --external_table_definition=sf-$SCALE_FACTOR-partsupp serverless-scheduling:sf_$SCALE_FACTOR.partsupp
```

## Running a query:
A query can be either run by using the web GUI or using the follwing commands, or the script bg-run-queries.sh
The scritps has a variable for the scale factor and number of repetitions as well as for the labels

Single query example command:
```
export SCALE_FACTOR=1
sed "s/DATASET/sf_$SCALE_FACTOR/g" q1.sql | bq query --use_legacy_sql=false --label scale:$SCALE_FACTOR --label location:storage
```
Queries can be cached and immediately returned