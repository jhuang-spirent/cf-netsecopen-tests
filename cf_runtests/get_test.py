#!/usr/bin/python3
import pathlib
import json
import sys

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

if len(sys.argv) >1:
    get_test_type = sys.argv[1]
    get_test_id = sys.argv[2]

response = cf.get_test(get_test_type, get_test_id, output_dir / get_test_to_file)
if cf.exception_state:
    print(f"\nSaved to file: {get_test_to_file} \n{json.dumps(response, indent=4)}")
else:
    print(f"Unable to save test id: {get_test_id} with test type: {get_test_type}")
