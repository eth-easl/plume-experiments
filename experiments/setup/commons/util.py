import os
import sys

from commons.colors import print_info, print_error
from commons.local import Local
from commons.remote import RemoteTargets

LOCAL_SSH_KEY = "~/Projects/control_center/remote_setup/server_ssh_key"
REMOTE_SSH_KEY = "~/.ssh/id_ed25519"

def generate_ssh_keys():
    if not os.path.exists(os.path.expanduser(LOCAL_SSH_KEY)):
        keygen_res = Local.exec_cmd(f"ssh-keygen -t ed25519 -f {LOCAL_SSH_KEY} -N ''")
        if keygen_res[0] != 0:
            print_error(keygen_res[2])
            return False
        
        print_info("ACTION REQUIRED: Please add a new SSH key to your GitHub profile.")
        print_info("Step 1:$ Visit https://github.com/settings/ssh/new")
        print_info("Step 2: Paste the following contents:")
        with open(os.path.expanduser(f"{LOCAL_SSH_KEY}.pub")) as f:
            print_info(f.read())
        input("Press Enter after making these changes to continue.")\
        
    return True

def copy_ssh_keys(remotes: RemoteTargets):
    condition = f"[ ! -f {REMOTE_SSH_KEY} ]"
    commands = [
        "ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts",
        "ssh-keyscan -t rsa gitlab.inf.ethz.ch >> ~/.ssh/known_hosts"
    ]
    remotes.exec_cmds(commands, condition=condition)
    if not remotes.check_and_print_results():
        return False
    
    remotes.copy_from_local(LOCAL_SSH_KEY, REMOTE_SSH_KEY, condition=condition)
    return remotes.check_and_print_results()

def get_remotes(ssh_key_path="", targets=None) -> RemoteTargets:
    if targets is None:
        if len(sys.argv) <= 1:
            print_error(f"Usage {sys.argv[0]} target0 [target1 ...]")
        targets = sys.argv[1:]
    remotes = RemoteTargets(targets, parallel_exec=True, ssh_key_path=ssh_key_path)

    ok = remotes.check_connection()
    if not ok: exit()

    print(f"Got remote targets: {remotes.targets}")
    return remotes

def common_remote_setup(remotes: RemoteTargets):
    ok = generate_ssh_keys()
    if not ok: exit()

    ok = copy_ssh_keys(remotes)
    if not ok: exit()

    remotes.exec_cmds(
        [f"sed -i '/case \$- in/,/esac/ {{ /^#/! s/^/#/; }}' ~/.bashrc", # -> allows non interactive shells to load the .bashrc on cloudlab nodes
         f"sed -i 's/^#force_color_prompt=yes/force_color_prompt=yes/' ~/.bashrc"], # -> might cause the .bashrc to fail further below
         msg="Updating .bashrc file...")

    remotes.exec_cmds(
        ["git config --global user.name \"Tobias Stocker\"",
         "git config --global user.email \"tobias.stocker@inf.ethz.ch\""],
        msg="Configuring git..."
    )

    print("Common remote setup done.")
