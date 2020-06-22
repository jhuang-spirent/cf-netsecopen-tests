#!/usr/bin/python3
import sys
import os
import getopt
import time
import csv
import pathlib
import json

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

tests_to_update = input_dir / update_tests_from_csv
test_to_file   = output_dir / get_test_to_file
queue_to_file = output_dir / "queue.json"
device_to_file = output_dir / "device.json"
device_info_to_file = output_dir / "device_info.json"

jenkins.update_test(tests_to_update)
with open(tests_to_update, "r") as f:
    reader = csv.DictReader(f)
    update_test_list = list(reader)
log.debug(f"update test list:\n{update_test_list}")

cf = CfClient(cf_controller_address, username, password, verify_ssl)
cf.connect()

print('*'*100)
print('*'* 40 + 'Updating test' + '*'* 40)
print('*'*100)
for test in update_test_list:
    list_computeGroups = []
    list_systemId = []
    dict_device = []
    found = False
    ready = False
    if test["update"].lower() in {"y", "yes", "true"}:
        print(f"Updating {test['name']} to queue {test['queue']} with {test['device_id']}")  
        queue = cf.get_queue_info(test['queue'], queue_to_file)
        if "Error" in queue or 'type' in queue:
            found = False
        elif test["device_id"] == queue["devices"][0]["id"]:
            found = True 
        response = cf.get_device_list(device_to_file)
        while not found and not ready: 
            ready = True
            dict_device = cf.get_device_info(test["device_id"], device_info_to_file)
            for item in dict_device["slots"][0]["computeGroups"]:
                if item["available"] == False:
                    ready = False
                    print("Sleeping 30 seconds")
                    time.sleep(30)
                    break
        if dict_device == []:
            dict_device = cf.get_device_info(test["device_id"], device_info_to_file)
        for item in dict_device["slots"][0]["computeGroups"]:
            systemId = []
            for port in item["ports"]:
                systemId.append(port["systemId"])
            list_systemId.append(systemId)
            if found == False:
                list_computeGroups.append(item["id"])
        #print(list_computeGroups)
        #print(list_systemId)
        if found == False:     
            queue_to_create = {"name": test["queue"], "computeGroupIds": list_computeGroups}
            response = cf.create_queue(queue_to_create)
        cf.get_test(test["type"], test["id"], test_to_file)
        cf.configure_test_queue(test_to_file, test["queue"])
        response = cf.configure_test_interfaces(test_to_file, list_systemId, test["connection"])
        if response:
            cf.update_test(test["type"], test["id"], test_to_file)
        
    if cf.exception_state:
        pass
    else:
        pass
