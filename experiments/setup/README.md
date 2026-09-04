# Setup

This part contains utilities to setup Plume on a cluster of aws or cloudlab nodes. The key scripts are:

- `remote_setup_dandelion.py` clones the Dandelion repo, installs dependencies such as Rust, and creates configurations based on the node information.
- `remote_setup_dataclient.py` clones the `plume-experiments` repo, makes sure go is installed, fetches the tpch data from S3 and saves it under `~/data`.
- `remote_setup_plume.py` clones the Plume repo, installs the necessary dependencies, and builds/installs the Dandelion function binaries and/or client.
- `aws_full_setup.py` takes a set of aws node information and runs the Dandelion and Plume remote setup scripts accordingly (see AWS Setup below).
- `cloudlab_full_setup.py` takes a set of cloudlab node information and runs the Dandelion and Plume remote setup scripts accordingly (see Cloudlab Setup below).
- `remote_start_plume_workers.py` starts Dandelion with the Plume configurations.

# Setup Configuration

Both full setup scripts read their configuration from `setup_config.json`, located next to the scripts in `experiments/setup/`. The file is read before any node input is parsed, and the setup aborts if a required parameter is missing.

| Parameter | Type | Required | Description |
|-|-|-|-|
| `cloneWithHTTP` | bool | yes | Clone the repositories over HTTPS instead of SSH. When `false`, the SSH key at `gitConfig.sshKeyPath` is used for git access on the nodes (see below). |
| `sshKey` | string | no | Path to the private key used to reach the nodes themselves (passed to `ssh -i`/`scp -i`). Omit or leave empty to rely on the default SSH configuration. |
| `dandelionBranch` | string | no | Branch to check out in the Dandelion repository after cloning. Omit or leave empty to stay on the default branch. |
| `plumeBranch` | string | no | Branch to check out in the Plume repository after cloning. Omit or leave empty to stay on the default branch. |
| `plumeInstallFunctions` | bool | yes | Download the prebuilt Dandelion function binaries from the `latest-main` release into `~/plume_functions`. |
| `plumeInstallClient` | bool | yes | Download the prebuilt `plume`, `plume_bench` and `plume_export` binaries into `~/plume_bin`. |
| `plumeBuildFunctions` | bool | yes | Build the Dandelion function binaries from source into `~/plume_functions`. Skipped if the directory already exists. |
| `plumeBuildClient` | bool | yes | Build the Plume client from source in `~/plume/build/plume`. |
| `gitConfig` | object | no | Git settings applied to every node, see the following three parameters. |
| `gitConfig.sshKeyPath` | string | only if `cloneWithHTTP` is `false` | Path to the local SSH key used for git access on the nodes. If the key does not exist it is generated, and you are prompted to add the public key to your GitHub profile before the setup continues. The key is then copied to every node as `~/.ssh/id_ed25519`. |
| `gitConfig.gitUser` | string | no | Value for `git config --global user.name` on each node. Only applied if `gitConfig.gitEmail` is set as well. |
| `gitConfig.gitEmail` | string | no | Value for `git config --global user.email` on each node. Only applied if `gitConfig.gitUser` is set as well. |

Note that installing downloads prebuilt release binaries while building compiles them from source. The two are not meant to be combined:

- Functions share the `~/plume_functions` directory. Since the build step is skipped if that directory already exists, enabling `plumeInstallFunctions` and `plumeBuildFunctions` together silently skips the build and leaves the downloaded binaries in place.
- The client does not share a directory: installing puts the binaries in `~/plume_bin`, building puts them in `~/plume/build/plume`. Enabling both produces both, see Start experiments below for the respective paths.

Example:

```json
{
    "cloneWithHTTP": true,
    "sshKey": "~/.ssh/plume26.pem",

    "dandelionBranch": "",
    "plumeBranch": "",

    "plumeBuildFunctions": false,
    "plumeBuildClient": false,
    "plumeInstallFunctions": true,
    "plumeInstallClient": true,

    "gitConfig": {
        "sshKeyPath": "~/.ssh/cloudlab",
        "gitUser": "Your Name",
        "gitEmail": "your.name@inf.ethz.ch"
    }
}
```

## AWS Setup

### Prerequisites

- Cluster of AWS EC2 nodes in the same region where the data is stored.
- SSH key to establish SSH and SCP connections to the nodes.

### Setup

1. Run the `aws_full_setup.py` script and enter the ec2 node details in the following form. The first node will be setup as the client/scheduler node, all others as worker nodes.

    ```
    python aws_full_setup.py
    Paste your node data below then press Enter followed by 'Ctrl + D' to finish.

    --------------------------------------------------
    ec2-13-62-99-122.eu-north-1.compute.amazonaws.com
    ip-172-31-32-183.eu-north-1.compute.internal
    ec2-13-60-99-0.eu-north-1.compute.amazonaws.com
    ip-172-31-45-53.eu-north-1.compute.internal

    ```

2. Press `Ctrl + D` to start parsing the node info.

3. The script now prints the parsed results and summarizes the setup. Press `Enter` to start the setup.

    ```
    Client node (Node 0)
      Public IP:   13.62.99.122
      Internal IP: 172.31.32.183
    Worker nodes:
      Node 1:
        Public IP:   13.60.99.0
        Internal IP: 172.31.45.53

    Confirm setup...
    Press [ENTER] to continue or [ESC] to abort...
    ```

4. After the setup is complete it will print the ssh commands and the command that starts all workers using the `remote_start_plume_workers.py` script.

    ```
    Remote setups completed!

    Parsed nodes:
      Client node (Node 0)
        Public IP:   108.129.97.116
        Internal IP: 172.31.38.186
      Worker nodes:
        Node 1:
          Public IP:   3.250.30.80
          Internal IP: 172.31.42.197

    SSH commands:
      Node 0: ssh -i ~/.ssh/plume26.pem ubuntu@13.62.99.122
      Node 1: ssh -i ~/.ssh/plume26.pem ubuntu@13.60.99.0

    Start workers:
      python remote_start_plume_workers.py -t ~/.ssh/plume26.pem ubuntu@13.62.99.122 ubuntu@13.60.99.0
    ```

## Cloudlab Setup

1. Run the `cloudlab_full_setup.py` script and enter the cloudlab node details in the following form. The first node will be setup as the client/scheduler node, all others as worker nodes.

    ```
    python cloudlab_full_setup.py
    Paste your node data below then press Enter followed by 'Ctrl + D' to finish.

    --------------------------------------------------
    tstocker@pc746.emulab.net
    tstocker@pc752.emulab.net

    ```

2. Press `Ctrl + D` to start parsing the node info.

3. The script now prints the parsed results and summarizes the setup. Press `Enter` to start the setup.

    ```
    Parsed nodes:
    Client node (Node 0)
      User:        tstocker
      Public IP:   pc746.emulab.net
    Internal IP: 10.0.1.1
    Worker nodes:
      Node 1:
        User:        tstocker
        Public IP:   pc752.emulab.net
        Internal IP: 10.0.1.2

    Confirm setup...
    Press [ENTER] to continue or [ESC] to abort...
    ```

4. After the setup is complete it will print the ssh commands and the command that starts all workers using the `remote_start_plume_workers.py` script.

    ```
    Remote setups completed!

    Parsed nodes:
    Client node (Node 0)
      Public IP:   pc746.emulab.net
      Internal IP: 10.0.1.1
    Worker nodes:
      Node 1:
        Public IP:   pc752.emulab.net
        Internal IP: 10.0.1.2

    SSH commands:
      Node 0: ssh tstocker@pc746.emulab.net
      Node 1: ssh tstocker@pc752.emulab.net

    Start workers:
      python remote_start_plume_workers.py tstocker@pc746.emulab.net tstocker@pc752.emulab.net
    ```


---

# Start experiments

The dandelion nodes may be started using the `~/start_dandelion_plume.sh` script on the node itself or using the `remote_start_plume_workers.py` python script from a remote node.

The benchmarks can be run using `~/plume/build/plume/benchmarks/plume_bench ~/plume/benchmarks/tpch/<config>` if the client was built or `~/plume_bin/plume_bench ~/plume/benchmarks/tpch/<config>` if the client release was installed.
