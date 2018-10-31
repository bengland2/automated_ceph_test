
import yaml, os, time, json, hashlib, paramiko
import socket, datetime, logging, rados, ipaddress
from paramiko import SSHClient
from elasticsearch.client.remote import RemoteClient

logger = logging.getLogger("index_cbt")

class cbt_config_transcriber:
    
    def __init__(self, test_id, cbt_yaml_config):
        self.test_id = test_id 
        self.config = yaml.load(open(cbt_yaml_config))   
        self.config_file = cbt_yaml_config
        self.host_map = {}
        
        try:
            self.acitve_ceph_client = ceph_client()
        except:
            logger.warn("Unable to establish a connection to ceph")   
         
        if self.acitve_ceph_client.Connection_status:   
            self.remoteclient = ssh_remote_command()
    
            
            self.make_host_map()
        else:
            logger.warn("Ceph host to role mapping was not performed.")

            
    def set_host_type_list(self):
        
        host_type_list = ""
        
        for host in self.host_map:
            host_type_list = ""
            for child in self.host_map[host]['children']:
                if child['service_type'] not in host_type_list:
                    host_type_list += "%s," % str(child['service_type'])
                    
            self.host_map[host]['host_type_list'] = host_type_list
    
    def get_host_info(self, hostname_or_ip):
        if self.acitve_ceph_client.Connection_status: 
            host_fqdn = self.get_fqdn(self.remoteclient, hostname_or_ip)   
            for host in self.host_map:
                if host_fqdn in host:
                    return self.host_map[host]               
        else:
            empty_dict = {}
            return empty_dict
        
    def get_host_type(self, host):
        
        if self.acitve_ceph_client.Connection_status:
            try:
                host_fqdn = self.get_fqdn(self.remoteclient, host)
                host_info = self.get_host_info(host_fqdn)
                return host_info['host_type_list']
            except:
                logger.warn("Unable to get host type list for %s" % host_fqdn)
        else:
            return "UNKOWN"
        
    def make_host_map(self):
        logger.debug("getting ceph node map")
        ceph_node_map = self.acitve_ceph_client.issue_command("node ls")
        logger.debug("getting client list")
        client_list = self.config['cluster']['clients']
        
        ceph_role_list = ['mds', 'mon', 'osd', 'mgr']
        for role in ceph_role_list:
            host_role_list = self.acitve_ceph_client.issue_command("%s metadata" % role)
            #print json.dumps(host_role_list, indent=4)
            
            if len(host_role_list) > 0:
                for role_info in host_role_list:
                    #print role_info['hostname']
                    host_fqdn = self.get_fqdn(self.remoteclient, role_info['hostname'])
                    
                    child = {}
                    child['service_type'] = role
                    
                    if "mon" in role:
                        service_id = str(role_info['name'])
                    elif "osd" in role or "mgr" in role:
                        service_id = str(role_info['id'])
                        
                    child['service_id'] = service_id
                    child['service_pid'] = self.get_ceph_service_pid(self.remoteclient, host_fqdn, role, service_id)                
                    
                    if host_fqdn not in self.host_map:
                        self.host_map[host_fqdn] = {}
                        self.host_map[host_fqdn]['children'] = [] 
                        #get interface dict
                        self.host_map[host_fqdn]['interfaces'] = self.get_interfaces(self.remoteclient, host_fqdn)
                        #get cpuinfo dict
                        self.host_map[host_fqdn]['cpu_info'] = self.get_cpu_info(self.remoteclient, host_fqdn)
                        
                    if child not in self.host_map[host_fqdn]['children']:
                        self.host_map[host_fqdn]['children'].append(child)
                    
        
        if client_list:
            for client in client_list:
                
                client_fqdn = self.get_fqdn(self.remoteclient, client)
                child = {}
                child['service_type'] = "client"
                child['service_pid'] = "-1"
                child['service_id'] = -1
                    
                if client_fqdn not in self.host_map:
                    self.host_map[client_fqdn] = {}                
                    self.host_map[client_fqdn]['children'] = []
                    try:
                        #get interface dict
                        self.host_map[client_fqdn]['interfaces'] = self.get_interfaces(self.remoteclient, client_fqdn)
                        #get cpuinfo dict
                        self.host_map[client_fqdn]['cpu_info'] = self.get_cpu_info(self.remoteclient, client_fqdn)
                    except:
                        logger.debug("unable to reach client - %s" % client_fqdn) 
                    
                    
                        
                self.host_map[client_fqdn]['children'].append(child)
        self.set_host_type_list()
        
        #print json.dumps(self.host_map, indent=4)
        
    def get_fqdn(self, remoteclient, host):
        output = remoteclient.issue_command(host, "hostname -f")
        output = output[0].strip()
        return output
        
    def get_cpu_info(self, remoteclient, host):
        output = remoteclient.issue_command(host, "lscpu")
        cpu_info_dict = {}
        
        for line in output:
            #print line
            seperated_line = line.split(":")
            #print seperated_line
            cpu_prop = seperated_line[0].strip()
            cpu_prop_value = seperated_line[1].strip()
            
            if "NUMA node" in cpu_prop and "CPU(s)" in cpu_prop:
                cpu_info_dict[cpu_prop] = []
                split_values = cpu_prop_value.split(",")
                for value in split_values:
                    cpu_info_dict[cpu_prop].append(value)
            elif "Flags" not in cpu_prop:
                cpu_info_dict[cpu_prop] = cpu_prop_value  
        
        return cpu_info_dict    
    
    def get_interfaces(self, remoteclient, host):
        output = remoteclient.issue_command(host, "ip a")
        interface_dict = {}
        for line in output:
            seperated_line = line.split(" ")
            
            #Get interface name
            if seperated_line[0].strip(":").isdigit():
                interface_name = seperated_line[1]
                interface_dict[interface_name] = []
            
            #Get IPv4 for interface 
            if "inet" in line and not "inet6" in line:
                ipindex = seperated_line.index("inet") + 1
                ip_address = seperated_line[ipindex]
                interface_dict[interface_name].append(ip_address)
            
        #return a dict of all interfaces:IPaddresses
        return interface_dict

    def get_ceph_service_pid(self, remoteclient, host, service, id):
        pid_grep_command = "ps -eaf | grep %s | grep 'id %s ' | grep -v grep| awk '{print $2}'" % (service, id)
        output = remoteclient.issue_command(host, pid_grep_command)
        return output[0]
    
    def emit_actions(self):
        
        logger.debug("Indexing %s" % self.config_file)
        importdoc = {}
        importdoc["_index"] = "cbt_config-test1"
        importdoc["_type"] = "cbt_config_data"
        importdoc["_op_type"] = "create"
        importdoc["_source"] = { 'ceph_benchmark_test': 
                                { "common": 
                                 { 
                                     "test_info": 
                                     { 
                                         "test_id": self.test_id }
                                     }
                                 }, 
                              #  "ceph_config": self.host_map,
                                "cbt_config": self.config
                                }
        #importdoc["_source"]['ceph_benchmark_test']['cbt_config'] = self.config
        #importdoc["_source"]['ceph_benchmark_test']['test_id'] = self.test_id
        
        file_time = os.path.getmtime(self.config_file)
        file_time = datetime.datetime.fromtimestamp(file_time)
        importdoc['_source']['date'] = file_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        
        importdoc["_id"] = hashlib.md5(json.dumps(importdoc)).hexdigest()
        yield importdoc    
        

class ssh_remote_command():
    def __init__(self):
          self.sshclient = SSHClient()
    
    def issue_command(self, host, command):
        
        try:
            self.sshclient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            key_path = os.path.expanduser("~/.ssh/authorized_keys")
            self.sshclient.connect(host, username="root", key_filename=key_path)
            stdin, stdout, stderr = self.sshclient.exec_command(command)
            
            #SSprint stdin.readlines()
            
            output = stdout.readlines()
            #remove trailing \n
            formated_output = []
            for i in output:
                formated_output.append(i.strip('\n'))
                
            return formated_output
        
        except Exception as e:
            logger.error("Connection Failed: %s" % e)
    
class ceph_client():
    def __init__(self):
        
        self.Connection_status = False
        
        if os.path.exists("/etc/ceph/ceph.conf"):
            logger.warn("/etc/ceph/ceph.conf not found!")
        elif os.path.exists("/etc/ceph/ceph.client.admin.keyring"):
            logger.warn("/etc/ceph/ceph.client.admin.keyring not found!")
        else:
            self.cluster = rados.Rados(conffile="/etc/ceph/ceph.conf",
                                       conf=dict(keyring='/etc/ceph/ceph.client.admin.keyring'),
                                       )
            try:
                self.cluster.connect()
                self.Connection_status = True
            except Exception as e:
                logger.exception("Connection error: %s" % e.strerror )
                
            self.osd_host_list = []
            self.osd_list = []
        
    def issue_command(self, command):
        cmd = json.dumps({"prefix": command, "format": "json"})
        try:
            _, output, _ = self.cluster.mon_command(cmd, b'', timeout=6)
            return json.loads(output)
        except Exception as e:
            logger.error("Error issuing command, %s" % command)
