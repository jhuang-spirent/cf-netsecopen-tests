#!/usr/bin/python3
import csv
import pathlib
import sys
import os

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

if (pathlib.Path.cwd() / "dev_settings.py").is_file():
    from cf_runtests.dev_settings import *

input_dir, output_dir, report_dir = verify_directory_structure(
    in_project_dir, input_location, output_location, report_location
)

cf = CfClient(cf_controller_address, username, password, verify_ssl)
cf.connect()

delete_test_list_csv = output_dir / delete_tests_csv
test_to_update_csv_file = input_dir / test_to_update_csv_file
test_to_run_csv_file = input_dir / test_to_run_csv_file

with open(delete_test_list_csv, "r") as f:
    reader = csv.DictReader(f)
    test_list = list(reader)
print(f"\ntest_list\n{json.dumps(test_list, indent=4)}")

deleted_test_list = []
print('*'*100)
print('*'* 40 + 'Deleting test' + '*'* 40)
print('*'*100)
for test in test_list:
    last_deleted_test = output_dir / "last_deleted_test.json"
    print(f"checking if test exists: {test['id']}  {test['name']}")
    response = cf.get_test(test["type"], test["id"], last_deleted_test)
    if "id" in response:
        print(f"test exists, attempting to delete: {test['id']}  {test['name']}")
        # print(f'\nTest to delete:\n{json.dumps(response, indent=4)}')
        response = cf.delete_test(test["type"], test["id"])
        if response.status_code == 204:
            print(f"test successfully deleted: {test['id']}  {test['name']}")
            deleted_test_list.append(test['id'])
        else:
            print(f"Test may not have been deleted: {response}")
    else:
        print(f"\nunable to delete test: {test['id']}  {test['name']}\n")
delete_test(deleted_test_list, test_to_update_csv_file)
delete_test(deleted_test_list, test_to_run_csv_file)
delete_test(deleted_test_list, delete_test_list_csv)
