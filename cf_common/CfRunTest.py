#!/usr/bin/python3
import json
import logging
import time
import sys
import os
import numpy as np
import pandas as pd
import pathlib
import sys
import math
from shutil import move

script_version = 1.79

project_dir = pathlib.Path().absolute().parent
sys.path.append(str(project_dir))

from cf_common.CfClient import *


class RollingStats:
    """Creates rolling window statistics object

    Inputs are sample window size and number of digits to round values too.
    For example:
    - transactions per second window size can be 2 or higher with 0 round digits
    - time to first byte can have 1 round digit, best is to use the same window size
    """

    def __init__(self, sample_window_size, round_digits):
        # initiate list with sample size count of zeros
        self.sample_size = sample_window_size
        self.round_digits = round_digits
        self.list = [0] * self.sample_size
        self.current_value = 0
        self.avg_val = 0
        self.avg_val_last = 0
        self.increase_avg = 0
        self.variance = 0.000
        self.avg_max_variance = 0.00
        self.new_high = False
        self.highest_value = 0
        self.not_high_count = 0
        self.stable = False
        self.stable_count = 0
        self.unstable_count = 0
        self.no_positive_increase_count = 0

    def update(self, new_value):
        """Updates Rolling List and returns current variance

        :param new_value: new single value of for example TPS or TTFB
        :return: variance
        """
        self.current_value = new_value
        if len(self.list) == self.sample_size:
            self.list.pop(0)
        self.list.append(self.current_value)
        self.avg_val = sum(self.list) / len(self.list)
        self.avg_val = round(self.avg_val, self.round_digits)
        if self.round_digits == 0:
            self.avg_val = int(self.avg_val)
        max_var = max(self.list) - min(self.list)
        self.variance = (max_var / self.avg_val) if self.avg_val != 0 else 0
        self.variance = round(self.variance, 3)
        # check if new value value is the new high for later use
        self.check_if_highest()
        return self.variance

    def reset(self):
        """Resets rolling window back to all 0

        Can be used after load increase on stat as current load that tracks if load is stable after increase
        Don't use on reported rolling stat as it will have high increase after its set to all 0

        :return: None
        """
        self.list = [0] * self.sample_size

    def reset_count(self):
        #print(f"reset unstable_count and no_positive_increase_count back to all 0")
        self.unstable_count = 0
        self.no_positive_increase_count = 0

    def check_if_stable(self, max_var_reference):
        """Checks if load is stable in current list

        If its stable also check the increase since a load change was last completed.

        :param max_var_reference: user/test configured reference value, e.g. 0.03 for 3%
        :return: True if stable, False if not
        """
        self.increase_since_last_load_change()
        if self.variance <= max_var_reference:
            self.stable = True
            self.stable_count += 1
            return True
        else:
            self.stable = False
            self.stable_count = 0
            self.unstable_count += 1
            return False

    def increase_since_last_load_change(self):
        """Sets increase_avg, the increase since last load

        This function can be called from check_if_stable. The set result can be used by a function to
        determine by how much to increase the load. After load change call load_increase_complete to
        set the value for the next round.
        :return: None
        """
        if self.avg_val_last != 0:
            self.increase_avg = (
                (self.avg_val - self.avg_val_last) / self.avg_val_last
            ) * 100
            self.increase_avg = round(self.increase_avg, 2)
            if self.increase_avg <= 0:
                self.no_positive_increase_count += 1
        else:
            self.avg_val_last = 1

    def load_increase_complete(self):
        """set last load change value

        Use in combination with increase_since_last_load_change

        :return: None
        """
        self.avg_val_last = self.avg_val

    def check_if_highest(self):
        """Checks and sets highest value reference

        Can be called by update function to track if the current update is the new highest value

        :return: True if new high, False if not higher vs. previous
        """
        if self.highest_value < self.avg_val:
            self.highest_value = self.avg_val
            self.new_high = True
            self.not_high_count = 0
        else:
            self.new_high = False
            self.not_high_count += 1

        self.avg_max_variance = (
            (self.avg_val / self.highest_value) if self.highest_value != 0 else 0
        )
        self.avg_max_variance = round(self.avg_max_variance, 2)

        if self.new_high:
            return True
        if not self.new_high:
            return False


class CfRunTest:
    def __init__(self, cf, test_details, result_file, temp_file_dir):
        log.info(f"script version: {script_version}")
        self.cf = cf  # CfClient instance
        self.result_file = result_file
        self.temp_dir = temp_file_dir
        self.test_id = test_details["id"]
        self.type_v2 = test_details["type"]
        self.in_name = test_details["name"]
        self.in_run = test_details["run"]
        self.in_load_type = test_details["load_type"]
        self.in_start_load = test_details["start_load"]
        self.in_incr_low = int(test_details["incr_low"])
        self.in_incr_med = int(test_details["incr_med"])
        self.in_incr_high = int(test_details["incr_high"])
        self.in_duration = int(test_details["duration"])
        self.in_startup = int(test_details["startup"])
        self.in_rampup = int(test_details["rampup"])
        self.in_rampdown = int(test_details["rampdown"])
        self.in_shutdown = int(test_details["shutdown"])
        self.in_sustain_period = int(test_details["sustain_period"])
        self.in_kpi_1 = test_details.get("kpi_1", "tps")
        self.in_kpi_2 = test_details.get("kpi_2", "cps")
        self.in_kpi_and_or = self.return_bool_true(test_details.get("kpi_and_or"), "AND")
        self.in_threshold_low = float(test_details["low_threshold"])
        self.in_threshold_med = float(test_details["med_threshold"])
        self.in_threshold_high = float(test_details["high_threshold"])
        self.in_sustain_period = int(test_details["sustain_period"])
        self.variance_sample_size = int(test_details["variance_sample_size"])
        self.in_max_variance = float(test_details["max_variance"])
        self.in_ramp_low = int(test_details.get("ramp_low", 60))
        self.in_ramp_med = int(test_details.get("ramp_med", 40))
        self.in_ramp_high = int(test_details.get("ramp_high", 20))

        self.in_ramp_seek = self.if_in_set_true(test_details, "ramp_seek",
                                                {"true", "y", "yes"})
        self.in_ramp_seek_kpi = test_details.get("ramp_kpi", "tps")
        self.in_ramp_seek_value = int(test_details.get("ramp_value", 1))
        self.in_ramp_step = int(test_details.get("ramp_step", 1))
        if not self.in_ramp_seek:
            self.ramp_seek_complete = True
        else:
            self.ramp_seek_complete = False

        self.living_simusers_max_bool = self.check_if_number(
            test_details.get("living_simusers_max", False))
        self.living_simusers_max = self.return_int_if_present(
            self.living_simusers_max_bool,
            test_details.get("living_simusers_max", False))

        self.in_goal_seek = False
        self.first_steady_interval = True
        self.in_goal_seek = test_details["goal_seek"]
        if self.in_goal_seek.lower() in {"true", "y", "yes"}:
            self.in_goal_seek = True
            self.first_steady_interval = False
        else:
            self.in_goal_seek = False

        self.test_config = self.get_test_config()
        self.test_suite = test_details["suite"]
        self.goal_seek_count = 0
        self.goal_seek_count_after_max_load = 0
        self.c_current_load_startup = 0
        self.c_memory_main_used_startup = 0
        self.s_memory_main_used_startup = 0
        self.c_memory_one_connection = 0
        self.ttfb_threshold = int(100)
        self.pkt_memory_threshold = int(2500)
        self.speed_capacity_adjust = 1.2
        self.count_load_adjust_low = 1.2
        self.count_load_adjust_high = 1.5
        self.count_load_adjust_emix = 1.5
        self.new_load_list = []
        self.load_increase_list = []
        self.highest_pair = {"highest_tps": 0, "highest_load": 0, "highest_desired_load": 0, "highest_bw": 0, "highest_cps": 0, "highest_conns": 0}
        self.queue_id = self.test_config["config"]["queue"]["id"]
        self.get_queue_keyinfo()
        (report_dir, report_name) = self.get_report_info()
        self.result_file.make_report_dir(report_dir)
        self.result_file.make_report_csv_file(report_name)
        self.get_response_length()
        self.client_ports = []
        self.server_ports = []
        self.subnet_number = len(self.test_config["config"]["interfaces"]["client"])
        for i in range(0, self.subnet_number):
            self.client_ports.append(self.test_config["config"]["interfaces"]["client"][i]["portSystemId"])
            self.server_ports.append(self.test_config["config"]["interfaces"]["server"][i]["portSystemId"])
        print(f"Client ports: {self.client_ports}")
        print(f"Server ports: {self.server_ports}")
        #self.queue_info = self.get_queue(self.queue_id)
        #self.queue_capacity = int(self.queue_info["capacity"])
        log.info(f"queue_capacity: {self.queue_capacity}")
        #self.core_count = self.core_count_lookup(self.queue_info)
        #log.info(f"core_count: {self.core_count}")
        self.client_port_count = len(self.test_config["config"]["interfaces"]["client"])
        log.info(f"client_port_count: {self.client_port_count}")
        self.server_port_count = len(self.test_config["config"]["interfaces"]["server"])
        log.info(f"server_port_count: {self.server_port_count}")
        #self.client_core_count = int(
        #    self.core_count
        #    / (self.client_port_count + self.server_port_count)
        #    * self.client_port_count
        #)
        log.info(f"client_core_count: {self.client_core_count}")
        self.in_capacity_adjust = self.check_capacity_adjust(
            test_details["capacity_adj"],
            self.in_load_type,
            self.client_port_count,
            self.client_core_count,
        )
        self.load_constraints = {"enabled": False}
        if not self.update_config_load():
            report_error = f"unknown load_type with test type"
            log.debug(report_error)
            print(report_error)
        print(f"in_capacity_adjust: {self.in_capacity_adjust}")
        log.info(f"in_capacity_adjust: {self.in_capacity_adjust}")
        self.test_config = self.get_test_config()

        self.test_run = self.start_test_run()
        if not self.test_started:
            report_error = f"test did not start\n{json.dumps(self.test_run, indent=4)}"
            log.debug(report_error)
            print(report_error)
        self.test_run_update = None

        self.id = self.test_run.get("id")
        self.queue_id = self.test_run.get("queueId")
        self.score = self.test_run.get("score")
        self.grade = self.test_run.get("grade")
        self.run_id = self.test_run.get("runId")
        self.status = self.test_run.get("status")  # main run status 'running'
        self.name = self.test_run.get("test", {}).get("name")
        self.type_v1 = self.test_run.get("test", {}).get("type")
        self.sub_status = self.test_run.get("subStatus")
        self.created_at = self.test_run.get("createdAt")
        self.updated_at = self.test_run.get("updatedAt")
        self.started_at = self.test_run.get("startedAt")
        self.finished_at = self.test_run.get("finishedAt")
        self.progress = self.test_run.get("progress")
        self.time_elapsed = self.test_run.get("timeElapsed")
        self.time_remaining = self.test_run.get("timeRemaining")

        self.run_link = (
            "https://"
            + self.cf.controller_ip
            + "/#livecharts/"
            + self.type_v1
            + "/"
            + self.id
        )
        print(f"Live charts: {self.run_link}")

        self.report_link = None
        self.sub_status = None  # subStatus -  none while running or not started
        self.progress = 0  # progress  -  0-100
        self.time_elapsed = 0  # timeElapsed  - seconds
        self.time_remaining = 0  # timeRemaining  - seconds
        self.started_at = None  # startedAt
        self.finished_at = None  # finishedAt

        self.c_rx_bandwidth = 0
        self.c_rx_packet_count = 0
        self.c_rx_packet_rate = 0
        self.c_tx_bandwidth = 0
        self.c_tx_packet_count = 0
        self.c_tx_packet_rate = 0
        self.c_http_aborted_txns = 0
        self.c_http_aborted_txns_sec = 0
        self.c_http_attempted_txns = 0
        self.c_http_attempted_txns_sec = 0
        self.c_http_successful_txns = 0
        self.c_http_successful_txns_sec = 0
        self.c_http_unsuccessful_txns = 0
        self.c_http_unsuccessful_txns_sec = 0
        self.c_loadspec_avg_idle = 0
        self.c_loadspec_avg_cpu = 0
        self.c_memory_main_size = 0
        self.c_memory_main_used = 0
        self.c_memory_packetmem_used = 0
        self.c_memory_rcv_queue_length = 0
        self.c_simusers_alive = 0
        self.c_simusers_animating = 0
        self.c_simusers_blocking = 0
        self.c_simusers_sleeping = 0
        self.c_tcp_avg_ttfb = 0
        self.c_tcp_avg_tt_synack = 0
        self.c_tcp_cumulative_attempted_conns = 0
        self.c_tcp_cumulative_established_conns = 0
        self.c_url_avg_response_time = 0
        self.c_tcp_attempted_conn_rate = 0
        self.c_tcp_established_conn_rate = 0
        self.c_tcp_attempted_conns = 0
        self.c_tcp_established_conns = 0
        self.c_current_load = 0
        self.c_desired_load = 0
        self.c_total_bandwidth = 0
        self.c_memory_percent_used = 0
        self.c_current_desired_load_variance = 0.0
        self.c_current_max_load_variance = 0.0
        self.c_transaction_error_percentage = 0.0

        self.s_rx_bandwidth = 0
        self.s_rx_packet_count = 0
        self.s_rx_packet_rate = 0
        self.s_tx_bandwidth = 0
        self.s_tx_packet_count = 0
        self.s_tx_packet_rate = 0
        self.s_memory_main_size = 0
        self.s_memory_main_used = 0
        self.s_memory_packetmem_used = 0
        self.s_memory_rcv_queue_length = 0
        self.s_memory_avg_cpu = 0
        self.s_tcp_closed_error = 0
        self.s_tcp_closed = 0
        self.s_tcp_closed_reset = 0
        self.s_memory_percent_used = 0

        self.first_ramp_load_increase = True
        self.first_goal_load_increase = True
        self.max_load_reached = False
        self.max_load = 0
        self.stop = False  # test loop control
        self.phase = None  # time phase of test: ramp up, steady ramp down

        # rolling statistics
        self.rolling_sample_size = self.variance_sample_size
        self.max_var_reference = self.in_max_variance
        self.rolling_tps = RollingStats(self.rolling_sample_size, 0)
        self.rolling_ttfb = RollingStats(self.rolling_sample_size, 1)
        self.rolling_load = RollingStats(self.rolling_sample_size, 0)
        self.rolling_count_since_goal_seek = RollingStats(
            self.rolling_sample_size, 1
        )  # round to 1 for > 0 avg
        self.rolling_cps = RollingStats(self.rolling_sample_size, 0)
        self.rolling_conns = RollingStats(self.rolling_sample_size, 0)
        self.rolling_bw = RollingStats(self.rolling_sample_size, 0)

        self.kpi_1 = self.rolling_tps
        self.kpi_2 = self.rolling_cps
        self.kpi_1_stable = True
        self.kpi_2_stable = True
        self.kpi_1_list = []
        self.kpi_2_list = []
        self.ramp_seek_kpi = self.rolling_tps

        self.start_time = time.time()
        self.timer = time.time() - self.start_time
        self.time_to_run = 0
        self.time_to_start = 0
        self.time_to_activity = 0
        self.time_to_stop_start = 0
        self.time_to_stop = 0
        self.test_started = False

        # create entry in result file at the start of test
        self.save_results()

    @staticmethod
    def if_in_set_true(dict_var, dict_key, in_set):
        if dict_key in dict_var:
            var = dict_var[dict_key]
            if var.lower() in in_set:
                return True
        return False

    @staticmethod
    def check_if_number(in_value):
        if isinstance(in_value, int) or isinstance(in_value, float):
            return True
        if isinstance(in_value, str):
            if in_value.isdigit():
                return True
        return False

    @staticmethod
    def return_int_if_present(present, value):
        if present:
            return int(value)

    def get_test_config(self):
        try:
            response = self.cf.get_test(
                self.type_v2, self.test_id, self.temp_dir / "running_test_config.json"
            )
            log.debug(f"{json.dumps(response, indent=4)}")
        except Exception as detailed_exception:
            log.error(
                f"Exception occurred when retrieving the test: "
                f"\n<{detailed_exception}>"
            )
        return response

    def get_queue(self, queue_id):
        try:
            response = self.cf.get_queue(queue_id)
            log.debug(f"{json.dumps(response, indent=4)}")
        except Exception as detailed_exception:
            log.error(
                f"Exception occurred when retrieving test queue informationn: "
                f"\n<{detailed_exception}>"
            )
        return response

    def get_queue_keyinfo(self):
        self.queue_speed = int(0)
        self.client_core_count = int(0)
        self.queue_capacity = int(0)
        self.portSystemId = []
        self.queue_id = self.test_config["config"]["queue"]["id"]
        self.subnet_number = len(self.test_config["config"]["interfaces"]["client"])
        for i in range(0, self.subnet_number):
            self.portSystemId.append(self.test_config["config"]["interfaces"]["client"][i]["portSystemId"])
        self.device_id = self.portSystemId[0].split("/", 1)[0]
        self.device_info = self.cf.get_device_info(self.device_id, self.temp_dir / "device_info.json")
        for computeGroup in self.device_info["slots"][0]["computeGroups"]:
            for port in computeGroup["ports"]:
                if port["systemId"] in self.portSystemId:
                    self.queue_speed = self.queue_speed + int(port["speed"])
                    self.client_core_count = self.client_core_count + int(port["cores"])
                    self.queue_capacity = self.queue_capacity + int(port["capacity"])
        print(f"Client speed: {self.queue_speed/1000}G")
        print(f"Client cores: {self.client_core_count}")
        
    def get_report_info(self):
        self.device_mode = ""
        self.device_ip = self.device_info["ip"]
        self.device_description = self.device_info["description"][4:]
        self.device_firmware = self.device_info["firmware"]["version"]
        self.device_profile = self.device_info["slots"][0]["profile"]
        for profile_info in ["Functional-", "Performance-", "Maximum-"]:
            if profile_info in self.device_profile:
                self.device_profile = self.device_profile.split(profile_info)[-1].strip("\n")
                break
        if self.device_description == "CFV":
            self.device_model = self.device_info["slots"][0]["model"][8:-5]
            report_dir_info = (self.device_description, self.device_model)
        else:
            report_dir_info = (self.device_description, self.device_profile)
        report_name_info = (self.device_ip, self.device_firmware)
        report_dir = "-".join(report_dir_info)
        report_name = "_".join(report_name_info)
        return (report_dir, report_name)

    def get_response_length(self):
        self.response_length = 987654321
        if "protocol" in self.test_config["config"]:
            if "responseBodyType" in self.test_config["config"]["protocol"]:
                self.response_config = self.test_config["config"]["protocol"]["responseBodyType"]["config"]
                if "length" in self.response_config:
                    self.response_length = self.response_config["length"]
                if "bytes" in self.response_config:
                    self.response_length = self.response_config["bytes"]

    @staticmethod
    def core_count_lookup(queue_info):
        cores = 0
        for cg in queue_info["computeGroups"]:
            cores = cores + int(cg["cores"])
        return cores

    @staticmethod
    def check_capacity_adjust(
        cap_adjust, load_type, client_port_count, client_core_count
    ):
        if cap_adjust.lower() == "auto":
            if load_type.lower() in {"simusers", "simusers/second"}:
                return client_core_count
            else:
                return client_port_count
        else:
            return int(cap_adjust)

    def update_config_load(self):
        load_type = self.in_load_type.lower()
        test_type = self.test_type()

        self.minimal_load_spec_change = 1
        if test_type in {"tput", "emix"} and load_type == "simusers":
            self.load_key = "bandwidth"
            self.in_load_type = "SimUsers"
        elif test_type in {"tput", "emix"} and load_type == "bandwidth":
            self.load_key = "bandwidth"
            self.in_load_type = "Bandwidth"
            self.minimal_load_spec_change = 5000
        elif test_type in {"tput", "emix"} and load_type == "simusers/second":
            self.load_key = "bandwidth"
            self.in_load_type = "SimUsers/Second"
            if self.response_length <= 1000:
                self.minimal_load_spec_change = 8
        elif test_type == "cps" and load_type == "connections/second":
            self.load_key = "connectionsPerSecond"
            self.in_load_type = "Connections/Second"
            self.minimal_load_spec_change = 100
        elif test_type == "cps" and load_type == "simusers":
            self.load_key = "connectionsPerSecond"
            self.in_load_type = "SimUsers"
        elif test_type == "cps" and load_type == "simusers/second":
            self.load_key = "connectionsPerSecond"
            self.in_load_type = "SimUsers/Second"
            self.minimal_load_spec_change = 200
        elif test_type == "conns" and load_type == "simusers":
            self.load_key = "connections"
            self.in_load_type = "SimUsers"
            self.minimal_load_spec_change = 100
        elif test_type == "conns" and load_type == "connections":
            self.load_key = "connections"
            self.in_load_type = "Connections"
            self.minimal_load_spec_change = 500
        elif self.test_type == "conns" and load_type == "simusers/second":
            self.load_key = "connections"
            self.in_load_type = "SimUsers/Second"
            self.minimal_load_spec_change = 10
        elif self.test_type == "max_cps":
            self.load_key = "connectionsPerSecond"
        elif self.test_type == "max_tput":
            self.load_key = "bidirectionalBandwidth"
        elif self.test_type == "ddos":
            self.load_key = "bandwidth"
            self.in_start_load = int(self.queue_speed * 1000)
        else:
            return False

        if self.test_suite == "default":
          if self.test_type in ["ddos", "max_cps", "max_tput"]:
            self.in_load_type = ""
            self.in_goal_seek = False
            self.in_duration = 300
            self.in_rampup = 120
            self.in_rampdown = 0 
            self.in_shutdown = 32 
          else:
            if self.response_length <= 4000:
                self.in_capacity_adjust = self.round_up_to_core(16, self.client_core_count)
            elif self.response_length <= 16000:
                self.in_capacity_adjust = self.round_up_to_core(8, self.client_core_count)
            elif self.response_length <= 32000:
                self.in_capacity_adjust = self.round_up_to_core(4, self.client_core_count)
            else:
                self.in_capacity_adjust = self.round_up_to_core(3, self.client_core_count)
            self.in_start_load = int(self.in_start_load) * self.client_core_count
            if self.in_start_load <= 16:
                self.in_start_load = self.round_up_to_core(16, self.client_core_count) 
        else:
            self.in_start_load = int(self.in_start_load) * self.in_capacity_adjust
            self.update_load_constraints()
        self.update_load_specification()
        self.update_runtime_options()
        load_update = {
            "config": {
                "runtimeOptions": self.runtime_options,
                "loadSpecification": self.load_specification,
                }
              }
        with open(self.temp_dir / "test_load_update.json", "w") as f:
            json.dump(load_update, f, indent=4)

        response = self.cf.update_test(
            self.type_v2, self.test_id, self.temp_dir / "test_load_update.json"
        )

        log.info(f"{json.dumps(response, indent=4)}")
        return True

    def update_load_constraints(self):
        living = {"enabled": False}
        open_connections = {"enabled": False}
        birth_rate = {"enabled": False}
        connections_rate = {"enabled": False}
        constraints = False

        if self.living_simusers_max_bool:
            constraints = True
            living = {
                "enabled": True,
                "max": self.living_simusers_max
            }
        if constraints:
            self.load_constraints = {
                "enabled": True,
                "living": living,
                "openConnections": open_connections,
                "birthRate": birth_rate,
                "connectionsRate": connections_rate,
            }

    def update_load_specification(self):
        if self.test_type == "ddos":
            self.load_specification = {
                "duration": int(self.in_duration),
                "startup": int(self.in_startup),
                "rampup": int(self.in_rampup),
                "shutdown": int(self.in_shutdown),
                self.load_key: int(self.in_start_load),
            }
        elif self.test_type in ["max_cps", "max_tput"]:
            self.load_specification = {
                "duration": int(self.in_duration),
                "startup": int(self.in_startup),
                "rampup": int(self.in_rampup),
                "shutdown": int(self.in_shutdown),
            }
        else:
            self.load_specification = {
                "duration": int(self.in_duration),
                "startup": int(self.in_startup),
                "rampup": int(self.in_rampup),
                "rampdown": int(self.in_rampdown),
                "shutdown": int(self.in_shutdown),
                self.load_key: int(self.in_start_load),
                "type": self.in_load_type,
                "constraints": self.load_constraints,
                #"constraints": {"enabled": False},
            }

    def update_runtime_options(self):
        self.stat_sampling_interval = self.test_config["config"]["runtimeOptions"]["statisticsSamplingInterval"]
        if self.stat_sampling_interval == False:
            if int(self.in_duration) <= 800:
                self.stat_sampling_interval = 4
            else:
                self.stat_sampling_interval = int(self.in_duration/200)
        self.runtime_options = {
            "statisticsSamplingInterval": self.stat_sampling_interval,
            }

    def test_type(self):
        if self.type_v2 == "http_throughput":
            test_type = "tput"
        elif self.type_v2 == "http_connections_per_second":
            test_type = "cps"
        elif self.type_v2 == "open_connections":
            test_type = "conns"
        elif self.type_v2 == "emix":
            test_type = "emix"
        elif self.type_v2 == "max_http_connections_per_second":
            test_type = "max_cps"
        elif self.type_v2 == "max_http_throughput":
            test_type = "max_tput"
        elif self.type_v2 in ["volumetric_ddos", "protocol_ddos"]:
            test_type = "ddos"
        else:
            test_type = "tput"
        self.test_type = test_type
        return test_type

    def start_test_run(self):
        try:
            response = self.cf.start_test(self.test_id)
            log.info(f"{json.dumps(response, indent=4)}")
            self.test_started = True
        except Exception as detailed_exception:
            log.error(
                f"Exception occurred when starting the test: "
                f"\n<{detailed_exception}>"
            )
            self.test_started = False
        return response

    def update_test_run(self):
        self.test_run_update = self.cf.get_test_run(self.id)
        self.status = self.test_run_update.get("status")  # main run status 'running'
        self.sub_status = self.test_run_update.get("subStatus")
        self.score = self.test_run_update.get("score")
        self.grade = self.test_run_update.get("grade")
        self.started_at = self.test_run_update.get("startedAt")
        self.finished_at = self.test_run_update.get("finishedAt")
        self.progress = self.test_run_update.get("progress")
        self.time_elapsed = self.test_run_update.get("timeElapsed")
        self.time_remaining = self.test_run_update.get("timeRemaining")

        update_test_run_log = (
            f"Status: {self.status} sub status: {self.sub_status} "
            f" elapsed: {self.time_elapsed}  remaining: {self.time_remaining}"
        )
        log.debug(update_test_run_log)
        return True

    def update_phase(self):
        """updates test phase based on elapsed time vs. loadspec configuration

        If goal seeking is enabled and the test is in steady phase, the phase will be set to goalseek

        :return: None
        """
        phase = None
        steady_duration = self.in_duration - (
            self.in_startup + self.in_rampup + self.in_rampdown + self.in_shutdown
        )
        if 0 <= self.time_elapsed <= self.in_startup:
            phase = "startup"
        elif self.in_startup <= self.time_elapsed <= (self.in_startup + self.in_rampup):
            phase = "rampup"
        elif (
            (self.in_startup + self.in_rampup)
            <= self.time_elapsed
            <= (self.in_duration - (self.in_rampdown + self.in_shutdown))
        ):
            phase = "steady"
            if self.first_steady_interval:
                phase = "rampup"
                self.first_steady_interval = False
        elif (
            (self.in_startup + self.in_rampup + steady_duration)
            <= self.time_elapsed
            <= (self.in_duration - self.in_shutdown)
        ):
            phase = "rampdown"
        elif (
            (self.in_duration - self.in_shutdown)
            <= self.time_elapsed + self.stat_sampling_interval
            < self.in_duration
        ):
            phase = "shutdown"
        elif self.in_duration <= self.time_elapsed + self.stat_sampling_interval:
            phase = "finished"

        log.info(f"test phase: {phase}")
        self.phase = phase

        # Override phase if ramp seek is enabled
        if self.in_ramp_seek and self.phase == "steady" and not self.ramp_seek_complete:
            self.phase = "rampseek"
            log.info(f"ramp seek phase: {self.phase}")
        # Override phase if goal seeking is enabled
        elif self.in_goal_seek and self.phase == "steady":
            self.phase = "goalseek"
            log.info(f"goal seek phase: {self.phase}")

    def update_run_stats(self):
        get_run_stats = self.cf.fetch_test_run_statistics(self.id)
        #log.debug(f'********************************************')
        #log.debug(f'{get_run_stats}')
        #log.debug(f'********************************************')
        self.update_client_stats(get_run_stats)
        self.update_server_stats(get_run_stats)

    def update_client_stats(self, get_run_stats):
        client_stats = {}
        for i in get_run_stats["client"]:
            if "type" in i and "subType" in i and "value" in i:
                type = i["type"]
                sub_type = i["subType"]
                value = i["value"]
                if not type in client_stats:
                    client_stats[type] = {}
                client_stats[type][sub_type] = value
            elif "type" in i and "value" in i:
                type = i["type"]
                value = i["value"]
                client_stats[type] = value
        self.assign_client_run_stats(client_stats)

    def update_server_stats(self, get_run_stats):
        server_stats = {}
        for i in get_run_stats["server"]:
            if "type" in i and "subType" in i and "value" in i:
                type = i["type"]
                sub_type = i["subType"]
                value = i["value"]
                if not type in server_stats:
                    server_stats[type] = {}
                server_stats[type][sub_type] = value
            elif "type" in i and "value" in i:
                type = i["type"]
                value = i["value"]
                server_stats[type] = value
        self.assign_server_run_stats(server_stats)

    def assign_client_run_stats(self, client_stats):
        self.c_rx_bandwidth = client_stats.get("driver", {}).get("rxBandwidth", 0)
        self.c_rx_packet_count = client_stats.get("driver", {}).get("rxPacketCount", 0)
        self.c_rx_packet_rate = client_stats.get("driver", {}).get("rxPacketRate", 0)
        self.c_tx_bandwidth = client_stats.get("driver", {}).get("txBandwidth", 0)
        self.c_tx_packet_count = client_stats.get("driver", {}).get("txPacketCount", 0)
        self.c_tx_packet_rate = client_stats.get("driver", {}).get("txPacketRate", 0)
        self.c_http_aborted_txns = client_stats.get("http", {}).get("abortedTxns", 0)
        self.c_http_aborted_txns_sec = client_stats.get("http", {}).get(
            "abortedTxnsPerSec", 0
        )
        self.c_http_attempted_txns = client_stats.get("sum", {}).get("attemptedTxns", 0)
        self.c_http_attempted_txns_sec = client_stats.get("sum", {}).get(
            "attemptedTxnsPerSec", 0
        )
        self.c_http_successful_txns = client_stats.get("sum", {}).get(
            "successfulTxns", 0
        )
        self.c_http_successful_txns_sec = client_stats.get("sum", {}).get(
            "successfulTxnsPerSec", 0
        )
        self.c_http_unsuccessful_txns = client_stats.get("sum", {}).get(
            "unsuccessfulTxns", 0
        )
        self.c_http_unsuccessful_txns_sec = client_stats.get("sum", {}).get(
            "unsuccessfulTxnsPerSec", 0
        )
        self.c_loadspec_avg_idle = client_stats.get("loadspec", {}).get(
            "averageIdleTime", 0
        )
        self.c_loadspec_avg_cpu = round(
            client_stats.get("loadspec", {}).get("cpuUtilized", 0), 1
        )
        self.c_memory_main_size = client_stats.get("memory", {}).get("mainPoolSize", 0)
        self.c_memory_main_used = client_stats.get("memory", {}).get("mainPoolUsed", 0)
        self.c_memory_packetmem_used = client_stats.get("memory", {}).get(
            "packetMemoryUsed", 0
        )
        self.c_memory_rcv_queue_length = client_stats.get("memory", {}).get(
            "rcvQueueLength", 0
        )
        self.c_simusers_alive = client_stats.get("simusers", {}).get("simUsersAlive", 0)
        self.c_simusers_animating = client_stats.get("simusers", {}).get(
            "simUsersAnimating", 0
        )
        self.c_simusers_blocking = client_stats.get("simusers", {}).get(
            "simUsersBlocking", 0
        )
        self.c_simusers_sleeping = client_stats.get("simusers", {}).get(
            "simUsersSleeping", 0
        )
        self.c_current_load = client_stats.get("sum", {}).get("currentLoadSpecCount", 0)
        self.c_desired_load = client_stats.get("sum", {}).get("desiredLoadSpecCount", 0)
        self.c_tcp_avg_ttfb = round(
            client_stats.get("tcp", {}).get("averageTimeToFirstByte", 0), 1
        )
        self.c_tcp_avg_tt_synack = round(
            client_stats.get("tcp", {}).get("averageTimeToSynAck", 0), 1
        )
        self.c_tcp_cumulative_attempted_conns = client_stats.get("tcp", {}).get(
            "cummulativeAttemptedConns", 0
        )
        self.c_tcp_cumulative_established_conns = client_stats.get("tcp", {}).get(
            "cummulativeEstablishedConns", 0
        )
        self.c_url_avg_response_time = round(
            client_stats.get("url", {}).get("averageRespTimePerUrl", 0), 1
        )
        self.c_tcp_attempted_conn_rate = client_stats.get("sum", {}).get(
            "attemptedConnRate", 0
        )
        self.c_tcp_established_conn_rate = client_stats.get("sum", {}).get(
            "establishedConnRate", 0
        )
        self.c_tcp_attempted_conns = client_stats.get("sum", {}).get(
            "attemptedConns", 0
        )
        self.c_tcp_established_conns = client_stats.get("sum", {}).get(
            "currentEstablishedConns", 0
        )

        self.time_elapsed = client_stats.get("timeElapsed", 0)
        self.time_remaining = client_stats.get("timeRemaining", 0)

        if self.test_type in ["max_cps", "max_tput"]:
            self.c_rx_bandwidth = client_stats.get("sum", {}).get("rxBandwidth", 0)
            self.c_tx_bandwidth = client_stats.get("sum", {}).get("txBandwidth", 0)
            self.c_http_aborted_txns = client_stats.get("sum", {}).get("abortedTxns", 0)
            self.c_current_load = client_stats.get("esp", {}).get("currentLoadSpecCount", 0)
            self.c_desired_load = client_stats.get("esp", {}).get("desiredLoadSpecCount", 0)

        self.c_total_bandwidth = self.c_rx_bandwidth + self.c_tx_bandwidth
        if self.c_memory_main_size > 0 and self.c_memory_main_used > 0:
            self.c_memory_percent_used = round(100*
                (self.c_memory_main_used / self.c_memory_main_size), 2
            )
        if self.c_current_load > 0 and self.c_desired_load > 0:
            self.c_current_desired_load_variance = round(
                self.c_current_load / self.c_desired_load, 2
            )

        if self.c_http_successful_txns > 0:
            self.c_transaction_error_percentage = (
                self.c_http_unsuccessful_txns + self.c_http_aborted_txns
            ) / self.c_http_successful_txns
        self.c_cpu_percent = round(100 - self.c_loadspec_avg_cpu, 2)
        self.c_memory_percent = round(100 - self.c_memory_percent_used, 2)
        self.c_pktmem_percent = round(100 - (self.c_memory_packetmem_used*100)/self.pkt_memory_threshold, 2)
        self.c_ttfb_percent = round(100 - (self.c_tcp_avg_ttfb*100)/self.ttfb_threshold, 2)
        if self.c_current_load_startup == 0:
            self.c_current_load_startup = self.c_current_load
        if self.c_memory_main_used_startup == 0:
            self.c_memory_main_used_startup = self.c_memory_main_used
        return True

    def assign_server_run_stats(self, server_stats):
        self.s_rx_bandwidth = server_stats.get("driver", {}).get("rxBandwidth", 0)
        self.s_rx_packet_count = server_stats.get("driver", {}).get("rxPacketCount", 0)
        self.s_rx_packet_rate = server_stats.get("driver", {}).get("rxPacketRate", 0)
        self.s_tx_bandwidth = server_stats.get("driver", {}).get("txBandwidth", 0)
        self.s_tx_packet_count = server_stats.get("driver", {}).get("txPacketCount", 0)
        self.s_tx_packet_rate = server_stats.get("driver", {}).get("txPacketRate", 0)
        self.s_memory_main_size = server_stats.get("memory", {}).get("mainPoolSize", 0)
        self.s_memory_main_used = server_stats.get("memory", {}).get("mainPoolUsed", 0)
        self.s_memory_packetmem_used = server_stats.get("memory", {}).get(
            "packetMemoryUsed", 0
        )
        self.s_memory_rcv_queue_length = server_stats.get("memory", {}).get(
            "rcvQueueLength", 0
        )
        self.s_memory_avg_cpu = round(
            server_stats.get("memory", {}).get("cpuUtilized", 0), 1
        )
        self.s_tcp_closed_error = server_stats.get("sum", {}).get("closedWithError", 0)
        self.s_tcp_closed = server_stats.get("sum", {}).get("closedWithNoError", 0)
        self.s_tcp_closed_reset = server_stats.get("sum", {}).get("closedWithReset", 0)

        if self.test_type in ["max_cps", "max_tput", "ddos"]:
            self.c_tcp_established_conn_rate = server_stats.get("sum", {}).get("connsPerSec", 0)
        if self.test_type in ["ddos"]:
            self.c_tcp_established_conns = server_stats.get("sum", {}).get("openConns", 0)

        if self.s_memory_main_size > 0 and self.s_memory_main_used > 0:
            self.s_memory_percent_used = round(100*
                (self.s_memory_main_used / self.s_memory_main_size), 2
            )
        self.s_cpu_percent = round(100 - self.s_memory_avg_cpu, 2)
        self.s_memory_percent = round(100 - self.s_memory_percent_used, 2)
        self.s_pktmem_percent = round(100 - (self.s_memory_packetmem_used*100)/self.pkt_memory_threshold, 2)
        if self.s_memory_main_used_startup == 0:
            self.s_memory_main_used_startup = self.s_memory_main_used
        return True

    def check_resource(self):
        log.debug("Inside the check_resources method.")
        current_available = {}
        if self.test_type == "conns" and self.in_load_type != "SimUsers/Second":
            current_available['Client Memory'] = self.c_memory_percent
            current_available['Server Memory'] = self.s_memory_percent
            self.lowest_available_resource = min(current_available.values())
        else:
            current_available['Client CPU'] = self.c_cpu_percent
            current_available['Server CPU'] = self.s_cpu_percent
            current_available['Client Pkt Mem'] = self.c_pktmem_percent
            current_available['Server Pkt Mem'] = self.s_pktmem_percent
            current_available['TTFB'] = self.c_ttfb_percent
            current_available['BW'] = round(100 * (self.queue_speed * self.speed_capacity_adjust - self.c_total_bandwidth/1000)/self.queue_speed, 2)
            if self.goal_seek_count >= 2:
                current_available['Client Memory'] = self.c_memory_percent
                current_available['Server Memory'] = self.s_memory_percent
            self.lowest_available_resource = min(current_available.values())
        for key, val in current_available.items():
            if val == self.lowest_available_resource:
                lowest = key
        log.debug(f"Lowest available resource is {lowest} at {self.lowest_available_resource}% availability")
        if self.lowest_available_resource < 0:
            log.warning(f"Resource spike detected: {lowest} is {self.lowest_available_resource}% available ")
        elif self.lowest_available_resource < 1:
            log.warning(f"At least one resource is exhausted or close to exhausted: "
                        f"{lowest} is {self.lowest_available_resource}% available")
            log.debug((f"At least one resource is exhausted or close to exhausted. Current percentages are: "
                        f"\nClient CPU {self.c_cpu_percent}% available "
                        f"\nServer CPU {self.s_cpu_percent}% available "
                        f"\nClient Memory {self.c_memory_percent}% available "
                        f"\nServer Memory {self.s_memory_percent}% available "
                        f"\nClient Packet Memory {self.c_pktmem_percent}% available "
                        f"\nServer Packet Memory {self.s_pktmem_percent}% available "
                        f"\nTTFB {self.c_ttfb_percent}% available (% of specified acceptable limit)"))

    def count_new_load(self):
        log.debug("Counting new load")
        counted_load = 0
        self.check_resource()
        check_minimal_load = True
        load_increase_value = int(round(self.minimal_load_spec_change * self.in_capacity_adjust) )
        last_loadspec_increase_percentage = self.rolling_load.increase_avg
        last_metric_increase_percentage = max(self.rolling_tps.increase_avg,
                                              self.rolling_cps.increase_avg,
                                              self.rolling_bw.increase_avg)
        metric_evolution_based_percentage_increase = int(round(last_metric_increase_percentage / 2))
        if metric_evolution_based_percentage_increase <= 0:
            metric_evolution_based_percentage_increase = 0.3
        if self.lowest_available_resource != 100:
            tentative_load_increase_percentage = (self.lowest_available_resource / (100 - self.lowest_available_resource))*100
        else:
            tentative_load_increase_percentage = 100
        loadValueIncreasePercentage = int(round(tentative_load_increase_percentage / 2))
        if loadValueIncreasePercentage <= 0:
            loadValueIncreasePercentage = 0.3
        if loadValueIncreasePercentage >=200:
            loadValueIncreasePercentage = loadValueIncreasePercentage / 1.2
        resource_based_percentage_increase = loadValueIncreasePercentage
        log.debug(f"last_loadspec_increase_percentage is: {last_loadspec_increase_percentage}")
        log.debug(f"last_metric_increase_percentage is: {last_metric_increase_percentage}")
        log.debug(f"self.lowest_available_resource is: {self.lowest_available_resource}")
        log.debug(f"metric_evolution_based_percentage_increase is: {metric_evolution_based_percentage_increase}")
        log.debug(f"resource_based_percentage_increase is: {resource_based_percentage_increase}")
        if self.test_type == "conns" and self.in_load_type != "SimUsers":
            log.debug(f"Open Conns")
            if self.in_load_type == "SimUsers/Second":
                if self.lowest_available_resource < 30:
                    load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / 2) / 100)
                else:
                    load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase ) / 100)
            if self.in_load_type == "Connections":
                if self.c_memory_one_connection == 0:
                    self.c_memory_one_connection = round((self.c_memory_main_used - self.c_memory_main_used_startup) * 1000 / (self.c_current_load - self.c_current_load_startup), 2)
                load_increase_value = int((self.c_memory_main_size - self.c_memory_main_used_startup) * 1000 / self.c_memory_one_connection) - self.c_current_load
                log.debug(f"Memory of Client for one Connection: {self.c_memory_one_connection}K")
        elif self.test_type == "cps":
            if self.rolling_tps.increase_avg >= 10:
                load_increase_value = int(round(self.minimal_load_spec_change * self.in_capacity_adjust) * 5 )
            elif self.rolling_tps.increase_avg >= 4:
                load_increase_value = int(round(self.minimal_load_spec_change * self.in_capacity_adjust) * 4 )
            elif self.rolling_tps.increase_avg >= 2:
                load_increase_value = int(round(self.minimal_load_spec_change * self.in_capacity_adjust) * 3 )
            elif self.rolling_tps.increase_avg >= 0.5:
                load_increase_value = int(round(self.minimal_load_spec_change * self.in_capacity_adjust) * 2 )
            else:
                load_increase_value = int(round(self.minimal_load_spec_change * self.in_capacity_adjust) )
            if self.max_load_reached:
                load_increase_value = int(round(self.minimal_load_spec_change * self.in_capacity_adjust / 2) )
                check_minimal_load = False
        else:
            if last_loadspec_increase_percentage <= 0.3 or last_metric_increase_percentage <= 0.3:
                log.debug(f"Case 1: last_loadspec_increase_percent {last_loadspec_increase_percentage}, last_metric_increase_percent is {last_metric_increase_percentage}")
                if self.lowest_available_resource <=1:
                    load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase) / 100)
                else:
                    load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / self.count_load_adjust_high) / 100)
            else:
                log.debug(f"Case 2: last_metric_increase_percent {last_metric_increase_percentage}, last_loadspec_increase_percent {last_loadspec_increase_percentage}")
                if metric_evolution_based_percentage_increase > resource_based_percentage_increase:
                    if resource_based_percentage_increase >= 30:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase ) / 100)
                    elif resource_based_percentage_increase >= 5:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / self.count_load_adjust_high) / 100)   
                    else:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / self.count_load_adjust_low) / 100)  
                else:
                    if resource_based_percentage_increase >= 100:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase * self.count_load_adjust_low) / 100)
                    elif resource_based_percentage_increase >= 50 and resource_based_percentage_increase < 100:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / self.count_load_adjust_high) / 100)
                    elif resource_based_percentage_increase >= 35:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / self.count_load_adjust_low) / 100)
                    elif resource_based_percentage_increase >= 20:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase) / 100)
                    elif resource_based_percentage_increase >= 10:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / self.count_load_adjust_low) / 100)
                    elif resource_based_percentage_increase >= 1:
                        load_increase_value = int(round(self.c_current_load * resource_based_percentage_increase / self.count_load_adjust_high) / 100)
                    else:
                        load_increase_value = int(round(self.c_current_load * metric_evolution_based_percentage_increase) / 100)
        if self.test_type == "emix":
            if 15 < resource_based_percentage_increase < 40:
                load_increase_value = int(load_increase_value / self.count_load_adjust_emix)
            if resource_based_percentage_increase <= 15:
                load_increase_value = int(load_increase_value / 2.5)
        if check_minimal_load:                
            counted_minimal_load_spec_change_1 = int(self.c_current_load * 0.004)
            counted_minimal_load_spec_change_2 = self.round_up_to_core(self.c_current_load, self.client_core_count) + self.minimal_load_spec_change * self.in_capacity_adjust                                                 - self.c_current_load
            counted_minimal_load_spec_change = max(counted_minimal_load_spec_change_1, counted_minimal_load_spec_change_2)
            if load_increase_value < counted_minimal_load_spec_change:
                load_increase_value = counted_minimal_load_spec_change
            if len(self.load_increase_list) >=2 and resource_based_percentage_increase < 10 and load_increase_value > self.load_increase_list[-1]:
                load_increase_value = int((self.load_increase_list[-1] + self.load_increase_list[-2]) / 2)
        load_increase_value = self.round_up_to_core(load_increase_value, self.client_core_count)
        counted_load = self.c_current_load + load_increase_value
        counted_load = self.round_up_to_core(counted_load, self.client_core_count)
        load_increase_value = counted_load - self.c_current_load
        self.load_increase_list.append(load_increase_value)
        log.debug(f"{load_increase_value} will be added to current load {self.c_current_load}")
        return counted_load

    def print_test_status(self):
        status = (
            f"{self.timer}s -status: {self.status} -sub status: {self.sub_status} "
            f"-progress: {self.progress} -seconds elapsed: {self.time_elapsed} "
            f"-remaining: {self.time_remaining}"
        )
        print(status)

    def print_test_stats(self):
        stats = (
            f"{self.time_elapsed}s {self.phase} "
            f"-seek ready: {str(self.rolling_count_since_goal_seek.stable):5}"
            f"\n-load: {self.c_current_load:3.0f}/{self.c_desired_load:3.0f}  -stable: {str(self.rolling_load.stable):5} "
            f" -cur avg/max var: {self.rolling_load.avg_max_variance:3.2f} "
            f" -current/desired load var: {self.c_current_desired_load_variance:6.1f} "
            f" -delta: {self.rolling_load.increase_avg:4.2f} load list: {self.rolling_load.list}"
            f"\n-bw:{self.c_total_bandwidth:10,.0f}  -stable: {str(self.rolling_bw.stable):5} "
            f" -cur avg/max var: {self.rolling_bw.avg_max_variance:3.2f} "
            f" -cur avg:{self.rolling_bw.avg_val:8.0f}  -prev:{self.rolling_bw.avg_val_last:8.0f} "
            f" -delta: {self.rolling_bw.increase_avg:4.2f}  -bw list: {self.rolling_bw.list}"
            f"\n-tps: {self.c_http_successful_txns_sec:8.0f}  -stable: {str(self.rolling_tps.stable):5} "
            f" -cur avg/max var: {self.rolling_tps.avg_max_variance:3.2f} "
            f" -cur avg: {self.rolling_tps.avg_val:7.0f}  -prev: {self.rolling_tps.avg_val_last:7.0f} "
            f" -delta: {self.rolling_tps.increase_avg:4.2f} -tps list: {self.rolling_tps.list}"
            f"\n-cps: {self.c_tcp_established_conn_rate:8.0f}  -stable: {str(self.rolling_cps.stable):5} "
            f" -cur avg/max var: {self.rolling_cps.avg_max_variance:3.2f} "
            f" -cur avg: {self.rolling_cps.avg_val:7.0f}  -prev: {self.rolling_cps.avg_val_last:7.0f} "
            f" -delta: {self.rolling_cps.increase_avg:4.2f} -cps list: {self.rolling_cps.list} "
            f"\n-conns:{self.c_tcp_established_conns:7.0f}  -stable: {str(self.rolling_conns.stable):5} "
            f" -cur avg/max var: {self.rolling_conns.avg_max_variance:3.2f} "
            f" -cur avg: {self.rolling_conns.avg_val:7.0f}  -prev: {self.rolling_conns.avg_val_last:7.0f} "
            f" -delta: {self.rolling_conns.increase_avg:4.2f} -con list: {self.rolling_conns.list}"
            f"\n-ttfb: {self.c_tcp_avg_ttfb:7.0f}  -stable: {str(self.rolling_ttfb.stable):5} "
            f" -cur avg/max var: {self.rolling_ttfb.avg_max_variance:3.2f} "
            f" -cur avg: {self.rolling_ttfb.avg_val:7.1f}  -prev: {self.rolling_ttfb.avg_val_last:7.1f} "
            f" -delta: {self.rolling_ttfb.increase_avg:4.2f} ttfb list: {self.rolling_ttfb.list}"
            f"\n-cpu_c: {self.c_loadspec_avg_cpu:6.1f}  -pktmemused_c: {self.c_memory_packetmem_used:4.0f} "
            f" -memused_c: {self.c_memory_main_used:5.0f}  -memusedpert_c: {self.c_memory_percent_used:3.1f}"
            f"\n-cpu_s: {self.s_memory_avg_cpu:6.1f}  -pktmemUsed_s: {self.s_memory_packetmem_used:4.0f} "
            f" -memused_s: {self.s_memory_main_used:5.0f}  -memusedperc_s: {self.s_memory_percent_used:3.1f}"
            f"\n-attempt txn: {self.c_http_attempted_txns:8.0f}  -success txns: {self.c_http_successful_txns:8.0f} "
            f" -failed txns: {self.c_http_unsuccessful_txns} (unsucc) + {self.c_http_aborted_txns} (abort)"
            f"\n-highest_tps: {self.highest_pair['highest_tps']:8.0f}  -highest_load: {self.highest_pair['highest_load']:8.0f} "
            f" -highest_desired_load: {self.highest_pair['highest_desired_load']:5.0f}  -highest_bw: {self.highest_pair['highest_bw']:5,.0f} "
            f" -highest_cps: {self.highest_pair['highest_cps']:5.0f}  -highest_conns: {self.highest_pair['highest_conns']}"
            f"\n-max_load_reached: {self.max_load_reached}  -goal_seek_count_after_max_load: {self.goal_seek_count_after_max_load}"
        )
        print(stats)
        log.debug(f"\n{stats}")

    def wait_for_running_status(self):
        """
        Wait for the current test to return a 'running' status.
        :return: True if no statements failed and there were no exceptions. False otherwise.
        """
        log.debug("Inside the RunTest/wait_for_running_status method.")
        i = 0
        while True:
            log.info(f"Sleeping {self.stat_sampling_interval} seconds")
            time.sleep(self.stat_sampling_interval)
            self.timer = int(round(time.time() - self.start_time))
            i += 4
            if not self.update_test_run():
                return False
            if self.status == "running":
                print(f"{self.timer}s - status: {self.status}")
                break

            print(
                f"{self.timer}s - status: {self.status}  sub status: {self.sub_status}"
            )
            if self.status in {"failed", "finished"}:
                log.error("Test failed")
                return False
            # check to see if another test with the same ID is running
            # (can happen due to requests retry)
            if i > 120 and self.status == "waiting":
                self.check_running_tests()
            # stop after 1800 seconds of waiting
            if i > 1800:
                log.error(
                    "Waited for 1800 seconds, test did not transition to a running status."
                )
                return False
        self.time_to_run = self.timer
        log.debug(f"Test {self.name} successfully went to running status.")
        log.debug(json.dumps(self.test_run_update, indent=4))
        self.run_id = self.test_run_update.get("runId")
        self.report_link = (
            "https://"
            + self.cf.controller_ip
            + "/#results/"
            + self.type_v1
            + "/"
            + self.run_id
        )
        return True

    def check_running_tests(self):
        """Checks if tests with same ID is running and changes control to this test
        This function can be triggered if waiting status is too long because the requests module retry mechanism has
        kicked off two duplicate tests in error. It will look for matching running tests and switch control over to the
        already running duplicate test.
        :return: None
        """
        # get list of run IDs and test IDs with status
        test_runs = self.cf.list_test_runs()
        # look for running status and compare ID
        for run in test_runs:
            if run["status"] == "running":
                log.debug(
                    f"check_running_tests found running test: {json.dumps(run, indent=4)}"
                )
                # if waiting and running test IDs match, change the running test
                if self.test_id == run["testId"]:
                    log.debug(
                        f"check_running_tests found matching test_id {self.test_id}"
                    )
                    # stop current waiting test
                    response = self.cf.stop_test(self.id)
                    log.debug(
                        f"change_running_test, stopped duplicate waiting test: {response}"
                    )
                    # change over to running test
                    self.id = run["id"]
                else:
                    log.debug(
                        f"check_running_tests test_id: {self.test_id} "
                        f"does not match running test_id: {run['testId']}"
                    )

    def wait_for_running_sub_status(self):
        """
        Wait for the current test to return a 'None' sub status.
        :return: True if no statements failed and there were no exceptions. False otherwise.
        """
        log.debug("Inside the RunTest/wait_for_running_sub_status method.")
        i = 0
        while True:
            log.info(f"Sleeping {self.stat_sampling_interval} seconds")
            time.sleep(self.stat_sampling_interval)
            self.timer = int(round(time.time() - self.start_time))
            i += 4
            if not self.update_test_run():
                return False
            print(
                f"{self.timer}s - status: {self.status}  sub status: {self.sub_status}"
            )
            if self.sub_status is None:
                break

            if self.status in {"failed", "finished"}:
                log.error("Test failed")
                return False
            # stop after 0 seconds of waiting
            if i > 360:
                log.error(
                    "Waited for 360 seconds, test did not transition to traffic state."
                )
                return False
        self.time_to_start = self.timer - self.time_to_run
        log.debug(f"Test {self.name} successfully went to traffic state.")
        log.debug(json.dumps(self.test_run_update, indent=4))
        return True

    def stop_wait_for_finished_status(self):
        """
        Stop and wait for the current test to return a 'finished' status.
        :return: True if no statements failed and there were no exceptions.
         False otherwise.
        """
        log.debug("Inside the stop_test/wait_for_finished_status method.")
        self.time_to_stop_start = self.timer
        if self.status == "running":
            self.cf.stop_test(self.id)

        i = 0
        while True:
            log.info(f"Sleeping {self.stat_sampling_interval} seconds")
            time.sleep(self.stat_sampling_interval)
            self.timer = int(round(time.time() - self.start_time))
            i += 4
            if not self.update_test_run():
                return False
            if self.status in {"stopped", "finished", "failed"}:
                print(f"{self.timer} status: {self.status}")
                break
            if self.status == "failed":
                print(f"{self.timer} status: {self.status}")
                return False

            print(
                f"{self.timer}s - status: {self.status}  sub status: {self.sub_status}"
            )
            if i > 1800:
                error_msg = (
                    "Waited for 1800 seconds, "
                    "test did not transition to a finished status."
                )
                log.error(error_msg)
                print(error_msg)
                return False
        self.time_to_stop = self.timer - self.time_to_stop_start
        log.debug(
            f"Test {self.name} successfully went to finished status in "
            f"{self.time_to_stop} seconds."
        )
        return True

    def wait_for_test_activity(self):
        """
        Wait for the current test to show activity - metric(s) different than 0.
        :return: True if no statements failed and there were no exceptions.
        False otherwise.
        """
        log.debug("Inside the RunTest/wait_for_test_activity method.")
        test_generates_activity = False
        i = 0
        while not test_generates_activity:
            self.timer = int(round(time.time() - self.start_time))
            self.update_test_run()
            self.update_run_stats()
            # self.print_test_status()

            if self.sub_status is None:
                self.print_test_stats()
                self.save_results()

            if self.c_http_successful_txns_sec > 0:
                test_generates_activity = True
            if self.status in {"failed", "finished"}:
                log.error("Test failed")
                return False
            if i > 180:
                error_msg = (
                    "Waited for 180 seconds, test did not have successful transactions"
                )
                log.error(error_msg)
                print(error_msg)
                return False
            log.info(f"Sleeping {self.stat_sampling_interval} seconds")
            time.sleep(self.stat_sampling_interval)
            i = i + 4
            print(f"")
        self.time_to_activity = self.timer - self.time_to_start - self.time_to_run
        return True

    @staticmethod
    def countdown(t):
        """countdown function

        Can be used after load increase for results to update

        :param t: countdown in seconds
        :return: None
        """
        log.info(f"Sleeping {t} seconds")
        while t:
            mins, secs = divmod(t, 60)
            time_format = "{:02d}:{:02d}".format(mins, secs)
            #print(time_format, end="\r")
            time.sleep(1)
            t -= 1

    def goal_seek(self):
        log.info(f"In goal_seek function")
      #  self.bad_load_count = 0
        if self.c_current_load == 0:
            self.stop = True
            log.info(f"goal_seek stop, c_current_load == 0")
            return False
        if self.first_goal_load_increase:
            log.info(f"First time goal_seek")
            self.first_goal_load_increase = False
            new_load = self.c_current_load + (self.in_incr_low * self.in_capacity_adjust)
            log.info(f"new load {new_load} = current_load {self.c_current_load} + {self.in_incr_low} * {self.in_capacity_adjust}")
            if new_load <= self.c_desired_load:
                log.info(f"{new_load} (new load) <= {self.c_desired_load} (current desired load)")
                self.max_load_reached = True
                return False
            if self.test_suite == "default":
                if new_load < 32:
                    new_load = self.round_up_to_core(32, self.client_core_count) 
            self.load_increase_list.append(self.in_incr_low * self.in_capacity_adjust)
        else:
          if self.test_suite == "default":
            if self.test_type == "conns":
                 new_load = self.goal_seek_set_conns_by_resource()
                 log.info(f"new_load = {new_load}")
            elif self.check_if_load_type_simusers():
                new_load = self.goal_seek_set_simuser_kpi_by_resource(self.kpi_1)
                log.info(f"new_load = {new_load}")
            elif self.check_if_load_type_default():
                new_load = self.goal_seek_set_default_by_resource()
                log.info(f"new_load = {new_load}")
            else:
                report_error = f"Unknown load type: " \
                    f"{self.test_config['config']['loadSpecification']['type']}"
          else:
            if self.check_if_load_type_simusers():
                new_load = self.goal_seek_set_simuser_kpi(self.kpi_1)
                log.info(f"new_load = {new_load}")
            elif self.check_if_load_type_default():
                new_load = self.goal_seek_set_default()
                log.info(f"new_load = {new_load}")
            else:
                report_error = f"Unknown load type: " \
                    f"{self.test_config['config']['loadSpecification']['type']}"
                log.error(report_error)
                print(report_error)
                return False

        if new_load is False:
            log.info(
                f"Config load spec type: {self.test_config['config']['loadSpecification']['type']}"
            )
            log.info(f"Goal_seek return, new_load is False")
            return False

        self.new_load_list.append(new_load)
        count_time = self.stat_sampling_interval * 4
        self.change_update_load(new_load, count_time)
        if self.max_load_reached == True:
            self.goal_seek_count_after_max_load += 1
        self.goal_seek_count += 1
        log.info(f"Goal seeking has changed load list:   {self.new_load_list}")
        log.info(f"Goal seeking has increased load list: {self.load_increase_list}")
        return True

    def ramp_seek(self, ramp_kpi, ramp_to_value):
        log.info(f"In ramp_seek function")
        if self.c_current_load == 0:
            self.stop = True
            log.info(f"ramp_seek stop, c_current_load == 0")
            return False
        # if self.first_ramp_load_increase:
        #     self.first_ramp_load_increase = False
        #     new_load = self.c_current_load * 2

        if self.in_ramp_step < 1:
            self.ramp_seek_complete = True
            return
        if ramp_kpi.current_value < ramp_to_value:
            load_increase_multiple = round(ramp_to_value / ramp_kpi.current_value, 3)
            load_increase = (self.c_current_load * load_increase_multiple) - self.c_current_load
            load_increase = round(load_increase / self.in_ramp_step, 3)
            new_load = self.round_up_to_even(self.c_current_load + load_increase)
            self.in_ramp_step = self.in_ramp_step - 1

            log.info(f"new load: {new_load}, current_load: {self.c_current_load}"
                     f" * {load_increase} load_increase "
                     f"ramp_step left: {self.in_ramp_step} "
                     f"\n ramp_to_value: {ramp_to_value} "
                     f"ramp_kpi.current_value: {ramp_kpi.current_value}"
                     )
            self.in_incr_low = self.round_up_to_even(new_load * self.in_ramp_low/100)
            self.in_incr_med = self.round_up_to_even(new_load * self.in_ramp_med/100)
            self.in_incr_high = self.round_up_to_even(new_load * self.in_ramp_high/100)
        else:
            self.ramp_seek_complete = True
        self.change_update_load(new_load, 8)
        return True

    @staticmethod
    def round_up_to_even(v):
        return math.ceil(v / 2.) * 2

    @staticmethod
    def round_up_to_core(v, core_count):
        v = math.ceil(v / core_count) * core_count
        log.debug(f"Round up the load to {v} according to core count {core_count}")
        return v

    def check_if_load_type_simusers(self):
        if self.test_config["config"]["loadSpecification"]["type"].lower() in {
            "simusers",
            "simusers/second",
        }:
            return True
        return False

    def check_if_load_type_default(self):
        if self.test_config["config"]["loadSpecification"]["type"].lower() in {
            "bandwidth",
            "connections",
            "connections/second",
        }:
            return True
        return False

    def change_update_load(self, new_load, count_down):
        if self.test_suite != "default":
            new_load = self.round_up_to_even(new_load)
        log_msg = f"\nchanging load from: {self.c_current_load} to: {new_load}  status: {self.status}"
        log.info(log_msg)
        print(log_msg)
        try:
            self.cf.change_load(self.id, new_load)
            self.rolling_tps.load_increase_complete()
            self.rolling_ttfb.load_increase_complete()
            self.rolling_load.load_increase_complete()
            self.rolling_cps.load_increase_complete()
            self.rolling_conns.load_increase_complete()
            self.rolling_bw.load_increase_complete()
        except Exception as detailed_exception:
            log.error(
                f"Exception occurred when changing test: " f"\n<{detailed_exception}>"
            )
        self.countdown(count_down)
        return True

    def goal_seek_set_default(self):
        set_load = 0
        if self.c_current_desired_load_variance >= 0.97:
            if self.c_current_load <= self.in_threshold_low:
                set_load = self.c_current_load + (
                    self.in_incr_low * self.in_capacity_adjust
                )
            elif self.c_current_load <= self.in_threshold_med:
                set_load = self.c_current_load + (
                    self.in_incr_med * self.in_capacity_adjust
                )
            elif self.c_current_load <= self.in_threshold_high:
                set_load = self.c_current_load + (
                    self.in_incr_high * self.in_capacity_adjust
                )
            elif self.c_current_load > self.in_threshold_high:
                return False
        else:
            return False
        if self.in_threshold_high < set_load:
            if self.c_current_desired_load_variance > 0.99:
                return False
            else:
                set_load = self.in_threshold_high
        return set_load

    def goal_seek_set_simuser_kpi(self, kpi):
        log.debug(f"in goal_seek_set_simuser_kpi function")
        set_load = 0
        if kpi.increase_avg >= self.in_threshold_low:
            set_load = self.c_current_load + (self.in_incr_low *
                                              self.in_capacity_adjust)
        elif kpi.increase_avg >= self.in_threshold_med:
            set_load = self.c_current_load + (self.in_incr_med *
                                              self.in_capacity_adjust)
        elif kpi.increase_avg >= self.in_threshold_high:
            set_load = self.c_current_load + (self.in_incr_high *
                                              self.in_capacity_adjust)
        elif kpi.increase_avg < self.in_threshold_high:
            log.info(
                f"rolling_tps.increase_avg {kpi.increase_avg} < "
                f"{self.in_threshold_high} in_threshold_high"
            )
            return False
        if kpi.avg_max_variance < 0.97:
            set_load = self.c_current_load
            self.max_load_reached = True
        log.info(
            f"set_load = {set_load}  "
            f"kpi_avg_max_variance: {kpi.avg_max_variance}"
        )
        return set_load

    def goal_seek_set_default_by_resource(self):
        log.info(f"In goal_seek_set_default_by_resource function")
        log.info(f"load.increase_avg: {self.rolling_load.increase_avg}, load.no_positive_increase_count: {self.rolling_load.no_positive_increase_count}")
        if self.rolling_load.increase_avg < 0 and self.rolling_load.no_positive_increase_count >= 3:
            self.max_load_reached = True
        if self.max_load_reached == True:
            message = f"max load {self.highest_pair['highest_load']} reached"
            log.info(message)
            print(message)
        set_load = self.count_new_load()
        return set_load

    def goal_seek_set_conns_by_resource(self):
        log.info(f"In goal_seek_set_conns_by_resource function")
        log.info(f"current_desired_load_variance: {self.c_current_desired_load_variance}, client memory_percent_used: {self.c_memory_percent_used}, server memory_percent_used: {self.s_memory_percent_used}")
        #if self.c_current_desired_load_variance >= 1.0 and self.c_memory_percent_used < 100 and self.s_memory_percent_used < 100 and self.rolling_tps.avg_val !=0:
        if self.c_current_desired_load_variance >= 1.0 and self.c_memory_percent_used < 100 and self.s_memory_percent_used < 100:
            set_load = self.count_new_load()
        else:
            self.max_load_reached = True
            set_load = self.count_new_load()
        if self.max_load_reached == True:
            message = f"max load {self.highest_pair['highest_load']} reached"
            log.info(message)
            print(message)
        return set_load
    
    def goal_seek_set_simuser_kpi_by_resource(self, kpi):
        log.info(f"In goal_seek_set_simuser_kpi_by_resource function")
        log.info(f"Kpi avg_max_variance: {kpi.avg_max_variance}, Kpi.increase_avg: {kpi.increase_avg}, Kpi.no_positive_increase_count: {kpi.no_positive_increase_count}, rolling_load.increase_avg: {self.rolling_load.increase_avg}, rolling_load.not_high_count: {self.rolling_load.not_high_count}")
        if kpi.avg_max_variance >= 0.97 and self.rolling_load.increase_avg > 0 and kpi.increase_avg<= 0:
            self.max_load_reached = True
        elif kpi.avg_max_variance < 0.97 and kpi.no_positive_increase_count >= 3:
            self.max_load_reached = True
        if self.max_load_reached == True:
            message = f"max load {self.highest_pair['highest_load']} reached"
            log.info(message)
            print(message)
        set_load = self.count_new_load()
        return set_load

    def update_rolling_averages(self):
        """Updates rolling statistics averages used to make test control decisions

        :return: None
        """
        self.rolling_tps.update(self.c_http_successful_txns_sec)
        self.rolling_tps.check_if_stable(self.max_var_reference)

        self.rolling_ttfb.update(self.c_tcp_avg_ttfb)
        self.rolling_ttfb.check_if_stable(self.max_var_reference)

        self.rolling_load.update(self.c_current_load)
        self.rolling_load.check_if_stable(self.max_var_reference)

        self.rolling_cps.update(self.c_tcp_established_conn_rate)
        self.rolling_cps.check_if_stable(self.max_var_reference)

        self.rolling_conns.update(self.c_tcp_established_conns)
        self.rolling_conns.check_if_stable(self.max_var_reference)

        self.rolling_bw.update(self.c_total_bandwidth)
        self.rolling_bw.check_if_stable(self.max_var_reference)

        self.rolling_count_since_goal_seek.update(1)
        self.rolling_count_since_goal_seek.check_if_stable(0)

    def check_kpi(self):
        self.in_kpi_1 = self.in_kpi_1.lower()
        if self.in_kpi_1 == "tps":
            self.kpi_1 = self.rolling_tps
        elif self.in_kpi_1 == "cps":
            self.kpi_1 = self.rolling_cps
        elif self.in_kpi_1 == "conns":
            self.kpi_1 = self.rolling_conns
        elif self.in_kpi_1 == "bw":
            self.kpi_1 = self.rolling_bw
        elif self.in_kpi_1 == "ttfb":
            self.kpi_1 = self.rolling_ttfb
        else:
            log.debug(f"check_kpi unknown kpi_1, setting to TPS")
            self.kpi_1 = self.rolling_tps

        self.in_kpi_2 = self.in_kpi_2.lower()
        if self.in_kpi_2 == "tps":
            self.kpi_2 = self.rolling_tps
        elif self.in_kpi_2 == "cps":
            self.kpi_2 = self.rolling_cps
        elif self.in_kpi_2 == "conns":
            self.kpi_2 = self.rolling_conns
        elif self.in_kpi_2 == "bw":
            self.kpi_2 = self.rolling_bw
        elif self.in_kpi_2 == "ttfb":
            self.kpi_2 = self.rolling_ttfb
        else:
            log.debug(f"check_kpi unknown kpi_2, setting to CPS")
            self.kpi_2 = self.rolling_cps

    def check_ramp_seek_kpi(self):
        if self.in_ramp_seek_kpi == "tps":
            self.ramp_seek_kpi = self.rolling_tps
        elif self.in_ramp_seek_kpi == "cps":
            self.ramp_seek_kpi = self.rolling_cps
        elif self.in_ramp_seek_kpi == "conns":
            self.ramp_seek_kpi = self.rolling_conns
        elif self.in_ramp_seek_kpi == "bw":
            self.ramp_seek_kpi = self.rolling_bw
        elif self.in_ramp_seek_kpi == "ttfb":
            self.ramp_seek_kpi = self.rolling_ttfb
        else:
            log.debug(f"check_ramp_seek_kpi unknown kpi, setting to TPS")
            self.ramp_seek_kpi = self.rolling_tps

    @staticmethod
    def return_bool_true(check_if, is_value):
        if isinstance(check_if, bool):
            return check_if
        if isinstance(check_if, str) and check_if.lower() == is_value:
            return True
        return False

    def control_test(self):
        """Main test control

        Runs test. Start by checking if test is in running state followed by checking
        for successful connections.
        First updates stats, checks the phase test is in based on elapsed time, then updates
        rolloing averages.

        :return: True if test completed successfully
        """
        # exit control_test if test does not go into running state
        if not self.wait_for_running_status():
            log.info(f"control_test end, wait_for_running_status False")
            return False
        # exit control_test if test does not go into running state
        if not self.wait_for_running_sub_status():
            log.info(f"control_test end, wait_for_running_sub_status False")
            return False
        # exit control_test if test does not have successful transactions
        if not self.wait_for_test_activity():
            self.stop_wait_for_finished_status()
            log.info(f"control_test end, wait_for_test_activity False")
            return False
        self.check_ramp_seek_kpi()
        self.check_kpi()
        self.rolling_count_since_goal_seek.reset()
        # self.countdown(12)
        # test control loop - runs until self.stop is set to True
        while not self.stop:
            self.update_run_stats()
            self.update_phase()
            self.check_stop_conditions()
            self.update_sample_size(3)
            self.update_rolling_averages()
            self.check_highest_pair()
            # print stats if test is running
            if self.sub_status is None:
                self.print_test_stats()
                self.save_results()
            if self.in_ramp_seek and not self.ramp_seek_complete:
                log.info(f"control_test going to ramp_seek")
                self.control_test_ramp_seek(self.ramp_seek_kpi, self.in_ramp_seek_value)

            if self.in_goal_seek and self.ramp_seek_complete:
                log.info(f"control_test going to goal_seek")
                self.control_test_goal_seek_kpi(self.kpi_1, self.kpi_2,
                                                self.in_kpi_and_or)
            print(f"")
            log.info(f"Sleeping {self.stat_sampling_interval} seconds")
            time.sleep(self.stat_sampling_interval)
        # if goal_seek is yes enter sustained steady phase
        if self.in_goal_seek and self.in_sustain_period > 0:
            self.sustain_test()
        # stop test and wait for finished status
        if self.stop_wait_for_finished_status():
            self.time_to_stop = self.timer - self.time_to_stop_start
            self.save_results()
            return True
        return False

    def check_stop_conditions(self):
        log.debug(f"in check_stop_conditions method")
        # stop test if time_remaining returned from controller == 0
        if self.time_remaining == 0:
            self.phase = "timeout"
            log.info(f"control_test end, time_remaining == 0")
            self.stop = True
        # stop goal seeking test if time remaining is less than 30s
        if self.time_remaining < 30 and self.in_goal_seek:
            self.phase = "timeout"
            log.info(f"control_test end goal_seek, time_remaining < 30")
            self.stop = True
        elif self.time_remaining < 30 and self.in_ramp_seek:
            self.phase = "timeout"
            log.info(f"control_test end ramp_seek, time_remaining < 30")
            self.stop = True
        if self.phase == "finished":
            log.info(f"control_test end, over duration time > phase: finished")
            self.stop = True

    def update_sample_size(self, new_sample_size):
        if (self.c_loadspec_avg_cpu > 70 or self.s_memory_avg_cpu > 70) and self.rolling_tps.sample_size != new_sample_size:
           self.rolling_tps.sample_size = new_sample_size
           self.rolling_cps.sample_size = new_sample_size
           self.rolling_load.sample_size = new_sample_size
           self.rolling_conns.sample_size = new_sample_size
           self.rolling_bw.sample_size = new_sample_size
           self.rolling_ttfb.sample_size = new_sample_size
           self.rolling_count_since_goal_seek.sample_size = new_sample_size

    def check_highest_pair(self):
        if self.test_type == "conns":
            if self.c_tcp_established_conns > self.highest_pair["highest_conns"]:
                self.max_load_reached = False
                self.goal_seek_count_after_max_load = 0
                self.highest_pair = {"highest_conns": self.c_tcp_established_conns, "highest_load": self.c_current_load, "highest_desired_load": self.c_desired_load, 
                                     "highest_bw": self.rolling_bw.avg_val, "highest_cps": self.kpi_2.avg_val, "highest_tps": self.kpi_1.avg_val}
        else:
            if self.highest_pair["highest_tps"] != 0:
                if 100 * (self.kpi_1.avg_val - self.highest_pair["highest_tps"]) / self.highest_pair["highest_tps"] >= 0.03: 
                    self.max_load_reached = False
                    self.goal_seek_count_after_max_load = 0
            if self.device_description == "CFV":
              if self.kpi_1.avg_val >= self.highest_pair["highest_tps"] and self.kpi_1.stable:
                  pass
              else:
                  return
            else:
              if self.kpi_1.avg_val > self.highest_pair["highest_tps"] and self.kpi_1.stable:
                  pass
              else:
                  return
            self.highest_pair = {"highest_tps": self.kpi_1.avg_val, "highest_load": self.c_current_load, "highest_desired_load": self.c_desired_load, 
                                 "highest_bw": self.rolling_bw.avg_val, "highest_cps": self.kpi_2.avg_val, "highest_conns": self.c_tcp_established_conns}

    def control_test_ramp_seek(self, ramp_kpi, ramp_to_value):
        """
        Increases load to a configured tps, cps, conns or bandwidth level.
        :return: True if no statements failed and there were no exceptions.
        False otherwise.
        """
        ramp_seek_count = 1
        #log.debug("Inside the RunTest/ramp_to_seek method.")
        log.info(
            f"Inside the RunTest/ramp_to_seek method.\n"
            f"rolling_count_list stable: {self.rolling_count_since_goal_seek.stable} "
            f"list: {self.rolling_count_since_goal_seek.list} "
            f"\nramp_to_value: {ramp_to_value} ramp_kpi current: {ramp_kpi.current_value}"
            f" increase: {ramp_kpi.increase_avg}"
            f"\n current load: {self.c_current_load}"
            f" desired_load: {self.c_desired_load}"
        )
        if self.phase is not "rampseek":
            log.info(f"phase {self.phase} is not 'rampseek', "
                     f"returning from contol_test_ramp_seek")
            return
        if not self.rolling_count_since_goal_seek.stable:
            log.info(f"count since goal seek is not stable. "
                     f"count list: {self.rolling_count_since_goal_seek.list}"
                     f"returning from control_test_ramp_seek")
            return
        if self.max_load_reached:
            log.info(f"control_test_ramp_seek end, max_load_reached")
            self.stop = True
            return
        # check if kpi avg is under set avg - if not, stop loop
        if ramp_to_value < ramp_kpi.current_value:
            log.info(f"ramp_to_value {ramp_to_value} < ramp_kpi.current_value {ramp_kpi.current_value}"
                     f"completed ramp_seek")
            self.ramp_seek_complete = True
            self.in_capacity_adjust = 1
            return

        if self.ramp_seek(ramp_kpi, ramp_to_value):
            # reset rolling count > no load increase until
            # at least the window size interval.
            # allows stats to stabilize after an increase
            self.rolling_count_since_goal_seek.reset()
        else:
            log.info(f"control_test_ramp_seek end, ramp_seek False")
            self.ramp_seek_complete = True
            self.in_capacity_adjust = 1
            return

        if (ramp_kpi.current_value / ramp_to_value) > 0.95:
            log.info(
                f"ramp_kpi.current_value {ramp_kpi.current_value} / "
                f"ramp_to_value {ramp_to_value} > 0.95 "
                f"increasing ramp_seek_count + 1")
            ramp_seek_count = ramp_seek_count + 1
            if ramp_seek_count == self.in_ramp_step:
                log.info(f"ramp_seek_complete early")
                self.ramp_seek_complete = True
                self.in_capacity_adjust = 1
                return
        return

    def control_test_goal_seek_kpi(self, kpi_1,
                                   kpi_2, kpis_and_bool):
        log.info(
            f"\nrolling_count_list stable: {str(self.rolling_count_since_goal_seek.stable):5} "
            f" -list: {self.rolling_count_since_goal_seek.list} "
            f"\nKpi1 {self.in_kpi_1} stable: {str(kpi_1.stable):15}  -list: {kpi_1.list}  unstable_count: {kpi_1.unstable_count}"
            f"\nKpi2 {self.in_kpi_2} stable: {str(kpi_2.stable):15}  -list: {kpi_2.list}     unstable_count: {kpi_2.unstable_count}"
            f"\nKpi1.no_positive_increase_count: {kpi_1.no_positive_increase_count}"
            f"\nload.no_positive_increase_count: {self.rolling_load.no_positive_increase_count}"
            f"\nmax_load_reached is: {self.max_load_reached}, goal_seek_count_after_max_load is : {self.goal_seek_count_after_max_load}"
        )
        if self.phase is not "goalseek":
            log.info(f"phase {self.phase} is not 'goalseek', "
                     f"returning from contol_test_goal_seek")
            return
        if self.c_http_unsuccessful_txns > 0 or self.c_http_aborted_txns > 0:
            log.info(f"Failed transactions: {self.c_http_unsuccessful_txns} (unsucc) and {self.c_http_aborted_txns} (aborted)\n")
            self.stop = True
            return 
        if self.test_type == "conns":
            if self.in_load_type == "SimUsers/Second":
                if kpi_1.stable and self.max_load_reached:
                    self.stop = True
                    return
                elif kpi_1.stable:
                    pass
                else:
                    return
            else:
                log.info(f"Current tps: {self.c_http_successful_txns_sec} -cps: {self.c_tcp_established_conn_rate}")
                if self.c_http_successful_txns_sec == 0 or self.c_tcp_established_conn_rate == 0:
                    log.info(f"Ready for Open Conns goal seeking")
                    pass
                else:
                    log.info(f"Not ready for Open Conns goal seeking, continue to add current load")
                    return 
        elif not self.rolling_count_since_goal_seek.stable:
            log.info(f"count since goal seek is not stable. "
                     f"count list: {self.rolling_count_since_goal_seek.list}")
            return
        else:
            if self.goal_seek_count >= 3 and kpi_1.unstable_count >= 20 and self.c_current_desired_load_variance < 0.97:
                new_load = int(self.new_load_list[-1] - abs(self.load_increase_list[-1])/2)
                self.change_update_load(new_load, self.stat_sampling_interval * 4) 
                self.new_load_list.append(new_load)
                self.load_increase_list.append(self.new_load_list[-1] - self.new_load_list[-2])
                return
        if self.max_load_reached and self.goal_seek_count_after_max_load >= 2:
            log.info(f"control_test end, max_load_reached and goal_seek_count_after_max_load is {self.goal_seek_count_after_max_load}")
            self.stop = True
            return

        if self.test_type == "conns":
            goal_seek = True
        elif self.goal_seek_count <= 2 and kpi_1.unstable_count >= 5:
            goal_seek = True
        else:
          if kpis_and_bool:
            if kpi_1.stable and kpi_2.stable:
                goal_seek = True
            else:
                goal_seek = False
          else:
            if kpi_1.stable or kpi_2.stable:
                goal_seek = True
            else:
                goal_seek = False

        if goal_seek:
            if self.goal_seek():
                # reset rolling count > no load increase until
                # at least the window size interval.
                # allows stats to stabilize after an increase
                self.rolling_count_since_goal_seek.reset()
                self.rolling_load.reset_count()
                kpi_1.reset_count()
                kpi_2.reset_count()
            else:
                log.info(f"control_test end, goal_seek False")
                self.stop = True

    def sustain_test(self):
        self.phase = "steady"
        if self.highest_pair["highest_desired_load"] != 0:
            self.cf.change_load(self.id, self.highest_pair["highest_desired_load"])
            log.info(f"Sleeping {self.stat_sampling_interval*4} seconds")
            time.sleep(self.stat_sampling_interval*4)
        while self.in_sustain_period > 0:
            self.timer = int(round(time.time() - self.start_time))
            sustain_period_loop_time_start = time.time()
            self.update_run_stats()
            self.update_rolling_averages()
            if self.time_remaining < 30 and self.in_goal_seek:
                self.phase = "timeout"
                self.in_sustain_period = 0
                log.info(f"sustain_test end, time_remaining < 30")
            # self.update_averages()
            print(f"sustain period time left: {int(self.in_sustain_period)}")

            # print stats if test is running
            if self.sub_status is None:
                self.print_test_stats()
                self.save_results()

            log.info(f"Sleeping {self.stat_sampling_interval} seconds")
            time.sleep(self.stat_sampling_interval)
            self.in_sustain_period = self.in_sustain_period - (
                time.time() - sustain_period_loop_time_start
            )
        self.phase = "stopping"
        # self.stop_wait_for_finished_status()
        return True

    def save_results(self):

        csv_list = [
            self.in_name,
            self.time_elapsed,
            self.phase,
            self.c_current_load,
            self.c_desired_load,
            self.rolling_count_since_goal_seek.stable,
            self.c_http_successful_txns_sec,
            self.rolling_tps.stable,
            self.rolling_tps.increase_avg,
            self.c_http_successful_txns,
            self.c_http_unsuccessful_txns,
            self.c_http_aborted_txns,
            self.c_transaction_error_percentage,
            self.c_tcp_established_conn_rate,
            self.rolling_cps.stable,
            self.rolling_cps.increase_avg,
            self.c_tcp_established_conns,
            self.rolling_conns.stable,
            self.rolling_conns.increase_avg,
            self.c_tcp_avg_tt_synack,
            self.c_tcp_avg_ttfb,
            self.rolling_ttfb.stable,
            self.rolling_ttfb.increase_avg,
            self.c_url_avg_response_time,
            self.c_tcp_cumulative_established_conns,
            self.c_tcp_cumulative_attempted_conns,
            self.c_total_bandwidth,
            self.rolling_bw.stable,
            self.rolling_bw.increase_avg,
            self.c_rx_bandwidth,
            self.c_tx_bandwidth,
            self.c_rx_packet_rate,
            self.c_tx_packet_rate,
            self.s_tcp_closed,
            self.s_tcp_closed_reset,
            self.s_tcp_closed_error,
            self.c_simusers_alive,
            self.c_simusers_animating,
            self.c_simusers_blocking,
            self.c_simusers_sleeping,
            self.c_loadspec_avg_cpu,
            self.c_memory_percent_used,
            self.c_memory_packetmem_used,
            self.c_memory_rcv_queue_length,
            self.s_memory_avg_cpu,
            self.s_memory_percent_used,
            self.s_memory_packetmem_used,
            self.s_memory_rcv_queue_length,
            self.type_v1,
            self.type_v2,
            self.in_load_type,
            self.test_id,
            self.id,
            self.time_to_run,
            self.time_to_start,
            self.time_to_activity,
            self.time_to_stop,
            script_version,
            self.report_link,
        ]
        self.result_file.append_file(csv_list)


class DetailedCsvReport:
    def __init__(self, report_location):
        log.debug("Initializing detailed csv result files.")
        self.time_stamp = time.strftime("%Y%m%d-%H%M")
        log.debug(f"Current time stamp: {self.time_stamp}")
        self.report_location_parent = report_location
        #self.report_csv_file = report_location / f"{self.time_stamp}_Detailed.csv"
        #self.report_csv_file_orig = self.report_csv_file
        self.columns = [
            "test_name",
            "seconds",
            "state",
            "current_load",
            "desired_load",
            "seek_ready",
            "tps",
            "tps_stable",
            "tps_delta",
            "successful_txn",
            "unsuccessful_txn",
            "aborted_txn",
            "txn_error_rate",
            "cps",
            "cps_stable",
            "cps_delta",
            "open_conns",
            "conns_stable",
            "conns_delta",
            "tcp_avg_tt_synack",
            "tcp_avg_ttfb",
            "ttfb_stable",
            "ttfb_delta",
            "url_response_time",
            "total_tcp_established",
            "total_tcp_attempted",
            "total_bandwidth",
            "bw_stable",
            "bw_delta",
            "rx_bandwidth",
            "tx_bandwidth",
            "rx_packet_rate",
            "tx_packet_rate",
            "tcp_closed",
            "tcp_reset",
            "tcp_error",
            "simusers_alive",
            "simusers_animating",
            "simusers_blocking",
            "simusers_sleeping",
            "client_cpu",
            "client_mem",
            "client_pkt_mem",
            "client_rcv_queue",
            "server_cpu",
            "server_mem",
            "server_pkt_mem",
            "server_rcv_queue",
            "test_type_v1",
            "test_type_v2",
            "load_type",
            "test_id",
            "run_id",
            "t_run",
            "t_start",
            "t_tx",
            "t_stop",
            "version",
            "report",
        ]

    def append_columns(self):
        """
        Appends the column headers to the detailed report file.
        :return: no specific return value.
        """
        try:
            csv_header = ",".join(map(str, self.columns)) + "\n"
            with open(self.report_csv_file, "a") as f:
                f.write(csv_header)
        except Exception as detailed_exception:
            log.error(
                f"Exception occurred  writing to the detailed report file: \n<{detailed_exception}>\n"
            )
        log.debug(
            f"Successfully appended columns to the detailed report file: {self.report_csv_file}."
        )

    def append_file(self, csv_list):
        """
        Appends the detailed report csv file with csv_line.
        :param csv_list: items to be appended as line to the file.
        :return: no specific return value.
        """
        try:
            csv_line = ",".join(map(str, csv_list)) + "\n"
            with open(self.report_csv_file, "a") as f:
                f.write(csv_line)
        except Exception as detailed_exception:
            log.error(
                f"Exception occurred  writing to the detailed report file: \n<{detailed_exception}>\n"
            )

    def make_report_csv_file(self, new_report_csv_name):
        new_report_csv_name = self.report_location / f"{new_report_csv_name}_{self.time_stamp}_Detailed.csv"
        if new_report_csv_name.is_file():
            return
        else:
            self.report_csv_file = new_report_csv_name
            self.append_columns()

    def make_report_dir(self, report_dir_name):
        report_dir = self.report_location_parent / report_dir_name
        if report_dir.is_dir():
            pass
        else:
            report_dir.mkdir(parents=False, exist_ok=True)
        self.report_location = report_dir

class Report:
    def __init__(self, report_csv_file, column_order):
        self.report_csv_file = report_csv_file
        self.col_order = column_order
        self.df_base = pd.read_csv(self.report_csv_file)
        self.df_steady = self.df_base[self.df_base.state == "steady"].copy()
        self.unique_tests = self.df_base["test_name"].unique().tolist()
        self.results = []
        self.process_results()
        self.format_results()
        self.df_results = pd.DataFrame(self.results)
        self.df_results = self.df_results.reindex(columns=self.col_order)
        self.df_filter = pd.DataFrame(self.df_results)

    def process_results(self):
        for name in self.unique_tests:
            d = {}
            d["test_name"] = name

            # get mean values from steady state
            mean_cols = [
                "cps",
                "tps",
                "total_bandwidth",
                "open_conns",
                "tcp_avg_tt_synack",
                "tcp_avg_ttfb",
                "url_response_time",
                "client_cpu",
                "client_pkt_mem",
                "client_rcv_queue",
                "server_cpu",
                "server_pkt_mem",
                "server_rcv_queue",
            ]
            for col in mean_cols:
                d[col] = self.df_steady.loc[
                    self.df_steady["test_name"] == name, col
                ].mean()

            # get maximum values for all states
            max_cols = [
                "successful_txn",
                "unsuccessful_txn",
                "aborted_txn",
                "total_tcp_established",
                "total_tcp_attempted",
                "seconds",
                "current_load",
                "t_run",
                "t_start",
                "t_tx",
                "t_stop",
            ]
            for col in max_cols:
                d[col] = self.df_base.loc[self.df_base["test_name"] == name, col].max()

            max_steady_cols = ["seconds"]
            for col in max_steady_cols:
                d[col] = self.df_steady.loc[
                    self.df_steady["test_name"] == name, col
                ].max()

            # checks steady vs. all state max, add _max to column name
            max_compare_cols = ["cps", "tps", "total_bandwidth"]
            for col in max_compare_cols:
                col_name = col + "_max"
                d[col_name] = self.df_base.loc[
                    self.df_base["test_name"] == name, col
                ].max()
            # find current_load and seconds for max tps
            d["max_tps_load"] = self.df_base.loc[
                self.df_base["tps"] == d["tps_max"], "current_load"
            ].iloc[0]
            d["max_tps_seconds"] = self.df_base.loc[
                self.df_base["tps"] == d["tps_max"], "seconds"
            ].iloc[0]
            # get script version from test
            d["version"] = self.df_base.loc[self.df_base["test_name"] == name, "version"].iloc[0]

            # get report link for current test - changed to take from last row in test
            # d["report"] = self.df_base.loc[self.df_base["tps"] == d["tps_max"], "report"].iloc[0]
            d["report"] = self.df_base.loc[self.df_base["test_name"] == name, "report"].iloc[-1]

            # find min and max tps from steady phase
            max_steady_compare = ["tps"]
            for col in max_steady_compare:
                col_name_min = col + "_stdy_min"
                col_name_max = col + "_stdy_max"
                col_name_delta = col + "_stdy_delta"
                d[col_name_min] = self.df_steady.loc[
                    self.df_steady["test_name"] == name, col
                ].min()
                d[col_name_max] = self.df_steady.loc[
                    self.df_steady["test_name"] == name, col
                ].max()

                if d[col_name_min] != 0:
                    d[col_name_delta] = (
                        (d[col_name_max] - d[col_name_min]) / d[col_name_min]
                    ) * 100

                    d[col_name_delta] = round(d[col_name_delta], 3)
                else:
                    d[col_name_delta] = 0

            self.results.append(d)

    def reset_df_filter(self):
        self.df_filter = pd.DataFrame(self.df_results)

    def filter_rows_containing(self, test_name_contains):
        if test_name_contains is not None:
            self.df_filter = self.df_filter[
                self.df_filter.test_name.str.contains(test_name_contains)
            ].copy()

    def filter_columns(self, filtered_columns):
        if filtered_columns is not None:
            self.df_filter.drop(
                self.df_filter.columns.difference(filtered_columns), 1, inplace=True
            )

    def format_results(self):
        for row_num, row in enumerate(self.results):
            for key, value in row.items():
                if key in {
                    "cps",
                    "tps",
                    "total_bandwidth",
                    "open_conns",
                    "successful_txn",
                    "unsuccessful_txn",
                    "aborted_txn",
                    "total_tcp_established",
                    "total_tcp_attempted",
                    "tps_stdy_min",
                    "tps_stdy_max",
                    "cps_max",
                    "tps_max",
                    "total_bandwidth_max",
                    "max_tps_load",
                    "client_mem",
                    "client_pkt_mem",
                    "client_rcv_queue",
                    "server_mem",
                    "server_pkt_mem",
                    "server_rcv_queue",
                    "t_run",
                    "t_start",
                    "t_tx",
                    "t_stop",
                }:
                    self.results[row_num][key] = f"{value:,.0f}"
                elif key in {
                    "tcp_avg_ttfb",
                    "url_response_time",
                    "tcp_avg_tt_synack",
                    "client_cpu",
                    "server_cpu",
                }:
                    self.results[row_num][key] = f"{value:,.1f}"
                elif key in {"tps_stdy_delta"}:
                    self.results[row_num][key] = f"{value:,.2f}"
                elif key in {"report"}:
                    self.results[row_num][key] = f'<a href="{value}">link</a>'

    @staticmethod
    def style_a():
        styles = [
            # table properties
            dict(
                selector=" ",
                props=[
                    ("margin", "0"),
                    ("width", "100%"),
                    ("font-family", '"Helvetica", "Arial", sans-serif'),
                    ("border-collapse", "collapse"),
                    ("border", "none"),
                    ("border", "2px solid #ccf"),
                    # ("min-width", "600px"),
                    ("overflow", "auto"),
                    ("overflow-x", "auto"),
                ],
            ),
            # header color - optional
            dict(
                selector="thead",
                props=[
                    ("background-color", "SkyBlue"),
                    ("width", "100%")
                    # ("display", "table") # adds fixed scrollbar
                    # ("position", "fixed")
                ],
            ),
            # background shading
            dict(
                selector="tbody tr:nth-child(even)",
                props=[("background-color", "#fff")],
            ),
            dict(
                selector="tbody tr:nth-child(odd)", props=[("background-color", "#eee")]
            ),
            # cell spacing
            dict(selector="td", props=[("padding", ".5em")]),
            # header cell properties
            dict(
                selector="th",
                props=[
                    ("font-size", "100%"),
                    ("text-align", "center"),
                    ("min-width", "25px"),
                    ("max-width", "50px"),
                    ("word-wrap", "break-word"),
                ],
            ),
            # render hover last to override background-color
            dict(selector="tbody tr:hover", props=[("background-color", "SkyBlue")]),
        ]
        return styles

    def html_table(self, selected_style):
        # Style
        props = {
            "test_name": {"width": "20em", "min-width": "14em", "text-align": "left"},
            "cps": {"width": "6em", "min-width": "5em", "text-align": "right"},
            "tps": {"width": "6em", "min-width": "5em", "text-align": "right"},
            "cps_max": {"width": "6em", "min-width": "5em", "text-align": "right"},
            "tps_max": {"width": "6em", "min-width": "5em", "text-align": "right"},
            "total_bandwidth": {
                "width": "8em",
                "min-width": "7em",
                "text-align": "right",
            },
            "total_bandwidth_max": {
                "width": "8em",
                "min-width": "7em",
                "text-align": "right",
            },
            "open_conns": {"width": "8em", "min-width": "7em", "text-align": "right"},
            "tcp_avg_tt_synack": {
                "width": "3.7em",
                "min-width": "3.7em",
                "text-align": "right",
            },
            "tcp_avg_ttfb": {
                "width": "3.7em",
                "min-width": "3.7em",
                "text-align": "right",
            },
            "url_response_time": {
                "width": "3.7em",
                "min-width": "3.7em",
                "text-align": "right",
            },
            "report": {"width": "3.7em", "min-width": "3.7em", "text-align": "right"},
            "successful_txn": {
                "width": "8em",
                "min-width": "7em",
                "text-align": "right",
            },
            "total_tcp_established": {
                "width": "5em",
                "min-width": "5em",
                "text-align": "right",
            },
            "total_tcp_attempted": {
                "width": "5em",
                "min-width": "5em",
                "text-align": "right",
            },
            "seconds": {"width": "3.7em", "min-width": "3.7em", "text-align": "right"},
            "tps_stdy_min": {"width": "3.2em", "min-width": "3.2em", "text-align": "right"},
            "tps_stdy_max": {"width": "3.2em", "min-width": "3.2em", "text-align": "right"},
            "tps_stdy_delta": {
                "width": "3.2em",
                "min-width": "3.2em",
                "text-align": "right",
            },
            "client_cpu": {"width": "3em", "min-width": "3em", "text-align": "right"},
            "server_cpu": {"width": "3em", "min-width": "3em", "text-align": "right"},
            "client_pkt_mem": {
                "width": "3.5em",
                "min-width": "3.5em",
                "text-align": "right",
            },
            "client_rcv_queue": {
                "width": "3.5em",
                "min-width": "3.5em",
                "text-align": "right",
            },
            "server_pkt_mem": {
                "width": "3.9em",
                "min-width": "3.9em",
                "text-align": "right",
            },
            "server_rcv_queue": {
                "width": "3.9em",
                "min-width": "3.9em",
                "text-align": "right",
            },
            "current_load": {
                "width": "3.7em",
                "min-width": "3.7em",
                "text-align": "right",
            },
            "unsuccessful_txn": {
                "width": "3.8em",
                "min-width": "3.8em",
                "text-align": "right",
            },
            "aborted_txn": {
                "width": "3.5em",
                "min-width": "3.5em",
                "text-align": "right",
            },
            "max_tps_seconds": {
                "width": "3.7em",
                "min-width": "3.7em",
                "text-align": "right",
            },
            "max_tps_load": {
                "width": "3.7em",
                "min-width": "3.7em",
                "text-align": "right",
            },
            "t_run": {"width": "3em", "min-width": "3.7em", "text-align": "right"},
            "t_start": {"width": "3em", "min-width": "3em", "text-align": "right"},
            "t_tx": {"width": "3em", "min-width": "3em", "text-align": "right"},
            "t_stop": {"width": "3em", "min-width": "3em", "text-align": "right"},
            "version": {"width": "3em", "min-width": "3em", "text-align": "right"},
        }

        # html = ''
        all_columns = set(self.df_filter.columns)
        html = self.df_filter.style.set_properties(
            subset="test_name", **props["test_name"]
        )
        for k, v in props.items():
            if k in all_columns:
                html = html.set_properties(subset=k, **v)
        html = html.set_table_styles(selected_style).hide_index().render()

        return html
