#!/usr/bin/python3
import pathlib
import sys
import random
import string

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
from cf_common.CfCreateTest import *

if (pathlib.Path.cwd() / "dev_settings.py").is_file():
    from cf_runtests.dev_settings import *

input_dir, output_dir, report_dir = verify_directory_structure(
    in_project_dir, input_location, output_location, report_location
)

cf = CfClient(cf_controller_address, username, password, verify_ssl)
cf.connect()
log.info("Connected to controller")

create_tests_base_file = output_dir / create_tests_base_file
create_test_source_csv = input_dir / create_test_source_csv
create_tests_output_list_csv = output_dir / create_tests_output_list_csv

# get base test from controller and save to file
print(f"Using {create_tests_base_test_id} to create tests")
cf.get_test(create_tests_base_type, create_tests_base_test_id, create_tests_base_file)

# load base test from file
with open(create_tests_base_file) as infile:
    base = json.load(infile)
# bt = base test class instance
project_info = cf.get_project(base["projectId"], output_dir / "project.json")
test_list = get_testid_in_project(project_info)
if match_nso_test(test_list, create_tests_output_list_csv):
    print("ERROR: Cannot create new NSO tests which have been created before")
    sys.exit(1) 

bt = BaseTest(base)
with open(create_test_source_csv, "r") as f:
    reader = csv.DictReader(f)
    test_list = list(reader)
# print(f'\ntest_list\n{json.dumps(test_list, indent=4)}')

# create tests to run csv file
reference_to_run_csv_file = input_dir / reference_to_run_csv_file
test_to_run_csv_file = input_dir / test_to_run_csv_file
test_to_update_csv_file = input_dir / test_to_update_csv_file

# check CyberFlood version
cf_ver = cf.get_system_version()
print(f"CyberFlood controller version: {cf_ver['version']}")
log.debug(f"\nCyberFlood version response\n{json.dumps(cf_ver, indent=4)}")
log.debug(f"CyberFlood controller version: {cf_ver['version']}")

# set test name suffix to be used if input sheet is not set to "auto"
chars = 3
suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=chars))

order = 0
update = "Y"
print('*'*100)
print('*'* 40 + 'Creating test' + '*'* 40)
print('*'*100)
for test in test_list:
    if test["include"].lower() in {"y", "yes"}:
        #print(f"creating test: {json.dumps(test, indent=4)}")
        print(f" - Creating test: ", end='')
        # load test template from controller
        test_template = cf.fetch_test_template(
            test["type"], output_dir / "template_last_created.json"
        )
        log.debug(f"\nTemplate response\n{json.dumps(test_template, indent=4)}")
        # instantiate new test
        if test["name_suffix"] == "auto":
            test["name_suffix"] = suffix
        if "ipv6" in test["name"].lower():
            subnet_count = len(base["config"]["subnets"]["client"])
            ipv6_subnet = cf.get_CI_ipv6_subnet(subnet_count, output_dir / "ipv6_subnet.json")
            base["config"]["subnets"] = ipv6_subnet
        new = CfCreateTest(base, test, test_template, cf_ver["version"])
        new.update_config_changes()
        last_created_test = output_dir / "last_created_test.json"
        new.save_test(last_created_test)

        response = cf.post_test(test["type"], last_created_test)
        log.debug(f"\nPost response\n{json.dumps(response, indent=4)}")
        if "type" in response:
            if response["type"] == "validation":
                print(json.dumps(response, indent=4))
                sys.exit(1)
        order = order + 1
        if order == 1:
            with open(create_tests_output_list_csv, "w") as f:
                created_tests = f"id,type,name"
                f.write(created_tests)
            run_tests = TestsToRun(reference_to_run_csv_file, test_to_run_csv_file)
            update_tests = TestsToUpdate(test_to_update_csv_file)
        run_tests.add_test(response, test["type"])
        test_info = f"\n{response['id']},{test['type']},{response['name']}"
        print(f"{test_info}")
        with open(create_tests_output_list_csv, "a") as f:
            f.write(test_info)
        # for update tests csv
        queue = new.queue["id"]
        client_port1 = new.interfaces["client"][0]["portSystemId"]
        server_port1 = new.interfaces["server"][0]["portSystemId"]
        device = client_port1.split("/",1)[0]
        slots = [int(client_port1.rsplit("/",1)[-1]), int(server_port1.rsplit("/",1)[-1])] 
        if slots[1] - slots[0] == 1:
            connection = "p2p"
        else:
            connection = "c2c"
        update_tests.add_test(response, test["type"], update, order, queue, device, connection)
backup_file(test_to_run_csv_file)
backup_file(test_to_update_csv_file)
backup_file(create_tests_output_list_csv)
