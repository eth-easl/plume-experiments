#!/bin/bash
set -euo pipefail

install_dir="$HOME/.local"

# make sure installation folders exist and are in the PATH
if [ ! -d "$install_dir/bin" ]; then
    echo "export PATH=\"$install_dir/bin:\$PATH\"" >> $HOME/.bashrc
    source $HOME/.bashrc
fi
mkdir -p "$install_dir/bin" "$install_dir/include"

# protoc
PROTOC_ZIP="protoc-28.0-linux-x86_64.zip"
curl -OL "https://github.com/protocolbuffers/protobuf/releases/download/v28.0/$PROTOC_ZIP"
unzip -o "$PROTOC_ZIP" -d "$install_dir"
rm -f "$PROTOC_ZIP"
