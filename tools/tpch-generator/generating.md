# Process used to generate the tpc-h data

Using the tpchgen-cli since it does not require to have the entire table in memory.
Can be found: https://github.com/alamb/tpchgen-rs/tree/main

With rustup / cargo can be installed using (may need to make sure cargo is up to date for it to compile)
```
cargo install tpchgen-cli
```

## Scaling considerations

The tables `region` and `nation` are always a single table so can generate those with only 1 partion 
The tables that scale with the scale factor:
- part: scale_factor * 200'000 lines are populated
- supplier: scale_factor * 10'000 lines are populated
- customer: scale_factor * 150'000 lines populated
- orders: scale_factor * 1'500'000 lines populated
- partsupp: depending on other tables, ~ scale_factor * 800'000 lines populated
- lineitems: depending on other tables, ~ scale_factor * 6'000'000 lines populated

Accordingly supplier table should always be fine as one table for all scale factors.
lineitem, orders and partsupp should be split into different tables for scale factor 10, 100 and 1000
(2, 16 and 192 partitions should be enouth for parquet)

## Generation commands
```
export SCALE_FACTOR=1
export PARTS=1
export OUT_DIR="sf-$SCALE_FACTOR"
tpchgen-cli --format=parquet --tables region,nation,supplier,part,customer -s $SCALE_FACTOR --output-dir $OUT_DIR 
tpchgen-cli --format=parquet --tables lineitem,partsupp,orders -s $SCALE_FACTOR --output-dir $OUT_DIR --parts $PARTS
```