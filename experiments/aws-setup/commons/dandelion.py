import json

# constant over different setup scripts
PATH_CFG_MULTINODE = "~/cfg_multinode.json"

def gen_cfg_single(preload_path, system_cores=6):
    return f"""{{
    "min_sys_cores": {system_cores},
    "bin_preload_path": "{preload_path}",
    "virtual_max_ram_multiplier": 4
}}
"""

def gen_cfg_master(preload_cfg_path, node_id, system_cores=6):
    return f"""{{
    "min_sys_cores": {system_cores},
    "bin_preload_path": "{preload_cfg_path}",
    "virtual_max_ram_multiplier": 4,
    
    "node_id": {node_id},
    "multinode_config": "{PATH_CFG_MULTINODE}",
    
    "total_cores": {system_cores},
    "test_mode": "NoCompute"
}}
"""

def gen_cfg_worker(preload_path, node_id, system_cores=6):
    return f"""{{
    "min_sys_cores": {system_cores},
    "bin_preload_path": "{preload_path}",
    "virtual_max_ram_multiplier": 4,

    "node_id": {node_id},
    "multinode_config": "{PATH_CFG_MULTINODE}"
}}
"""

def gen_cfg_multinode(target_ips):
    if not target_ips or len(target_ips) == 0:
        print("No nodes found to generate configuration.")
        exit(1)

    config = {
        "queue_server": {
            "node_id": 0,
            "url": f"{target_ips[0]}:8081"
        },
        "data_servers": []
    }
    
    for i, ip in enumerate(target_ips):
        config["data_servers"].append({
            "node_id": i,
            "url": f"{ip}:10000"
        })
        
    return json.dumps(config, indent=2)

def gen_start_script(cfg_paths):
    s = 'readonly features="kvm,timestamp,log_function_stdio,vendored-ssl,data_locality"\n'
    s += 'readonly log="debug,machine_interface=info"\n'
    for i, p in enumerate(cfg_paths):
        if i > 0: s += '#'
        s += f'readonly config="{p}"\n'

    s += '\nclear\n'
    s += 'cd ~/dandelion\n'
    s += 'rm /dev/shm/*\n\n'

    s += 'RUST_LOG="${log}" cargo run --bin dandelion_server -F "${features}" --release -- --config-path "${config}"\n'
    return s

