import re
import subprocess
import sys
import termios
import tty
from commons.colors import print_info

CONFIG = {
    "dandelion_branch": "debug/sharding_performance", # leave empty to use main branch
    # "plume_branch": "dev/benchmark-updates", # leave empty to use main branch
    # "plume-v2_branch": "dev/benchmark-fixes", # leave empty to use main branch
    "build_functions": False,
    "build_client": False,
    "install_functions": True,
    "install_client": True,
}

def parse_aws_addresses(input_data):
    # Split the input by lines and remove empty lines
    lines = [line.strip() for line in input_data.strip().split("\n") if line.strip()]
    
    nodes = []
    
    # Process lines in pairs (Step of 2: Public, then Internal)
    for i in range(0, len(lines), 2):
        public_line = lines[i]
        internal_line = lines[i+1] if (i + 1) < len(lines) else None
        
        public_match = re.search(r'ec2-(\d+)-(\d+)-(\d+)-(\d+)', public_line)
        public_ip = ".".join(public_match.groups()) if public_match else "Unknown"
        
        internal_ip = "Unknown"
        if internal_line:
            internal_match = re.search(r'ip-(\d+)-(\d+)-(\d+)-(\d+)', internal_line)
            if internal_match:
                internal_ip = ".".join(internal_match.groups())
        
        nodes.append({
            "node_index": (i // 2),
            "public_ip": public_ip,
            "internal_ip": internal_ip
        })
        
    return nodes

def user_confirm():
    print("Press [ENTER] to continue or [ESC] to abort...")

    # Save the original terminal settings
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        # Set the terminal to read single keypresses immediately
        tty.setraw(sys.stdin.fileno())
        while True:
            char = sys.stdin.read(1)
            
            if char == '\r' or char == '\n':  # Enter key
                # Restore settings before printing so text looks normal
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                break
            elif char == '\x1b':  # Esc key
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                sys.exit()
                
    finally:
        # Ensure terminal settings are restored even if something crashes
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        

if __name__ == "__main__":
    # Get input
    print_info("Paste your node data below then press Enter followed by 'Ctrl + D' to finish.\n")
    print("-" * 50)
    raw_input_data = sys.stdin.read()
    print("-" * 50)
    print()
    
    parsed_nodes = parse_aws_addresses(raw_input_data)

    print_info("Parsed nodes:")
    print(f"Client node (Node {parsed_nodes[0]['node_index']})")
    print(f"  Public IP:   {parsed_nodes[0]['public_ip']}")
    print(f"  Internal IP: {parsed_nodes[0]['internal_ip']}")
    print("Worker nodes:")
    for node in parsed_nodes[1:]:
        print(f"  Node {node['node_index']}:")
        print(f"    Public IP:   {node['public_ip']}")
        print(f"    Internal IP: {node['internal_ip']}")
    print("")

    print_info("Confirm setup...")
    user_confirm()

    print_info("Running remote setup scripts...")
    targets = [f"ubuntu@{n['public_ip']}" for n in parsed_nodes]

    setup_dandelion_cmd = [sys.executable, "remote_setup_dandelion.py", "--aws"] + targets
    setup_dandelion_cmd += ["--internal_ips"] + [n['internal_ip'] for n in parsed_nodes]
    if "dandelion_branch" in CONFIG:
        setup_dandelion_cmd += ["-b", CONFIG['dandelion_branch']]
    subprocess.run(setup_dandelion_cmd, check=True)

    # setup_plume_cmd = [sys.executable, "remote_setup_plume.py", "--aws", "--ops"] + targets
    # if "plume_branch" in CONFIG:
    #     setup_plume_cmd += ["-b", CONFIG['plume_branch']]
    # subprocess.run(setup_plume_cmd, check=True)

    setup_plume_v2_cmd = [sys.executable, "remote_setup_plume-v2.py", "--aws"]
    if CONFIG['install_functions']: setup_plume_v2_cmd.append("--install-functions")
    if CONFIG['install_client']: setup_plume_v2_cmd.append("--install-client")
    if CONFIG['build_functions']: setup_plume_v2_cmd.append("--build-functions")
    if CONFIG['build_client']: setup_plume_v2_cmd.append("--build-client")
    setup_plume_v2_cmd += targets
    if "plume-v2_branch" in CONFIG:
        setup_plume_v2_cmd += ["-b", CONFIG['plume-v2_branch']]
    subprocess.run(setup_plume_v2_cmd, check=True)

    print_info("Remote setups completed!\n")

    print_info("Parsed nodes:")
    print(f"Client node (Node {parsed_nodes[0]['node_index']})")
    print(f"  Public IP:   {parsed_nodes[0]['public_ip']}")
    print(f"  Internal IP: {parsed_nodes[0]['internal_ip']}")
    print("Worker nodes:")
    for node in parsed_nodes[1:]:
        print(f"  Node {node['node_index']}:")
        print(f"    Public IP:   {node['public_ip']}")
        print(f"    Internal IP: {node['internal_ip']}")
    print()
    print_info("SSH commands:")
    for node in parsed_nodes:
        print(f"  Node {node['node_index']}: ssh -i ~/.ssh/aws-ireland.pem ubuntu@{node['public_ip']}")
    print()
    print_info("Start workers:")
    start_workers_cmd = "python remote_start_plume_workers.py --aws"
    for node in parsed_nodes:
        start_workers_cmd += f" ubuntu@{node['public_ip']}"
    print(f"  {start_workers_cmd}")
    print()
