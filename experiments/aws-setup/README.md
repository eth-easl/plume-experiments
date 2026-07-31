# AWS Setup Scripts

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

2. Make sure to add a newline at the end then press `Ctrl + D` to start parsing the node info.

3. The script now pasts the parsed results and summarizes the setup. Press `Enter` to start the setup.

    ```
    Client node (Node 0)
    Public IP:   13.62.99.122
    Internal IP: 172.31.32.183
    Worker nodes:
    Node 1:
        Public IP:   13.60.99.0
        Internal IP: 172.31.45.53

    Multinode config:
    {
    "queue_server": {
        "node_id": 0,
        "url": "172.31.32.183:8081"
    },
    "data_servers": [
        {
        "node_id": 0,
        "url": "172.31.32.183:10000"
        },
        {
        "node_id": 1,
        "url": "172.31.45.53:10000"
        }
    ]
    }

    Confirm setup...
    Press [ENTER] to continue or [ESC] to abort...
    ```

4. After the setup is complete it will print the ssh commands.

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

5. Finally, the client node needs some manual setup:
    - Build the plume client/tpch runner using `scripts/build_client.sh`.
    - Set the ip address of the dandelion node that should receive the requests in the Plume benchmark configs. 

# Start experiments

The dandelion nodes may be started using the `~/start_dandelion_plumev2.sh` script on the node itself or using the `remote_start_plume_workers.py` python script from a remote node.

The benchmarks can be run using `~/plume-v2/build/plume/benchmarks/tpch/plume_bench ~/plume-v2/benchmarks/tpch/<config>` if the client was built or `~/plume_bench ~/plume-v2/benchmarks/tpch/<config>` if the client release was installed.

