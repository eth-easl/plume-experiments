# Local Data Client

## Setup

```
# fetch the tpch data from s3
<plume-experiments-repo>/experiments/setup/bash/fetch_s3_data.sh

# install go
<plume-experiments-repo>/experiments/setup/bash/install_go.sh
```

## Execute

```
cd data-client
# assuming the data is stored under `$HOME/data`
go run main.go --config=config_default.json --storagePath=$HOME/data
```
