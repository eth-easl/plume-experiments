# Local Data Client

## Setup

Use `setup.sh` or the following commands:

```
# create the folder that should hold the data
mkdir -p ~/data/tpch10
cd ~/data/tpch10

# the default downloads the scale factor 10 data -> change to 
~/plume-experiments/experiments/setup/bash/fetch_s3_data.sh

# download go
wget --continue --quiet https://go.dev/dl/go1.25.4.linux-amd64.tar.gz -O go.tar.gz
mkdir ~/.go
tar -xzf go.tar.gz -C ~/.go --strip-components=1
echo "export PATH=\"\$HOME/.go/bin:\$PATH\"" >> ~/.bashrc
source ~/.bashrc
rm go.tar.gz
```

## Execute

```
cd data-client
# assuming the data is stored under `$HOME/data`
go run main.go --config=config_default.json --storagePath=$HOME/data
```
