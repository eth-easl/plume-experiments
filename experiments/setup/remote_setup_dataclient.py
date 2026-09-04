import argparse
from commons.util import get_remotes, common_remote_setup
from commons.dandelion import *

# configuration
RPATH_PLUME_EXPERIMENTS = "~/plume-experiments"
RPATH_DATA              = "~/data"


# basic setup
parser = argparse.ArgumentParser(description="Setup the plume-experiments data client on remote targets.")
parser.add_argument("targets", nargs='+', type=str)
parser.add_argument("-t", "--token", type=str)
parser.add_argument("-b", "--branch", type=str)
parser.add_argument("--aws", action="store_true")
parser.add_argument("--clone-with-http", action="store_true")
parser.add_argument("--local-ssh-key", type=str)
parser.add_argument("--git-user", type=str)
parser.add_argument("--git-email", type=str)
args = parser.parse_args()

config = {}
if args.local_ssh_key:
    config["sshKeyPath"] = args.local_ssh_key
if args.git_user:
    config["gitUser"] = args.git_user
if args.git_email:
    config["gitEmail"] = args.git_email

if args.token: 
    remotes = get_remotes(ssh_key_path=args.token, targets=args.targets)
else: 
    remotes = get_remotes(targets=args.targets)
common_remote_setup(remotes, config)


# > aws only
if args.aws:
    remotes.exec_cmd(
        "sudo apt update && sudo apt install -y make build-essential unzip libssl-dev",
        msg="Installing basic build tools..."
    )


# plume-experiments clone and basic setup
plume_exp_url = "https://github.com/eth-easl/plume-experiments.git" if args.clone_with_http else "git@github.com:eth-easl/plume-experiments.git"
remotes.exec_cmds(
    [f"sed -i '/^case \$- in/,/^esac/ s/^[[:space:]]*\([^#[:space:]]\)/#\1/' ~/.bashrc", # -> allows non interactive shells to load the .bashrc on cloudlab nodes
     f"git clone {plume_exp_url} {RPATH_PLUME_EXPERIMENTS}"], 
    condition=f"[ ! -d {RPATH_PLUME_EXPERIMENTS} ]", 
    msg="Cloning plume-experiments repository...")

if not args.branch is None and args.branch != "":
    remotes.exec_cmds(
        [f"cd {RPATH_PLUME_EXPERIMENTS}",
        f"git checkout {args.branch}"],
        msg=f"Checking out user specified branch {args.branch}...")


# install go
remotes.exec_cmds(
    [f'{RPATH_PLUME_EXPERIMENTS}/experiments/setup/bash/install_go.sh'],
    condition="! command -v go > /dev/null 2>&1",
    msg="Installing go..."
)

# clone tpch data
remotes.exec_cmds(
    [f'{RPATH_PLUME_EXPERIMENTS}/experiments/setup/bash/fetch_s3_data.sh'],
    msg="Fetching S3 data..."
)
