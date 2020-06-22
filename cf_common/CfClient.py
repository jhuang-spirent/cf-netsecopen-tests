import requests
import json
import logging
import sys
import os 
import pathlib
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

fmt_str = "[%(asctime)s] %(levelname)s %(lineno)d: %(message)s"
input_dir = "."
for path in sys.path:
    if "cf_runtests/input/CF_" in path:
        input_dir = path 
logfile = str(input_dir) + "/cf.log"
logging.basicConfig(filename = logfile, filemode="a", level=logging.DEBUG, format=fmt_str)
log = logging.getLogger(__name__)
log.debug("start logging")
print('*'*100)
print(f"Log file: {logfile}")

class CfClient:
    def __init__(self, controller_ip, username, password, verify_ssl):
        log.debug("Initializing a new object of the CfClient class.")
        self.log = logging.getLogger("requests.packages.urllib3")
        self.username = username
        self.password = password
        self.controller_ip = controller_ip
        self.api = "https://" + self.controller_ip + "/api/v2"
        self.__session = requests.session()
        self.__session.verify = verify_ssl
        self.exception_state = True
        retries = Retry(
            total=5, backoff_factor=1, status_forcelist=[422, 500, 502, 503, 504]
        )
        self.__session.mount("https://", HTTPAdapter(max_retries=retries))

    def connect(self):
        self.exception_state = True
        log.debug("Inside the CfClient/connect method.")
        credentials = {"email": self.username, "password": self.password}
        try:
            response = self.__session.post(
                self.api + "/token", data=credentials, timeout=10
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        #print(dict_response)
        if "token" in dict_response:
            self.__session.headers["Authorization"] = "Bearer " + dict_response["token"]

    def get_test(self, test_type, test_id, outfile):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + "/tests/" + test_type + "/" + test_id
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response


    def get_queue_list(self, outfile):
        try:
            response = self.__session.get(
                self.api + "/queues"
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response

    def get_queue(self, queue_id):
        self.exception_state = True
        try:
            response = self.__session.get(self.api + "/queues/" + queue_id)
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def get_queue_info(self, queue_id, outfile):
        try:
            response = self.__session.get(
                self.api + "/queues/" + queue_id
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response

    def create_queue(self, indict):
        self.exception_state = True
        try:
            response = self.__session.post(
                self.api + "/queues", json=indict
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def get_device_list(self, outfile):
        try:
            response = self.__session.get(
                self.api + "/devices/"
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response

    def get_device_info(self, device_id, outfile):
        try:
            response = self.__session.get(
                self.api + "/devices/" + device_id
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response


    def get_subnet(self, ip_version, profile_id, outfile):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + "/profiles/subnets/" + ip_version + "/" + profile_id
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response

    def post_subnet(self, ip_version, indict):
        self.exception_state = True
        try:
            response = self.__session.post(
                self.api + "/profiles/subnets/" + ip_version, json=indict
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        #print(f"{dict_response}")
        return dict_response


    def get_subnets_list(self, ip_version, outfile):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + "/profiles/subnets/" + ip_version
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        #print(f"{dict_response}")
        return dict_response

    def get_project(self, project_id, outfile):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + "/projects/" + project_id
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response

    def fetch_test_template(self, test_type, outfile):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + "/tests/" + test_type + "/template"
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        dict_response = response.json()
        with open(outfile, "w") as f:
            json.dump(dict_response, f, indent=4)
        return dict_response

    def configure_test_queue(self, infile, new_queue):
        with open(infile, "r") as f:
            intest = json.load(f)
        #    print(intest)
        intest["config"]["queue"] = {"id": new_queue, "name": new_queue}
        with open(infile, "w") as f:
            json.dump(intest, f, indent=4)
        return True

    def configure_test_interfaces(self, infile, new_interfaces, connection):
        with open(infile, "r") as f:
            intest = json.load(f)
        #    print(intest)
        length = len(intest["config"]["interfaces"]["client"])
        length1 = len(new_interfaces[0])
        length2 = len(new_interfaces)
        connection = connection.lower()
        if connection == "c2c":
            if length > length1:
                print("Ports are not enough")
                return False
            for i in range(0, length):
                intest["config"]["interfaces"]["client"][i]["portSystemId"] = new_interfaces[0][i]
                intest["config"]["interfaces"]["server"][i]["portSystemId"] = new_interfaces[1][i]
        if connection == "p2p":
          if length > length2:
              print("Ports are not enough")
              return False
          for i in range(0, length):
                intest["config"]["interfaces"]["client"][i]["portSystemId"] = new_interfaces[i][0]
                intest["config"]["interfaces"]["server"][i]["portSystemId"] = new_interfaces[i][1]
        with open(infile, "w") as f:
            json.dump(intest, f, indent=4)
        return True

    def get_CI_ipv6_subnet(self, pair, outfile):
        ipv6_subnet = {"client": [], "server": []}
        ipv6_subnet_name_needed = []
        ipv6_subnet_name_available = []
        for i in range(1, pair + 1):
            ipv6_subnet_name_needed.append(f"Client_IPv6_CI_{i}")
            ipv6_subnet_name_needed.append(f"Server_IPv6_CI_{i}")
        all_ipv6_subnet = self.get_subnets_list("ipv6", outfile)
        for subnet in all_ipv6_subnet:
            if subnet["name"] in ipv6_subnet_name_needed:
                ipv6_subnet_name_available.append(subnet["name"])
        if len(ipv6_subnet_name_available) < 2 * pair:
            ipv6_subnet_template = self.get_ipv6_subnet_template(pair)
            for i in range(0, len(ipv6_subnet_template)):
                if ipv6_subnet_template[i]["name"] in ipv6_subnet_name_available:
                    continue
                else:
                    print(f"Creating IPv6 subnets for {ipv6_subnet_template[i]['name']}")
                    self.post_subnet("ipv6", ipv6_subnet_template[i])
            all_ipv6_subnet = self.get_subnets_list("ipv6", outfile)
        for subnet in all_ipv6_subnet:
            subnet_detail = {}
            if subnet["name"] in ipv6_subnet_name_needed:
                subnet_detail = self.get_subnet("ipv6", subnet["id"], outfile)
                subnet_detail["type"] = "ipv6"
                if "client" in subnet["name"].lower():
                    ipv6_subnet["client"].append(subnet_detail)
                if "server" in subnet["name"].lower():
                    ipv6_subnet["server"].append(subnet_detail)
        return ipv6_subnet

    @staticmethod
    def get_ipv6_subnet_template(pair):
        j = 0
        ipv6_subnet_template = []
        for i in range(1, pair + 1):
          for item in ["Client", "Server"]:
            ipv6_subnet_template.append(
                {"name": f"{item}_IPv6_CI_{i}",
                 "addressing": {
                     "type": "static",
                     "address": f"7ffe::200:ff:fe0{j}:2",
                     "netmask": 64,
                     "count": 255,
                     "forceIpAllocation": False
                  },
                 "mld": 2,
                }
              )
            j = j+1
        return ipv6_subnet_template

    @staticmethod
    def get_ipv6_subnet_template_virtual(instance_type, client_address, server_address):
        ipv6_subnet_template = []
        ipv6_address ={"AWS": {"Client": "2600:1f18:6787:5865:5202:89d5:6953:cb93", 
                               "Server": "2600:1f18:6787:5866:8550:6b91:768c:5262"
                                },
                       "Azure": {"Client": "2600:1f18:6787:5865:5202:89d5:6953:cb93", 
                                 "Server": "2600:1f18:6787:5866:8550:6b91:768c:5262"
                                },
                       "GCP": {"Client": "2600:1f18:6787:5865:5202:89d5:6953:cb93", 
                               "Server": "2600:1f18:6787:5866:8550:6b91:768c:5262"
                                }
                       }
        if client_address:
            ipv6_address[instance_type]["Client"] = client_address
        if server_address:
            ipv6_address[instance_type]["Server"] = server_address
        for item in ["Client", "Server"]:
            ipv6_subnet_template.append(
            {"name": f"{instance_type}_{item}_IPv6_CI",
             "addressing": {
                "type": "static",
                "address": ipv6_address[instance_type][item],
                "netmask": 64,
                "count": 15,
                "forceIpAllocation": False
                },
             "mld": 2,
             }
            )
        return ipv6_subnet_template

    @staticmethod
    def get_ipv4_vlan_subnet_template(instance_type):
        if instance_type in ["AWS", "GCP", "Azure"]:
            vlan_name = ""
            vlans_value = []
        else:
            vlan_name = "vlan_"
            vlans_value = [{ 
                            "id": 12,
                           }]
        address = "10.10.101.2"
        ipv4_vlan_subnet_template = []
        for item in ["Client", "Server"]:
            if item == "Server":
                address = "10.10.102.2"
            ipv4_vlan_subnet_template.append(
                {"name": f"{item}_IPv4_{vlan_name}CI",
                 "addressing": {
                     "type": "custom",
                     "address": address,
                     "netmask": 24,
                     "count": 253,
                    },
                 "vlans": vlans_value
                 }
              )
        return ipv4_vlan_subnet_template


    def post_test(self, test_type, infile):
        self.exception_state = True
        with open(infile, "r") as f:
            intest = json.load(f)
        try:
            response = self.__session.post(
                self.api + "/tests/" + test_type + "/", json=intest
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        print(response)
        dict_response = response.json()
        return dict_response

    def update_test(self, test_type, test_id, infile):
        self.exception_state = True
        with open(infile, "r") as f:
            intest = json.load(f)
        #    print(intest)
        try:
            response = self.__session.put(
                self.api + "/tests/" + test_type + "/" + test_id, json=intest
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        if "Error" not in dict_response and 'type' not in dict_response:
            print("Update Successfully")
        else:
            print("Update Failed")
        return dict_response

    def delete_test(self, test_type, test_id):
        self.exception_state = True
        try:
            response = self.__session.delete(
                self.api + "/tests/" + test_type + "/" + test_id
            )
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        return response

    def start_test(self, test_id):
        self.exception_state = True
        #Command = "date +%s%3N"
        #ClickStart,lError,lExitStatus=SSHCommand(self.controller_ip,"qiaoqihu","Spirent123",Command)
        #print(f"Controller ClickStart time is: {ClickStart}")
        try:
            response = self.__session.put(self.api + "/tests/" + test_id + "/start")
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def list_test_runs(self):
        self.exception_state = True
        try:
            response = self.__session.get(self.api + "/test_runs")
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def get_test_run(self, test_run_id):
        self.exception_state = True
        try:
            response = self.__session.get(self.api + "/test_runs/" + test_run_id)
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def get_testrun_results(self, testRunId, outfile):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + f"/test_runs/{testRunId}/results"
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)

        list_response = response.json()
        with open(outfile, "w") as f:
            json.dump(list_response, f, indent=4)
        return list_response

    def get_test_result_zip(self, testRunId, testRunResultId, outdir):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + f"/test_runs/{testRunId}/results/{testRunResultId}/logs"
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        content_disposition = response.headers.get('content-disposition')
        print(f"content disposition is: {content_disposition}")
        fname = content_disposition.split("attachment; filename=")[-1].strip('"')
        if os.path.isdir(outdir):
            pass
        else:
            os.mkdir(outdir)
        resultpath = outdir / fname
        open(resultpath, 'wb').write(response.content)
        return resultpath

    def fetch_test_run_statistics(self, test_run_id):
        self.exception_state = True
        try:
            response = self.__session.get(
                self.api + "/test_runs/" + test_run_id + "/statistics"
            )
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def stop_test(self, test_run_id):
        self.exception_state = True
        try:
            response = self.__session.put(
                self.api + "/test_runs/" + test_run_id + "/stop"
            )
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def change_load(self, test_run_id, new_load):
        self.exception_state = True
        load = {"load": new_load}
        try:
            response = self.__session.put(
                self.api + "/test_runs/" + test_run_id + "/changeload", data=load
            )
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        log.debug(f"change load: {load} > {json.dumps(dict_response, indent=4)}")
        return dict_response

    def get_system_version(self):
        self.exception_state = True
        try:
            response = self.__session.get(self.api + "/system/version")
        except requests.exceptions.HTTPError as errh:
            self.requests_error_handler("http", errh, response)
        except requests.exceptions.ConnectionError as errc:
            self.requests_error_handler("connection", errc, None)
        except requests.exceptions.Timeout as errt:
            self.requests_error_handler("timeout", errt, None)
        except requests.exceptions.RequestException as err:
            self.requests_error_handler("other", err, None)
        self.exception_continue_check()
        dict_response = response.json()
        return dict_response

    def requests_error_handler(self, error_type, error_response, json_response):
        if error_type == "http":
            report_error = f"Http Error: {error_response}"
        elif error_type == "connection":
            report_error = f"Error Connecting: {error_response}"
        elif error_type == "timeout":
            report_error = f"Timeout Error: {error_response}"
        elif error_type == "other":
            report_error = (
                f"Other error, not http, connection or timeout error: {error_response}"
            )
        else:
            report_error = f"unknown"

        log.debug(report_error)
        print(report_error)
        if json_response is not None:
            log.debug(json_response.json())
            print(json_response.json())
        # sys.exit(1)
        self.exception_state = False

    def exception_continue_check(self):
        if not self.exception_state:
            #sys.exit(1)
            return
