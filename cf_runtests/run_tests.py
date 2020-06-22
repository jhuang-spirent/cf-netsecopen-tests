#!/usr/bin/python3
import csv
import logging
import pathlib
import sys
import time

current_dir = pathlib.Path().absolute()
project_dir = current_dir.parent
sys.path.append(str(project_dir))

from cf_common.CIJenkins import *
from cf_common.cf_functions import *
jenkins = CIJenkins()
add_sys_path(jenkins.input_dir)
loadModule("cf_config")
loadModule("credentials")
from cf_config import *
from credentials import *
from cf_common.CfClient import *
from cf_common.CfRunTest import *

if (pathlib.Path.cwd() / "dev_settings.py").is_file():
    from cf_runtests.dev_settings import *

input_dir, output_dir, report_dir = verify_directory_structure(
    in_project_dir, input_location, output_location, report_location
)

cf = CfClient(cf_controller_address, username, password, verify_ssl)
cf.connect()

tests_to_run = input_dir / run_tests_from_csv
report_header = ""
if len(sys.argv) >1:
    report_header = " ".join(sys.argv[1:])
    print(f"User defined report header: {report_header}")
with open(tests_to_run, "r") as f:
    reader = csv.DictReader(f)
    test_list = list(reader)
# sort tests by run_order column
test_list = sorted(test_list, key=lambda k: int(k["run_order"]))
log.debug(f"test list:\n{test_list}")

detailed_report = DetailedCsvReport(report_dir)

print('*'*100)
print('*'* 40 + 'Running test' + '*'* 40)
print('*'*100)
start_time = time.time()
for test in test_list:
    if test["run"].lower() in {"y", "yes", "true"} and test["suite"].lower() in jenkins.run_test_suites:
        test_key_info = {"name": test["name"], "id": test["id"], "type": test["type"], "load_type": test["load_type"], "goal_seek": test["goal_seek"]}
        print(f"\ntest details:\n{json.dumps(test_key_info, indent=4)}")
        rt = CfRunTest(cf, test, detailed_report, output_dir)
        if rt is not False:
            rt.control_test()
        # create reports
        table = Report(detailed_report.report_csv_file, col_order)
        file_name = detailed_report.report_csv_file.stem
        file_path = detailed_report.report_csv_file.parent
        if file_name.endswith("_Detailed"):
            file_name = file_name[: -len("_Detailed")]
        # create summary csv report with all columns
        csv_name = file_name + "_all"
        csv_report_file = pathlib.Path(file_path / f"{csv_name}.csv")
        print(csv_report_file)
        csv_report(table, csv_report_file)
        # create html report files
        for k, v in html_additional_reports.items():
            new_name = file_name + "_" + k
            report_file = pathlib.Path(file_path / f"{new_name}.html")
            print(report_file)
            html_report(table, report_tables, report_file, v, script_version, report_header)
duration = int(round(time.time() - start_time))
print(f"Run duration totally: {duration}s")
