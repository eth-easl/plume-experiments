import argparse
import sys
import time
from commons.util import get_remotes

# configuration
RPATH_START_SCRIPT = "~/start_dandelion_plumev2.sh"
RPATH_LOG          = "~/dandelion.log"
SSH_KEY_PATH       = "~/.ssh/aws-ireland.pem"


# basic setup
parser = argparse.ArgumentParser(description="Setup plume on remote targets.")
parser.add_argument("targets", nargs='+', type=str)
parser.add_argument("-t", "--token", type=str)
parser.add_argument("--aws", action="store_true")
args = parser.parse_args()

if args.token: 
    remotes = get_remotes(ssh_key_path=args.token, targets=args.targets)
elif args.aws: 
    remotes = get_remotes(ssh_key_path=SSH_KEY_PATH, targets=args.targets)
else: 
    remotes = get_remotes(targets=args.targets)


# start
remotes.exec_cmd(
    f"tmux new-session -d -s dandelion '{RPATH_START_SCRIPT} > {RPATH_LOG} 2>&1'",
    msg="Starting dandelion...")

# catch ctrl+c to stop
try:
    print("Started dandelion session.")
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    remotes.exec_cmd(
        f"tmux kill-session -t dandelion",
        msg="Stopping dandelion...")
    print("Finished.")
