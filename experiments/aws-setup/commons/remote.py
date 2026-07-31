import asyncio
import os.path as osp
import shutil
import subprocess

from commons.colors import print_error, print_debug

class RemoteTargets:
    def __init__(self, targets, parallel_exec=True, ssh_key_path=""):
        self.targets = [f'"{t}"' for t in targets]
        self.parallel_exec = parallel_exec
        self.ssh_bin = shutil.which("ssh")
        self.scp_bin = shutil.which("scp")
        self.exec_fails = []
        self.ssh_key_path = ssh_key_path

    def check_results(self):
        return len(self.exec_fails) == 0

    def check_and_print_results(self):
        next_fail_idx = -1 if len(self.exec_fails) == 0 else self.exec_fails[0][0]
        for t_idx, target in enumerate(self.targets):
            if t_idx == next_fail_idx:
                print(f"Got error for target {target}:")
                print_error(str(self.exec_fails[next_fail_idx][2]).replace('\\n', '\n').replace('\\r', '\r')[2:-2])
                next_fail_idx = next_fail_idx+1 if len(self.exec_fails) > next_fail_idx else -1
        return self.check_results()

    async def _run_async_cmd(self, cmd, mask=None):
        async def _run(idx, cmd):
            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                self.exec_fails.append((idx, stdout, stderr))
        
        tasks = []
        for t_idx, target in enumerate(self.targets):
            if mask[t_idx]:
                print_debug(f'{target} -> "{cmd}"')
                if len(self.ssh_key_path) > 0:
                    tasks.append(_run(t_idx, f'{self.ssh_bin} -oStrictHostKeyChecking=no -p 22 -i "{self.ssh_key_path}" {target} "{cmd}"'))
                else:
                    tasks.append(_run(t_idx, f'{self.ssh_bin} -oStrictHostKeyChecking=no -p 22 {target} "{cmd}"'))
        await asyncio.gather(*tasks)

    # executes a given command on each target
    # one might also provide a mask to execute the command only on some selected machines
    def exec_cmd(self, cmd, mask=None, msg=None, exit_on_fail=True):
        if mask is None:
            mask = [True]*len(self.targets)

        if not msg is None and any(mask):
            print(msg)

        self.exec_fails = []
        if self.parallel_exec:
            asyncio.run(self._run_async_cmd(cmd, mask))
        else:
            for t_idx, target in enumerate(self.targets):
                if mask[t_idx]:
                    print_debug(f'{target} -> "{cmd}"')
                    if len(self.ssh_key_path) > 0:
                        res = subprocess.run(f'{self.ssh_bin} -oStrictHostKeyChecking=no -p 22 -i "{self.ssh_key_path}" {target} "{cmd}"', capture_output=True, shell=True)
                    else:
                        res = subprocess.run(f'{self.ssh_bin} -oStrictHostKeyChecking=no -p 22 {target} "{cmd}"', capture_output=True, shell=True)
                    if res.returncode != 0:
                        self.exec_fails.append((t_idx, str(res.stdout), str(res.stderr)))

        if exit_on_fail:
            if self.check_and_print_results():
                return True
            else:
                print("Aborted.")
                exit()
        else:
            return self.check_results()

    # executes a list of commands on each target
    # one might additionally provide a condition that needs to be met to execute the commands
    def exec_cmds(self, cmds, condition=None, msg=None, exit_on_fail=True):
        cmds_combined = ""
        for cmd in cmds:
            cmds_combined += cmd + " && "
        if len(cmds) > 0:
            cmds_combined = cmds_combined[:-4]

        cond_mask = [True]*len(self.targets)
        if not condition is None:
            self.exec_cmd(condition, exit_on_fail=False)
            for fail in self.exec_fails:
                cond_mask[fail[0]] = False

        if not msg is None and any(cond_mask):
            print(msg)

        self.exec_cmd(cmds_combined, mask=cond_mask)

        if exit_on_fail:
            if self.check_and_print_results():
                return True
            else:
                print("Aborted.")
                exit()
        else:
            return self.check_results()
    
    def copy_from_local(self, local_src, remote_dest, condition=None):
        cond_mask = [True]*len(self.targets)
        if not condition is None:
            self.exec_cmd(condition, exit_on_fail=False)
            for fail in self.exec_fails:
                cond_mask[fail[0]] = False

        self.exec_fails = []
        for t_idx, target in enumerate(self.targets):
            if cond_mask[t_idx]:
                print_debug(f'{local_src} => {target}:{remote_dest}')
                if not osp.exists(osp.expanduser(local_src)):
                    self.exec_fails.append((t_idx, "", f"  Did not find local file {local_src}  "))
                    continue
                if len(self.ssh_key_path) > 0:
                    res = subprocess.run(
                        f'{self.scp_bin} -r -i "{self.ssh_key_path}" {local_src} {target}:{remote_dest}',
                        capture_output=True, shell=True)
                else:
                    res = subprocess.run(
                        f'{self.scp_bin} -r {local_src} {target}:{remote_dest}',
                        capture_output=True, shell=True)
                if res.returncode != 0:
                    self.exec_fails.append((t_idx, str(res.stdout), str(res.stderr)))

    def write_file_content(self, content, remote_dest, mask=None, msg=None, exit_on_fail=True):
        # Escape any existing backticks or dollar signs if you want literal text, 
        # but using single quotes around 'EOF' prevents most shell expansions.
        content = content.replace('"', '\\"')
        content = content.replace("'", "\\'")
        content = content.replace("$", "\\$")
        cmd = f"cat << 'EOF' > {remote_dest}\n{content}\nEOF"
        if msg is None:
            msg = f"Writing content to {remote_dest}..."
        return self.exec_cmd(cmd, mask=mask, msg=msg, exit_on_fail=exit_on_fail)
    
    def check_connection(self):
        ok = self.exec_cmd("ls", msg="Checking connection...", exit_on_fail=False)
        if not ok:
            next_fail_idx = -1 if len(self.exec_fails) == 0 else self.exec_fails[0][0]
            for t_idx, target in enumerate(self.targets):
                if t_idx == next_fail_idx:
                    print_error(f"Did not reach {target}")
                    next_fail_idx = next_fail_idx+1 if len(self.exec_fails) > next_fail_idx else -1
        return ok
