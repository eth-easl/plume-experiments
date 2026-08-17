import argparse
from commons.util import get_remotes, common_remote_setup
from commons.dandelion import gen_cfg_multinode, PATH_CFG_MULTINODE

# configuration
RPATH_DANDELION = "~/dandelion"
LPATH_START_SCRIPT    = "bash/dandelion/start_dandelion.sh"
RPATH_START_SCRIPT   = "~/start_dandelion.sh"

# basic setup
parser = argparse.ArgumentParser(description="Setup plume on remote targets.")
parser.add_argument("targets", nargs='+', type=str)
parser.add_argument("-t", "--token", type=str)
parser.add_argument("-b", "--branch", type=str)
parser.add_argument("--aws", action="store_true")
parser.add_argument("--internal_ips", nargs='+', type=str)
args = parser.parse_args()

has_internal_ips = False
if args.internal_ips is not None and len(args.internal_ips) > 0:
    if len(args.internal_ips) != len(args.targets):
        print("internal ips length does not match length of targets")
        exit(1)
    print("Using internal ips:")
    for i in range(len(args.targets)):
        print(f"{args.targets[i]} <-> {args.internal_ips[i]}")
    has_internal_ips = True

if args.token: 
    remotes = get_remotes(ssh_key_path=args.token, targets=args.targets)
elif args.aws: 
    remotes = get_remotes(ssh_key_path="~/.ssh/aws-ireland.pem", targets=args.targets)
else: 
    remotes = get_remotes(targets=args.targets)
common_remote_setup(remotes)


# setup dandelion
remotes.exec_cmds(
    ["curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"], 
    condition=f"! type cargo &> /dev/null", 
    msg="Installing rust...")

# TODO: this requires sudo which may not always be appropriate
remotes.exec_cmds(
    ["sudo apt update",
     "sudo apt install -y protobuf-compiler"],
     condition="! type protoc &> /dev/null",
     msg="Installing protobuf compiler...")

remotes.exec_cmds(
    ["echo off | sudo tee /sys/devices/system/cpu/smt/control"],
    condition="[ \$(cat /sys/devices/system/cpu/smt/active) -eq \"1\" ]",
    msg="Disabling hyper-threading..."
)

remotes.exec_cmds(
    ["sudo usermod -aG kvm \$(whoami)",
     "echo ulimit -n 1048576 >> ~/.bashrc"],
    msg="Adding user to kvm group + increasing open file descriptor limit..."
)

remotes.exec_cmds(
    [f"git clone git@github.com:eth-easl/dandelion.git {RPATH_DANDELION}"], 
    condition=f"[ ! -d {RPATH_DANDELION} ]", 
    msg="Cloning dandelion...")

if not args.branch is None and args.branch != "":
    remotes.exec_cmds(
        [f"cd {RPATH_DANDELION}",
        f"git checkout {args.branch}"],
        msg=f"Checking out user specified branch {args.branch}"
    )

ips = args.internal_ips if has_internal_ips else [t.split('@')[-1] for t in remotes.targets]
multinode_cfg = gen_cfg_multinode(ips)
remotes.write_file_content(
    multinode_cfg, PATH_CFG_MULTINODE, 
    msg="Adding multinode configuration..."
)

remotes.copy_from_local(
    LPATH_START_SCRIPT, 
    RPATH_START_SCRIPT, 
    condition=f"[ ! -f {RPATH_START_SCRIPT} ]")
