import json
import os
import subprocess
import sys

from commons.colors import print_info, print_error
from commons.local import Local
from commons.remote import RemoteTargets

REMOTE_SSH_KEY = "~/.ssh/id_ed25519"

APT_WAIT = ("while sudo fuser /var/lib/dpkg/lock-frontend /var/lib/apt/lists/lock "
            "/var/cache/apt/archives/lock >/dev/null 2>&1; do sleep 5; done")
APT = "sudo apt-get -o DPkg::Lock::Timeout=600"

def load_setup_config(path: str):
    with open(path, "r") as file:
        config = json.load(file)

    def required(key):
        key_parts = key.split('.')
        cfg = config
        if len(key_parts) > 1:
            for i in range(len(key_parts)-1):
                if not key_parts[i] in cfg:
                    print(f"Missing required key '{key}' in setup config!")
                    exit(1)
                cfg = cfg[key_parts[i]]
        if not key_parts[-1] in cfg:
            print(f"Missing required key '{key}' in setup config!")
            exit(1)

    required("cloneWithHTTP")
    if not config["cloneWithHTTP"]:
        required("gitConfig.sshKeyPath")
    required("plumeBuildFunctions")
    required("plumeBuildClient")
    required("plumeInstallFunctions")
    required("plumeInstallClient")
    
    return config

def generate_ssh_keys(local_ssh_key):
    if not os.path.exists(os.path.expanduser(local_ssh_key)):
        keygen_res = Local.exec_cmd(f"ssh-keygen -t ed25519 -f {local_ssh_key} -N ''")
        if keygen_res[0] != 0:
            print_error(keygen_res[2])
            return False
        
        print_info("ACTION REQUIRED: Please add a new SSH key to your GitHub profile.")
        print_info("Step 1:$ Visit https://github.com/settings/ssh/new")
        print_info("Step 2: Paste the following contents:")
        with open(os.path.expanduser(f"{local_ssh_key}.pub")) as f:
            print_info(f.read())
        input("Press Enter after making these changes to continue.")
        
    return True

def copy_ssh_keys(remotes: RemoteTargets, local_ssh_key):
    condition = f"[ ! -f {REMOTE_SSH_KEY} ]"
    commands = [
        "ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts",
        "ssh-keyscan -t rsa gitlab.inf.ethz.ch >> ~/.ssh/known_hosts"
    ]
    remotes.exec_cmds(commands, condition=condition)
    if not remotes.check_and_print_results():
        return False
    
    remotes.copy_from_local(local_ssh_key, REMOTE_SSH_KEY, condition=condition)
    return remotes.check_and_print_results()

def get_remotes(ssh_key_path="", targets=None) -> RemoteTargets:
    if targets is None:
        if len(sys.argv) <= 1:
            print_error(f"Usage {sys.argv[0]} target0 [target1 ...]")
        targets = sys.argv[1:]
    remotes = RemoteTargets(targets, parallel_exec=True, ssh_key_path=ssh_key_path)

    ok = remotes.check_connection()
    if not ok: exit(1)

    print(f"Got remote targets: {remotes.targets}")
    return remotes

def common_remote_setup(remotes: RemoteTargets, config: dict):
    if "sshKeyPath" in config and len(config["sshKeyPath"]) > 0:
        ok = generate_ssh_keys(config['sshKeyPath'])
        if not ok: exit(1)

        ok = copy_ssh_keys(remotes, config['sshKeyPath'])
        if not ok: exit(1)

    remotes.exec_cmds(
        [f"sed -i '/case \$- in/,/esac/ {{ /^#/! s/^/#/; }}' ~/.bashrc", # -> allows non interactive shells to load the .bashrc on cloudlab nodes
         f"sed -i 's/^#force_color_prompt=yes/force_color_prompt=yes/' ~/.bashrc"], # -> might cause the .bashrc to fail further below
         msg="Updating .bashrc file...")

    if "gitUser" in config and "gitEmail" in config:
        remotes.exec_cmds(
            [f"git config --global user.name \"{config['gitUser']}\"",
             f"git config --global user.email \"{config['gitEmail']}\""],
            msg="Configuring git..."
        )

    print("Common remote setup done.")

def run_setup_step(name, cmd, config, cwd=None):
    if "sshKeyPath" in config:
        cmd += ["--local-ssh-key", config["sshKeyPath"]]
    if "gitUser" in config:
        cmd += ["--git-user", config["gitUser"]]
    if "gitEmail" in config:
        cmd += ["--git-email", config["gitEmail"]]

    cmd_res = subprocess.run(cmd, cwd=cwd)
    if cmd_res.returncode != 0:
        print_error(f"{name} setup failed! (exit code {cmd_res.returncode})")
        exit(1)
