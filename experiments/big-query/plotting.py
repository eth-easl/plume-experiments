import pandas as pd
import matplotlib.pyplot as plt
import json
file_path = "bq-results-20260216-084706-1771231751221.json"

datalist = []

with open(file_path) as f:
    for line in f:
        line = line.strip()
        if line:
            new_line = json.loads(line)
            # remove lines we do not need
            new_line.pop("project_id")
            new_line.pop("project_number")
            new_line.pop("user_email")
            new_line.pop("principal_subject")
            new_line.pop("job_id") 
            new_line.pop("job_type") 
            new_line.pop("query_info")
            new_line.pop("job_creation_reason")
            if "destination_table" in new_line:
                new_line.pop("destination_table") 
            if "statement_type" in new_line:
                new_line.pop("statement_type")
            if "priority" in new_line:
                new_line.pop("priority") 
            new_line.pop("state") 
            new_line.pop("reservation_group_path") 
            # ignore ones that had errors 
            if "error_result" in new_line:
                # print(new_line["error_result"])
                continue 

            # flatten job stages
            job_stages = new_line.pop("job_stages")
            # if len(job_stages) > 1:
            #     print(f"long timeline: {job_stages}")
            # for (key, value) in timeline.items()
            # flatten labels
            label_dict = new_line.pop("labels")
            label_dict = {d['key']: d['value'] for d in label_dict}
            if "query" not in label_dict.keys():
                continue
            for (key, value) in label_dict.items():
                if key == "query":
                    new_line["query_number"] = int(value)
                else:
                    new_line[key] = value
            # flaten referenced tables
            referenced_tables = new_line.pop("referenced_tables")
            # not clean yet, but works for now
            if len(referenced_tables) >= 1:
                # print(referenced_tables)
                # assuming at the moment all tables come from same dataset
                dataset_id = referenced_tables[0]["dataset_id"]
                split_id = dataset_id.split(sep="_")
                if len(split_id) == 3:
                    new_line["loaded"] = True
                else:
                    new_line["loaded"] = False
                new_line['dataset_id'] = referenced_tables[0]["dataset_id"]  
            # if line_print < 5:
                # print(new_line)
                # line_print = line_print + 1
            # adjust datatypes
            datalist.append(new_line)

raw_frame = pd.json_normalize(datalist)
raw_frame["start_time"] = pd.to_datetime(raw_frame["start_time"])
raw_frame["end_time"] = pd.to_datetime(raw_frame["end_time"])
raw_frame["elapsed_wallclock"] = (raw_frame["end_time"] - raw_frame["start_time"]).dt.total_seconds() * 1000
raw_frame = raw_frame[raw_frame["query"].notna()]
# print(raw_frame[raw_frame["total_slot_ms"].isna()])
# TODO: check the values getting filtered out here
raw_frame = raw_frame[raw_frame["total_slot_ms"].notna()]
# convert types
raw_frame["total_slot_ms"] = raw_frame["total_slot_ms"].astype(int)
raw_frame["total_bytes_billed"] = raw_frame["total_bytes_billed"].astype(int)
# print(raw_frame.columns)

no_loaded = raw_frame[raw_frame["loaded"] == False]
aggregate_frame = no_loaded.groupby(["query_number", "scale"])["elapsed_wallclock"].agg(Min='min', Mean='mean', Max='max').reset_index()
print(aggregate_frame)
aggregate_frame.to_csv("big-query-aggregated.csv", index=False)

time_frame = raw_frame[["query_number", "scale", "loaded", "total_slot_ms", "total_bytes_billed", "elapsed_wallclock"]]
print(time_frame)

time_frame.to_csv("big_query_data.csv", index=False)

query_number = 2
time_frame = time_frame[time_frame["query_number"] == query_number] 

print(time_frame)
slot_time = time_frame.groupby(by=["scale", "loaded"])["total_slot_ms"].mean().unstack()
slot_time = slot_time / 1000 # convert to seconds
bytes_billed = time_frame.groupby(by=["scale", "loaded"])["total_bytes_billed"].mean().unstack()
wallclock_time = time_frame.groupby(by=["scale", "loaded"])["elapsed_wallclock"].mean().unstack()
print(slot_time)
print(bytes_billed)
print(wallclock_time)

fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(10, 10), sharex=True)
axes[0].legend
axes[-1].set_xlabel("Scale Factor")

wallclock_axis = axes[0]
wallclock_axis.plot(wallclock_time)
wallclock_axis.set_ylabel("Wallclock time [s]")
wallclock_axis.legend(['Storage', 'Table'], loc="center left")

slot_axis = axes[1]
slot_axis.plot(slot_time)
slot_axis.set_ylabel("Total slot time [s]")
slot_axis.legend(['Storage', 'Table'], loc="center left")

bytes_axis = axes[2]
bytes_axis.plot(bytes_billed)
bytes_axis.set_ylabel("Billed bytes")
bytes_axis.legend(['Storage', 'Table'], loc="center left")

fig.suptitle(f"Query {query_number}")

# plt.show()
plt.savefig("big_query.png")