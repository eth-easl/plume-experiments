#!/bin/bash

readonly data_path="$HOME/data/tpch10"
readonly repo_path="$HOME/plume-experiments"

# create the folder that should hold the data
mkdir -p "$data_path"
cd "$data_path"

# the default downloads the scale factor 10 data -> change to 
"$repo_path/experiments/setup/bash/fetch_s3_data.sh"

# download go
wget --continue --quiet https://go.dev/dl/go1.25.4.linux-amd64.tar.gz -O go.tar.gz
mkdir ~/.go
tar -xzf go.tar.gz -C ~/.go --strip-components=1
echo "export PATH=\"\$HOME/.go/bin:\$PATH\"" >> ~/.bashrc
source ~/.bashrc
rm go.tar.gz
