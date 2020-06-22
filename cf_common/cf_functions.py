import pathlib
import sys
import importlib
import os
import csv
from datetime import datetime
from shutil import copyfile


def add_sys_path(dirName):
    if type(dirName) == str:
        dirName = pathlib.Path(dirName)
    if dirName.is_dir():
        sys.path.append(str(dirName))
    else:
        print(f"{dirName} does not exist")
        return False
    return True


def loadModule(moduleName):
    module = None
    try:
        del sys.modules[moduleName]
    except BaseException as err:
        pass
    try:
        module = importlib.import_module(moduleName)
    except BaseException as err:
        serr = str(err)
        print("Error to load the module '" + moduleName + "': " + serr)
    return module
 
def rm_file(filename):
    filename = str(filename)
    if os.path.isfile(filename):
        os.remove(filename)
    else:    ## Show an error ##
        print(f"Error: {filename} not found")

def backup_file(filename):
    filename = str(filename)
    if os.path.isfile(filename):
        path = filename.rsplit(os.sep,1)[0]
        name = filename.rsplit(os.sep,1)[1]
        backup_file = name + "_" + datetime.fromtimestamp(os.path.getctime(filename)).strftime("%Y%m%d%H%M")
        backup_path = path + os.sep + "backup"
        if not os.path.isdir(backup_path):
            os.mkdir(backup_path)
        full_backup_file = backup_path + os.sep + backup_file
        copyfile(filename, full_backup_file)
        #print(f"backing up {name} to {backup_file}")
    else:    ## Show an error ##
        print(f"Error: {filename} not found")

def delete_test(test_id_list, filename):
    new_list = []
    with open(filename, "r") as f:
        reader = csv.DictReader(f)
        test_list = list(reader)
    if test_list:
        for test in test_list:
            if test['id'] not in test_id_list:
                new_list.append(test)    
    with open(filename, 'w') as f:
        if test_list:
            writer = csv.DictWriter(f, test_list[0].keys())
            writer.writeheader()
            if new_list:
                for test in new_list: 
                    writer.writerow(test)
    f.close()

def get_testid_in_project(project):
    test_id_list = []
    for test in project["tests"]:
        test_id_list.append(test["id"])
    return test_id_list
    
def match_nso_test(test_id_list, filename):
    found = False
    test_list = []
    if filename.is_file():
        with open(filename, "r") as f:
            reader = csv.DictReader(f)
            test_list = list(reader)
    if test_list and test_id_list:
        for test in test_list:
            if test['id'] in test_id_list:
                found = True
                break
    return found  

def verify_directory_structure(bool_project_dir, input_dir, output_dir, report_dir):
    # parent.parent assumes this function is in a sub directory of the main project
    # project_root_dir = pathlib.Path(__file__).parent.parent
    project_dir = pathlib.Path.cwd()
    if bool_project_dir:
        input_dir = project_dir / input_dir
        output_dir = project_dir / output_dir
        report_dir = project_dir / report_dir
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
    else:
        input_dir = pathlib.Path(input_dir)
        output_dir = pathlib.Path(output_dir)
        report_dir = pathlib.Path(report_dir)
    if not input_dir.is_dir():
        print(f"input_dir does not exist: {input_dir}")
    if not output_dir.is_dir():
        print(f"output_dir does not exist: {output_dir}")
    if not report_dir.is_dir():
        print(f"report_dir does not exist: {report_dir}")
    return input_dir, output_dir, report_dir


def html_report(df_table, sub_report_tables, html_report_file, filter_columns,
                script_version, report_header=""):
    html = ""
    report_header_html = f"<h2 style='color:Tomato;'>{report_header}</h2>"
    html = html + report_header_html

    for sub_table in sub_report_tables:
        df_table.reset_df_filter()
        df_table.filter_rows_containing(sub_table)
        df_table.filter_columns(filter_columns)
        # check if there are results in a table before adding it to the html file
        if not len(df_table.df_filter.index) == 0:
            if sub_table is None:
                table_filter = f"<h3>ALL TESTS - including above tests</h3>"
            else:
                table_filter = f"<h3>{sub_table}</h3>"
            html = html + table_filter + df_table.html_table(df_table.style_a())

    script_version_html = f"\n<body>" \
                          f"\n<p>Script version: {script_version}</p>" \
                          f"\n</body>"

    html = html + script_version_html

    with open(html_report_file, "w") as f:
        f.write(html)


def csv_report(df_table, csv_report_file):
    df_table.reset_df_filter()
    df_table.df_filter.to_csv(csv_report_file, index=False)


# def dut_refresh()
#     # A test run has ended at this point, either successfully or not.
#     # Perform DUT refresh and/or file transfers, if required.
#     dut_refresh_settings = current_test.dut_refresh
#     retrieve_files_settings = current_test.retrieve_files
#     if dut_refresh_settings["required"] or retrieve_files_settings["required"]:
#         from ssh_access import dut_refresh, file_transfer
#         time.sleep(4)
#         print()
#
#         if retrieve_files_settings["required"]:
#             # if file transfer is required for this test, run the function.
#             if not file_transfer(retrieve_files_settings["ip_address"], retrieve_files_settings["username"],
#                                  retrieve_files_settings["password"], retrieve_files_settings["remote_path"],
#                                  retrieve_files_settings["local_path"]):
#                 log.error("File transfer failed to perform.")
#
#         if dut_refresh_settings["required"]:
#             # if dut_refresh is required for this test, run the function.
#             if not dut_refresh(dut_refresh_settings["ip_address"], dut_refresh_settings["username"],
#                                dut_refresh_settings["password"],
#                                dut_refresh_settings["commands_to_execute"],
#                                dut_refresh_settings["optional_wait_time"]):
#                 log.error("DUT refresh required but failed to perform.")
