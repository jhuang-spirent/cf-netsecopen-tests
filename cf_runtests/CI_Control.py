#!/usr/bin/python3
import logging
import pathlib
import sys
import subprocess

current_dir = pathlib.Path().absolute()
project_dir = current_dir.parent
sys.path.append(str(project_dir))

from cf_common.CIJenkins import *
from cf_common.cf_functions import *
jenkins = CIJenkins()
 
if jenkins.delete_tests == "true":
    command = "./delete_created_tests.py"
    jenkins.run_command(command)
if jenkins.create_tests == "true":
    command = "./create_tests.py"
    jenkins.run_command(command)
if jenkins.update_tests == "true":
    command = "./update_tests.py"
    jenkins.run_command(command)
if jenkins.run_tests == "true":
    for i in range(0, jenkins.loop_count):
        command = f"./run_tests.py {jenkins.report_header}"
        jenkins.run_command(command)

