# Athena benchmarking
We are using Athena as a comparison, because it is advertised as the serverless SQL service over data in S3 buckets.
Redshift does have a "serverless" billing mode, but it seems like that is mostly capacity spilling for a data lake.
Built on presto (now trino)

## Setting up data in a bucket
Create the data with tpchgenerating.md instructions.
Then all single parquet files need to be put into their own folders, since athena only creates databases on folders.
Set up bucket from web interface
Then can use the aws cli to upload.
For uploading change to the directory containing the parquet files and execute
```
export SCALE_FACTOR=1
~/aws/aws-cli/v2/2.33.24/dist/aws s3 cp . s3://tpc-h-sf-$SCALE_FACTOR --recursive
```

## Setting up tables for athena
https://oneuptime.com/blog/post/2026-02-12-set-up-amazon-athena-for-querying-s3-data/view

The queries to create tables are in the athena-create.txt.
To use them make sure to replace the scale factor and the bucket location.
For each scale factor first need to create a database, which can be done running the with the following query in the web SQL (replacing DATABASENAME and DATASET, DATABASENAME may not contain any '-' ):
```
CREATE DATABASE <DATABASENAME>
    LOCATION 's3://<DATASET>';
```
Then generate the SQL to add the tables with
```
sed "s/DATASET/<bucket location>/g" "athena-create.txt" 
```

# Running queries: 
Queries can either be run from the web interface or using the aws-cli
Generate the queries from the file:
```
sed "s/\`DATASET.\([a-z]*\)\`/\1/g" ../queries/q1.sql | tr '\n' ' ' | tr -s ' '
```

```
aws athena start-query-execution --query-string "SELECT
  l_returnflag,
  l_linestatus,
  sum(l_quantity) AS sum_qty,
  sum(l_extendedprice) AS sum_base_price,
  sum(l_extendedprice * (1 - l_discount)) AS sum_disc_price,
  sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge,
  avg(l_quantity) AS avg_qty,
  avg(l_extendedprice) AS avg_price,
  avg(l_discount) AS avg_disc,
  count(*) AS count_order
FROM
  lineitem
WHERE
  l_shipdate <= date '1998-12-01' - interval '120' day" --query-execution-context Database=tpch-sf1 --result-configuration OutputLocation=s3://test-athena-bucket-t 
```
Which returns a query execution id as a json object:
```
{
    "QueryExecutionId": "39878b4b-1f69-4273-8ee1-86945816c55e"
}
```
And details on the query can be fetched with 
```
aws athena get-query-execution --query-execution-id <query-id>
```