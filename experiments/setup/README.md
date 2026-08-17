# Setup

This part contains utilities to setup Plume on a cluster of aws or cloudlab nodes. The key scripts are:

- `remote_setup_dandelion.py` clones the Dandelion repo, installs dependencies such as Rust, and creates configurations based on the node information.
- `remote_setup_plume.py` clones the Plume repo, installs the necessary dependencies, and builds/installs the Dandelion function binaries and/or client.
- `aws_full_setup.py` takes a set of aws node informations and runs the Dandelion and Plume remote setup scripts accordingly (see AWS Setup below).
- `aws_full_setup.py` takes a set of cloudlab node informations and runs the Dandelion and Plume remote setup scripts accordingly (see Cloudlab Setup below).
- `remote_start_plume_workers.py` starts Dandelion with the Plume configurations.

## AWS Setup

### Prerequisits

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

3. The script now pasts the parsed results and summarizes the setup. Press `Enter` to start the setup.

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

4. After the setup is complete it will print the ssh commands and the command that starts all workers using the `start_plume_workers.py` script.

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
      Node 0: ssh -i ~/.ssh/aws-2026.pem ubuntu@13.62.99.122
      Node 1: ssh -i ~/.ssh/aws-2026.pem ubuntu@13.60.99.0

    Start workers:
      python remote_start_plume_workers.py --aws ubuntu@13.62.99.122 ubuntu@13.60.99.0
    ```

## Cloudlab Setup


1. Run the `cloudlab_full_setup.py` script and enter the ec2 node details in the following form. The first node will be setup as the client/scheduler node, all others as worker nodes.

    ```
    python cloudlab_full_setup.py
    Paste your node data below then press Enter followed by 'Ctrl + D' to finish.

    --------------------------------------------------
    tstocker@pc746.emulab.net
    tstocker@pc752.emulab.net

    ```

2. Press `Ctrl + D` to start parsing the node info.

3. The script now pasts the parsed results and summarizes the setup. Press `Enter` to start the setup.

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

4. After the setup is complete it will print the ssh commands and the command that starts all workers using the `start_plume_workers.py` script.

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

The benchmarks can be run using `~/plume/build/plume/benchmarks/tpch/plume_bench ~/plume/benchmarks/tpch/<config>` if the client was built or `~/plume_bench ~/plume/benchmarks/tpch/<config>` if the client release was installed.
