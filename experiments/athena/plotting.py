import pandas as pd
import matplotlib.pyplot as plt
import json

file_sf_1 = "statistics_sf1.json"
file_sf_10 = "statistics_sf10.json"
file_sf_100 = "statistics_sf100.json"
file_sf_1000 = "statistics_sf1000.json"

query_result_cols = []
query_result_cols.append('[l_returnflag, l_linestatus, sum_qty, sum_base_price, sum_disc_price, sum_charge, avg_qty, avg_price, avg_disc, count_order]')
query_result_cols.append('[s_acctbal, s_name, n_name, p_partkey, p_mfgr, s_address, s_phone, s_comment]')
query_result_cols.append('[l_orderkey, revenue, o_orderdate, o_shippriority]')
query_result_cols.append('[o_orderpriority, order_count]')
query_result_cols.append('[n_name, revenue]')
query_result_cols.append('[revenue]')
query_result_cols.append('[supp_nation, cust_nation, l_year, revenue]')
query_result_cols.append('[o_year, mkt_share]')
query_result_cols.append('[nation, o_year, sum_profit]')
query_result_cols.append('[c_custkey, c_name, revenue, c_acctbal, n_name, c_address, c_phone, c_comment]')
query_result_cols.append('[ps_partkey, value]')
query_result_cols.append('[l_shipmode, high_line_count, low_line_count]')
query_result_cols.append('[c_count, custdist]')
query_result_cols.append('[promo_revenue]')
query_result_cols.append('[s_suppkey, s_name, s_address, s_phone, total_revenue]')
query_result_cols.append('[p_brand, p_type, p_size, supplier_cnt]')
query_result_cols.append('[avg_yearly]')
query_result_cols.append('[c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice, _col5]')
query_result_cols.append('[revenue]') # TODO diambiguate
query_result_cols.append('[s_name, s_address]')
query_result_cols.append('[s_name, numwait]')
query_result_cols.append('[cntrycode, numcust, totacctbal]')

def flatten_stages(nested_stages):
    new_list = []
    if "SubStages" not in nested_stages:
        return new_list
    substages = nested_stages.pop("SubStages")
    for substage in substages: 
        inner_stages = flatten_stages(substage) 
        new_list.append(substage)
        new_list.extend(inner_stages)
    return new_list 

def parse_file(file_name, scale):
    data_list = []
    file = open(file_name)
    file_json = json.load(file)
    for measurement in file_json:
        runtime_statistics = measurement.pop("QueryRuntimeStatistics")
        timeline = runtime_statistics.pop("Timeline")
        total_runtime = timeline["TotalExecutionTimeInMillis"]
        rows = runtime_statistics.pop("Rows")
        read_bytes = rows["InputBytes"]
        output_stage = runtime_statistics.pop("OutputStage")
        stage_list = flatten_stages(output_stage)
        stage_list.insert(0, output_stage)
        # runtime statistic is now empty
        query_stage_plan = output_stage.pop("QueryStagePlan")
        column_names = json.loads(query_stage_plan["Identifier"])["columnNames"]
        query_number = query_result_cols.index(column_names) + 1
        if query_number == 6:
            # print(query_stage_plan)
            # print(stage_list)
            if len(stage_list) == 2:
                query_number = 6
            else:
                # len(stage_list) == 3:
                query_number = 19
            # else:
                # raise Exception("Number of stages should be one of the two expected")
        total_slot_ms = 0
        for stage in stage_list:
            # print(stage)
            stage_time = stage["ExecutionTime"]
            # print(stage_time)
            total_slot_ms +=stage_time 
        # print(query_number)
        # print(total_runtime)
        # print(read_bytes)
        # print(total_slot_ms)
        new_data_dict = {}
        new_data_dict["query_number"] = query_number
        new_data_dict["scale"] = scale
        new_data_dict["elapsed_wallclock"] = total_runtime
        new_data_dict["total_bytes_billed"] = read_bytes
        new_data_dict["total_slot_ms"] = total_slot_ms
        data_list.append(new_data_dict)
    return data_list

data_list = []
data_list.extend(parse_file(file_sf_1, 1))
data_list.extend(parse_file(file_sf_10, 10))
data_list.extend(parse_file(file_sf_100, 100))
data_list.extend(parse_file(file_sf_1000, 1000))
print(len(data_list))

raw_frame = pd.DataFrame(data_list)
print(raw_frame)

raw_frame.to_csv("athena-data.csv", index=False)

# aggragate per frame
aggregate_frame = raw_frame.groupby(['query_number', 'scale'])['elapsed_wallclock'].agg(Min='min', Mean='mean', Max='max').reset_index()
print(aggregate_frame)
aggregate_frame.to_csv("athena-aggregated.csv", index=False)

# query_number = 2

# working_frame = raw_frame[raw_frame['query_number'] == query_number]
# print(working_frame)
# time_frame = working_frame[["scale", "loaded", "total_slot_ms", "total_bytes_billed", "elapsed_wallclock"]]
# print(time_frame)
# slot_time = time_frame.groupby(by=["scale", "loaded"])["total_slot_ms"].mean().unstack()
# slot_time = slot_time / 1000 # convert to seconds
# bytes_billed = time_frame.groupby(by=["scale", "loaded"])["total_bytes_billed"].mean().unstack()
# wallclock_time = time_frame.groupby(by=["scale", "loaded"])["elapsed_wallclock"].mean().unstack()
# print(slot_time)
# print(bytes_billed)
# print(wallclock_time)

# fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(10, 10), sharex=True)
# axes[0].legend
# axes[-1].set_xlabel("Scale Factor")

# wallclock_axis = axes[0]
# wallclock_axis.plot(wallclock_time)
# wallclock_axis.set_ylabel("Wallclock time [s]")
# wallclock_axis.legend(['Storage', 'Table'], loc="center left")

# slot_axis = axes[1]
# slot_axis.plot(slot_time)
# slot_axis.set_ylabel("Total slot time [s]")
# slot_axis.legend(['Storage', 'Table'], loc="center left")

# bytes_axis = axes[2]
# bytes_axis.plot(bytes_billed)
# bytes_axis.set_ylabel("Billed bytes")
# bytes_axis.legend(['Storage', 'Table'], loc="center left")

# fig.suptitle(f"Query {query_number}")

# # plt.show()
# plt.savefig("big_query.png")