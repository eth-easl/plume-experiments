#!/bin/bash
clear
cd data-client
go run main.go --config=config_default.json --storagePath=$HOME/data
