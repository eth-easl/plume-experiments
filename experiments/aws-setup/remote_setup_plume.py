import argparse
from commons.util import get_remotes, common_remote_setup
from commons.dandelion import *

# configuration
RPATH_PLUME             = "~/plume"
RPATH_PLUME_OPS_INSTALL = "~/plop_install"
RPATH_CFG_PLUME_SINGLE  = "~/cfg_plume_single.json"
RPATH_CFG_PLUME_MULTI   = "~/cfg_plume_multi.json"
RPATH_START_SCRIPT      = "~/start_dandelion_plume.sh"
DANDELION_SYSTEM_CORES  = 6


# basic setup
parser = argparse.ArgumentParser(description="Setup plume on remote targets.")
parser.add_argument("targets", nargs='+', type=str)
parser.add_argument("-t", "--token", type=str)
parser.add_argument("-b", "--branch", type=str)
parser.add_argument("--aws", action="store_true")
parser.add_argument("--ops", action="store_true")
parser.add_argument("--benchmarks", action="store_true")
parser.add_argument("--tools", action="store_true")
args = parser.parse_args()

if args.token: 
    remotes = get_remotes(ssh_key_path=args.token, targets=args.targets)
elif args.aws: 
    remotes = get_remotes(ssh_key_path="~/.ssh/aws-2026.pem", targets=args.targets)
else: 
    remotes = get_remotes(targets=args.targets)
common_remote_setup(remotes)


# > aws only
if args.aws:
    remotes.exec_cmd(
        "sudo apt update && sudo apt install -y make build-essential unzip",
        msg="Installing basic build tools."
    )


# plume setup
remotes.exec_cmds(
    [f"sed -i '/^case \$- in/,/^esac/ s/^[[:space:]]*\([^#[:space:]]\)/#\1/' ~/.bashrc", # -> allows non interactive shells to load the .bashrc on cloudlab nodes
     f"git clone git@github.com:tostocker/plume.git {RPATH_PLUME}"], 
    condition=f"[ ! -d {RPATH_PLUME} ]", 
    msg="Cloning plume repository...")

if not args.branch is None and args.branch != "":
    remotes.exec_cmds(
        [f"cd {RPATH_PLUME}",
        f"git checkout {args.branch}"],
        msg=f"Checking out user specified branch {args.branch}"
    )

remotes.exec_cmds(
    [f"{RPATH_PLUME}/scripts/setup_cloudlab.sh"], 
    msg="Installing building tools...")

if args.ops:
    remotes.exec_cmds(
        [f"mkdir {RPATH_PLUME_OPS_INSTALL}",
         f"cd {RPATH_PLUME}",
         f"./scripts/build_dandelion.sh -b build_ops_kvm",
         f"cp {RPATH_PLUME}/build_ops_kvm/src/fmt_fetch_req {RPATH_PLUME_OPS_INSTALL}/",
         f"cp {RPATH_PLUME}/build_ops_kvm/src/fmt_store_req {RPATH_PLUME_OPS_INSTALL}/",
         f"cp {RPATH_PLUME}/build_ops_kvm/src/assemble_parquet_region {RPATH_PLUME_OPS_INSTALL}/",
         f"cp {RPATH_PLUME}/build_ops_kvm/src/create_parquet_regions {RPATH_PLUME_OPS_INSTALL}/",
         f"cp {RPATH_PLUME}/build_ops_kvm/src/parquet_tail_load {RPATH_PLUME_OPS_INSTALL}/",
         f"cp {RPATH_PLUME}/build_ops_kvm/src/plume_op {RPATH_PLUME_OPS_INSTALL}/"], 
        condition=f"[ ! -d {RPATH_PLUME_OPS_INSTALL} ]", 
        msg="Building and installing plume operators...")
    
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
    
if args.benchmarks:
    remotes.exec_cmds(
        [f"cd {RPATH_PLUME}",
         "mkdir build_benchmarks",
         "cd build_benchmarks",
         "cmake ../benchmarks -GNinja",
         "ninja"], 
        msg="Building plume benchmarks...")

if args.tools:
    remotes.exec_cmds(
        [f"cd {RPATH_PLUME}",
         "mkdir build_tools",
         "cd build_tools",
         "cmake ../tools -GNinja -DPLUME_TOOL_TPCH_DATA_GENERATOR=ON -DPLUME_TOOL_DUCKDB_NATIVE_RUNNER=ON -DPLUME_TOOL_ARROW_DECODER=ON -DPLUME_TOOL_DUCKDB_DECODER=ON",
         "ninja"], 
        msg="Building plume tools...")