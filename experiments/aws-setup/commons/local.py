import subprocess

class Local:

    # executes a given command
    def exec_cmd(cmd):
        res = subprocess.run([cmd], capture_output=True, shell=True)
        if res.returncode != 0:
            return (res.returncode, 
                    str(res.stdout)[2:-1].replace('\\n', '\n').replace('\\r', '\r'), 
                    str(res.stderr)[2:-1].replace('\\n', '\n').replace('\\r', '\r'))
        else:
            return (0, "", "")

    # executes a list of commands
    # one might additionally provide a condition that needs to be met to execute the commands
    def exec_cmds(cmds, condition=None):
        cmds_combined = ""
        for cmd in cmds:
            cmds_combined += cmd + " && "
        if len(cmds) > 0:
            cmds_combined = cmds_combined[:-4]

        cond_res = Local.exec_cmd(condition)
        if cond_res[0] != 0:
            return (0, "", "")
        
        return Local.exec_cmd(cmds_combined)
