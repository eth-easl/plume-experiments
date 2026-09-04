import re
import sys
import termios
import tty
from pathlib import Path
from commons.colors import print_info
from commons.util import load_setup_config, run_setup_step

SETUP_DIR = Path(__file__).resolve().parent
SETUP_CONFIG_PATH = f"{SETUP_DIR}/setup_config.json"

def parse_cloudlab_addresses(input_data):
    lines = [line.strip() for line in input_data.strip().split("\n") if line.strip()]
    nodes = []
    for i in range(len(lines)):
        match = re.search(r"([a-zA-Z0-9_.-]+)@([a-zA-Z0-9_.-]+)", lines[i])
        if not match:
            continue

        user, public_ip = match.groups()
        internal_ip = f"10.0.1.{i+1}"
        nodes.append({
            "node_index": i,
            "user": user,
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
    config = load_setup_config(SETUP_CONFIG_PATH)

    # Get input
    print_info("Paste your node data below then press Enter followed by 'Ctrl + D' to finish.\n")
    print("-" * 50)
    raw_input_data = sys.stdin.read()
    print("-" * 50)
    print()
    
    parsed_nodes = parse_cloudlab_addresses(raw_input_data)

    print_info("Parsed nodes:")
    print(f"Client node (Node {parsed_nodes[0]['node_index']})")
    print(f"  User:        {parsed_nodes[0]['user']}")
    print(f"  Public IP:   {parsed_nodes[0]['public_ip']}")
    print(f"  Internal IP: {parsed_nodes[0]['internal_ip']}")
    print("Worker nodes:")
    for node in parsed_nodes[1:]:
        print(f"  Node {node['node_index']}:")
        print(f"    User:        {node['user']}")
        print(f"    Public IP:   {node['public_ip']}")
        print(f"    Internal IP: {node['internal_ip']}")
    print("")

    print_info("Confirm setup...")
    user_confirm()

    print_info("Running remote setup scripts...")
    targets = [f"{n['user']}@{n['public_ip']}" for n in parsed_nodes]

    setup_dandelion_cmd = [sys.executable, f"{SETUP_DIR}/remote_setup_dandelion.py"] + targets
    if "sshKey" in config and len(config["sshKey"]) > 0:
        setup_dandelion_cmd += ["-t", config["sshKey"]]
    setup_dandelion_cmd += ["--internal_ips"] + [n['internal_ip'] for n in parsed_nodes]
    if config['cloneWithHTTP']: setup_dandelion_cmd.append("--clone-with-http")
    if "dandelionBranch" in config and len(config["dandelionBranch"]) > 0:
        setup_dandelion_cmd += ["-b", config['dandelionBranch']]
    run_setup_step("Dandelion", setup_dandelion_cmd, config.get('gitConfig', {}), cwd=SETUP_DIR)

    setup_plume_cmd = [sys.executable, f"{SETUP_DIR}/remote_setup_plume.py"]
    if "sshKey" in config and len(config["sshKey"]) > 0:
        setup_plume_cmd += ["-t", config["sshKey"]]
    if config['plumeInstallFunctions']: setup_plume_cmd.append("--install-functions")
    if config['plumeInstallClient']: setup_plume_cmd.append("--install-client")
    if config['plumeBuildFunctions']: setup_plume_cmd.append("--build-functions")
    if config['plumeBuildClient']: setup_plume_cmd.append("--build-client")
    if config['cloneWithHTTP']: setup_plume_cmd.append("--clone-with-http")
    setup_plume_cmd += targets
    if "plumeBranch" in config and len(config["plumeBranch"]) > 0:
        setup_plume_cmd += ["-b", config['plumeBranch']]
    run_setup_step("Plume", setup_plume_cmd, config.get('gitConfig', {}), cwd=SETUP_DIR)

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
    has_ssh_key = "sshKey" in config and len(config["sshKey"]) > 0

    print_info("SSH commands:")
    ssh_key = f" -i {config['sshKey']}" if has_ssh_key else ""
    for node in parsed_nodes:
        print(f"  Node {node['node_index']}: ssh{ssh_key} {node['user']}@{node['public_ip']}")
    print()
    print_info("Start workers:")
    start_workers_cmd = f"python {SETUP_DIR}/remote_start_plume_workers.py"
    if has_ssh_key:
        start_workers_cmd += f" -t {config['sshKey']}"
    for node in parsed_nodes:
        start_workers_cmd += f" {node['user']}@{node['public_ip']}"
    print(f"  {start_workers_cmd}")
    print()
