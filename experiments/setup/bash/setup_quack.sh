#!/bin/bash
set -euo pipefail

readonly venv_path="$HOME/.venv_quack"

sudo apt install -y python3 python3-pip python3-venv
python3 -m venv "${venv_path}"
source "${venv_path}/bin/activate"
pip install duckdb --upgrade --pre

echo "Use 'source /"${venv_path}/bin/activate/" to activate the quack python venv."
