import logging
import time
import sys
import os
import re
import pathlib
import subprocess
import csv
import shlex
from datetime import datetime
from shutil import copyfile
from fileinput import FileInput

fmt_str = "[%(asctime)s] %(levelname)s %(lineno)d: %(message)s"

class CIJenkins:
    def __init__(self):
        self.job_name = os.getenv("JOB_NAME")
        self.build_user_id  = os.getenv("BUILD_USER_ID")
        self.result_path = os.getenv("CI_RESULT_PATH")
        self.nso_path = os.getenv("CI_NSO_PATH")
        self.controller_ip = os.getenv("CI_NSO_CONTROLLER")
        self.controller_username = os.getenv("CI_CONTROLLER_USERNAME")
        self.controller_password = os.getenv("CI_CONTROLLER_PASSWORD")
        self.project_name = os.getenv("CI_NSO_PROJECT_NAME")
        self.seed_id = os.getenv("CI_NSO_SEED_ID")
        self.delete_tests = os.getenv("CI_NSO_DELETE_TESTS")
        self.create_tests = os.getenv("CI_NSO_CREATE_TESTS")
        self.update_tests = os.getenv("CI_NSO_UPDATE_TESTS")
        self.run_tests = os.getenv("CI_NSO_RUN_TESTS")
        self.loop_count = os.getenv("CI_NSO_LOOP_COUNT")
        self.update_to_device = os.getenv("CI_NSO_DEVICE")
        self.update_to_connection = os.getenv("CI_NSO_CONNECTION")
        self.test_suite = os.getenv("CI_NSO_TEST_SUITE")
        self.report_header = os.getenv("CI_NSO_REPORT_HEADER")
        if not self.report_header:
            self.report_header = ""
        
        self.controller_ip = "10.71.50.105"
        self.controller_username = "admin@spirent.com"
        self.controller_password = "spirent"

        self.project_name = "http_obj_size_no_multicore"
        self.seed_id = "8bf2b0f31c4ab0cf3f07fda6b614086c"   #ipv4 no multicore
        #self.project_name = "http_obj_size"
        #self.seed_id = "016a3afae26727d37a6fd8c665786b91"   #ipv4 multicore enabled
        self.delete_tests = "false"
        self.create_tests = "false"
        self.update_tests = "false"
        self.run_tests = "true"
        #self.test_suite = "default and nso_mini" #default and nso_mini, default, cisco and nso_mini,  nso_full, default and nso_full
        self.test_suite = "default and nso_full" 
        self.report_header = "by default goal seeking and no multi core on Esxi"
        self.loop_count = 1
         

        if not self.project_name:
            print(f"ERROR: Please specified project name")
            sys.exit(1)
        if not self.loop_count:
            self.loop_count = 1
        self.loop_count = int(self.loop_count)
        self.project_name = self.replace_spec_letters(self.project_name, "_")
        self.spec_dir = os.sep + "CF_" + self.controller_ip + os.sep + self.project_name
        self.input_dir = self.make_input_dir()
        self.cf_config_file = self.make_file_available("cf_config.py")
        self.credentials_file = self.make_file_available("credentials.py")
        self.create_tests_nso_file = self.make_file_available("create_tests_nso.csv")
        self.run_tests_reference_file = self.make_file_available("run_tests_reference.csv")
        self.update_credentials_file()
        self.update_cf_config_file()
        self.get_run_test_suite()
        #print(f"jenkins info: {self.delete_tests}, {self.create_tests}, {self.update_tests}, {self.run_tests}")


    def make_input_dir(self):
        self.project_dir = str(pathlib.Path.cwd())
        input_dir = self.project_dir + os.sep + "input" + self.spec_dir + os.sep
        input_dir = pathlib.Path(input_dir)
        if input_dir.is_dir():
            pass
        else:
            input_dir.mkdir(parents=True, exist_ok=True)
        return str(input_dir)

    def replace_spec_letters(self, input_str, new_letter):
        output_str = input_str.translate ({ord(letter): new_letter for letter in " !@#$%^&*()[]{};:,./<>?\|`~-=_+"})
        output_str = re.sub('_{2,}', '_', output_str)
        output_str = output_str.strip("_")
        return output_str

    def make_file_available(self, filename):
        target_file = self.input_dir + os.sep + filename
        target_file = pathlib.Path(target_file)
        if not target_file.is_file():
            source_file = self.project_dir + "/template/" + filename
            copyfile(source_file, target_file) 
        if target_file.is_file():
            return str(target_file)

    def get_run_test_suite(self):
        if self.test_suite == "default and nso_mini":
            self.run_test_suites = ["default", "nso_mini"] 
        if self.test_suite == "default and nso_full":
            self.run_test_suites = ["default", "nso_mini", "nso"] 
        if self.test_suite == "nso_full":
            self.run_test_suites = ["nso_mini", "nso"] 

    def update_cf_config_file(self):
        input_location  = "input" + self.spec_dir
        report_location = "report" + self.spec_dir
        output_location = "output" + self.spec_dir
        with FileInput(self.cf_config_file, inplace=True) as f:
            for line in f:
                if line.startswith("cf_controller_address"):
                     line = f'cf_controller_address = "{self.controller_ip}"\n'
                if line.startswith("input_location"):
                     line = f'input_location = "{input_location}"\n'
                if line.startswith("report_location"):
                     line = f'report_location = "{report_location}"\n'
                if line.startswith("output_location"):
                     line = f'output_location = "{output_location}"\n'
                if line.startswith("create_tests_base_test_id"):
                     line = f"create_tests_base_test_id = '{self.seed_id}'\n"
                print(line, end='')
        return True

    def update_credentials_file(self):
        with FileInput(self.credentials_file, inplace=True) as f:
            for line in f:
                if line.startswith("username"):
                     line = f"username = '{self.controller_username}'\n"
                if line.startswith("password"):
                     line = f"password = '{self.controller_password}'\n"
                print(line, end='')
        return True

    def update_test(self, filename):
        with open(filename, "r") as f:
            reader = csv.DictReader(f)
            update_test_list = list(reader)
        if update_test_list:
            for test in update_test_list:
                test["queue"] = "_".join(self.update_to_device.rsplit(".", 2)[1:3])
                test["device_id"] = self.update_to_device
                test["connection"] = self.update_to_connection
        else:
            print(f"There is no test in {filename}")
            return False
        with open(filename, 'w') as f:
            writer = csv.DictWriter(f, update_test_list[0].keys())
            writer.writeheader()
            for test in update_test_list:
                writer.writerow(test)
        f.close()


    @staticmethod
    def run_command(command): 
        command = ['/usr/bin/python3','-u'] + shlex.split(command)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=1)
        while True:
            output = process.stdout.readline()
            output = output.strip().decode()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output, flush = True)
        rc = process.poll()
        return rc
