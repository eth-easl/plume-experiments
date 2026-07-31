readonly features="kvm,reqwest_io,timestamp,log_function_stdio,vendored-ssl"
# readonly features="kvm,reqwest_io,timestamp,log_function_stdio,vendored-ssl,data_locallity"
# readonly features="kvm,reqwest_io,log_function_stdio,vendored-ssl"

readonly log="debug"
# readonly log="trace"
# readonly log="debug,multinode=trace"
# readonly log="debug,machine_interface::interface=trace"

# readonly config="$HOME/plume/dandelion/config_d430.json"
# readonly config="$HOME/plume/dandelion/config_aws_single.json"
# readonly config="$HOME/plume/dandelion/config_aws_multi_master.json"
# readonly config="$HOME/plume/dandelion/config_aws_multi_master_nowork.json"
readonly config="$HOME/plume/dandelion/config_aws_multi_worker.json"


clear
cd ~/dandelion
rm /dev/shm/*

RUST_LOG="${log}" cargo run --bin dandelion_server -F "${features}" --release -- --config-path "${config}"
