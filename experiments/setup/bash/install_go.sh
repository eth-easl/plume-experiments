#!/bin/bash
set -euo pipefail

readonly go_version="1.25.4"
readonly install_dir="$HOME/.go"
readonly path_export='export PATH="$HOME/.go/bin:$PATH"'

wget --continue --quiet "https://go.dev/dl/go${go_version}.linux-amd64.tar.gz" -O go.tar.gz
mkdir -p "$install_dir"
tar -xzf go.tar.gz -C "$install_dir" --strip-components=1
rm go.tar.gz

# only append the export once, re-running the script must not duplicate it
if ! grep -qxF "$path_export" ~/.bashrc 2> /dev/null; then
    echo "$path_export" >> ~/.bashrc
fi
