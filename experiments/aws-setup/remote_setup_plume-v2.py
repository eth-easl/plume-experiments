import argparse
from commons.util import get_remotes, common_remote_setup
from commons.dandelion import *

# configuration
RPATH_PLUME            = "~/plume-v2"
RPATH_PLUME_FUNCTIONS  = "~/plume_functions"
RPATH_CFG_PLUME_SINGLE = "~/cfg_plumev2_single.json"
RPATH_CFG_PLUME_MULTI  = "~/cfg_plumev2_multi.json"
RPATH_START_SCRIPT     = "~/start_dandelion_plumev2.sh"
LPATH_GH_TOKEN         = "./gh_token.txt"
RPATH_GH_TOKEN         = "~/gh_token.txt"
DANDELION_SYSTEM_CORES = 6
SSH_KEY_PATH           = "~/.ssh/aws-ireland.pem"


# basic setup
parser = argparse.ArgumentParser(description="Setup plume on remote targets.")
parser.add_argument("targets", nargs='+', type=str)
parser.add_argument("-t", "--token", type=str)
parser.add_argument("-b", "--branch", type=str)
parser.add_argument("--aws", action="store_true")
parser.add_argument("--install-functions", action="store_true")
parser.add_argument("--build-functions", action="store_true")
parser.add_argument("--install-client", action="store_true")
parser.add_argument("--build-client", action="store_true")
args = parser.parse_args()

if args.token: 
    remotes = get_remotes(ssh_key_path=args.token, targets=args.targets)
elif args.aws: 
    remotes = get_remotes(ssh_key_path=SSH_KEY_PATH, targets=args.targets)
else: 
    remotes = get_remotes(targets=args.targets)
common_remote_setup(remotes)


# > aws only
if args.aws:
    remotes.exec_cmd(
        "sudo apt update && sudo apt install -y make build-essential unzip libssl-dev",
        msg="Installing basic build tools..."
    )


# plume clone and basic setup
remotes.exec_cmds(
    [f"sed -i '/^case \$- in/,/^esac/ s/^[[:space:]]*\([^#[:space:]]\)/#\1/' ~/.bashrc", # -> allows non interactive shells to load the .bashrc on cloudlab nodes
     f"git clone git@github.com:tostocker/plume-v2.git {RPATH_PLUME}"], 
    condition=f"[ ! -d {RPATH_PLUME} ]", 
    msg="Cloning plume repository...")

if not args.branch is None and args.branch != "":
    remotes.exec_cmds(
        [f"cd {RPATH_PLUME}",
        f"git checkout {args.branch}"],
        msg=f"Checking out user specified branch {args.branch}")


# install functions/client
if args.install_functions or args.install_client:
    remotes.exec_cmd('sudo apt install -y gh', msg="Installing gh...")
    remotes.copy_from_local(LPATH_GH_TOKEN, RPATH_GH_TOKEN)
    remotes.exec_cmd(f'cat {RPATH_GH_TOKEN} | gh auth login --with-token', msg="Authorizing gh...")

if args.install_functions:
    release_url = "https://github.com/eth-easl/plume-v2/releases/download/operators"
    remotes.exec_cmds(
        ['mkdir -p ~/plume_functions',
         'cd ~/plume_functions',
         f'gh release download operators --repo eth-easl/plume-v2 --pattern \\"plume_*\\" --clobber'],
        msg="Installing functions...")

if args.install_client:
    remotes.exec_cmds(
        ['gh release download client --repo eth-easl/plume-v2 --pattern \\"plume_bench\\" --clobber',
         'chmod +x plume_bench'],
        msg="Installing client...")


# build functions/client
if args.build_functions or args.build_client:
    remotes.exec_cmds(
        [f"{RPATH_PLUME}/scripts/setup_cloudlab.sh"], 
        msg="Installing building tools...")

if args.build_functions:
    remotes.exec_cmds(
        [f"mkdir {RPATH_PLUME_FUNCTIONS}",
         f"cd {RPATH_PLUME}",
         f"./scripts/build_dandelion.sh", # TODO: add -t skylake-avx512
         f"cp {RPATH_PLUME}/build_dandelion/functions/plume_* {RPATH_PLUME_FUNCTIONS}/"], 
        condition=f"[ ! -d {RPATH_PLUME_FUNCTIONS} ]", 
        msg="Building and installing plume functions...")
    
if args.build_client:
    remotes.exec_cmds(
        [f"cd {RPATH_PLUME}",
         "./scripts/setup_duckdb.sh",
         "cd build",
         "mkdir plume",
         "cd plume",
         "cmake ../.. -GNinja -DPLUME_BUILD_FUNCTIONS=OFF -DPLUME_BUILD_BENCHMARKS=ON",
         "ninja"], 
        msg="Building plume client...")


# create dandelion configurations
if args.build_functions or args.install_functions:
    path_preload_cfg = f"{RPATH_PLUME}/dandelion/preload_cfg_plume.json"
    remotes.write_file_content(gen_start_script([RPATH_CFG_PLUME_MULTI, RPATH_CFG_PLUME_SINGLE]), RPATH_START_SCRIPT)
    remotes.write_file_content(gen_cfg_single(path_preload_cfg, DANDELION_SYSTEM_CORES), RPATH_CFG_PLUME_SINGLE)
    for i, t in enumerate(remotes.targets):
        mask = [False]*len(remotes.targets)
        mask[i] = True
        if i == 0:
            cfg = gen_cfg_master(path_preload_cfg, i, DANDELION_SYSTEM_CORES)
        else:
            cfg = gen_cfg_worker(path_preload_cfg, i, DANDELION_SYSTEM_CORES)
        remotes.write_file_content(cfg, RPATH_CFG_PLUME_MULTI, mask=mask)

    remotes.exec_cmds(
        [f"chmod +x {RPATH_START_SCRIPT}"],
        msg="Making dandelion start script executable...")

    remotes.exec_cmd(
        f"sed -i 's/<dandelion_url>/localhost/g' {RPATH_PLUME}/benchmarks/tpch/config/*",
        mask=([True] + [False]*(len(remotes.targets) - 1)),
        msg="Setting <dandelion_url> to localhost in configs on client node..."
    )
