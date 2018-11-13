import os, sys, json, time, types, csv, copy
import logging, statistics, yaml 
import datetime, socket, itertools
from scribes import *
import cbt_pbench_analyzer
from datetime import timedelta
import hashlib
from ansible.modules.system import hostname

logger = logging.getLogger("index_cbt")

def analyze_cbt_smf_results(tdir, cbt_config_obj, test_metadata):

    logger.info("Processing Rados benchmark results.")
    
    metadata = {}
    metadata = test_metadata
    for dirpath, dirs, files in os.walk(tdir):
        for filename in files:
            fname = os.path.join(dirpath, filename)
            if 'benchmark_config.yaml' in fname:
                benchmark_data = yaml.load(open(fname))
                metadata['ceph_benchmark_test']['test_config'] = benchmark_data['cluster']
                
                if "smallfile" in metadata['ceph_benchmark_test']['test_config']['benchmark']:
                        json_obj = None
            try:
                with open(os.path.join(dirpath, 'smfresults.json'), 'r') as json_f:
                    json_obj = json.load(json_f)
            except IOError as e:
                if IOError.errno != errno.ENOENT:
                    raise e
            if json_obj:
                metadata['ceph_benchmark_test']['results'] = json_obj
                cbt_smf_rspt_files_generator = analyze_cbt_smallfile_rspt_files(
                    os.path.join(dirname, 'rsptimes'), cbt_config_obj, copy.deepcopy(metadata))
                for cbt_smf_obj in cbt_smf_rspt_files_generator:
                    yield cbt_smf_obj

def analyze_cbt_rados_files(tdir, cbt_config_obj, metadata):
    logger.info("Processing smallfile response time files...")
    for dirpath, dirs, files in os.walk(tdir):
        for filename in files:
            fname = os.path.join(dirpath, filename)
        if fname.startswith('rsptime') and fname.endswith('csv')
                smf_rspt_transcriber_obj = smf_rspt_transcriber(fname, copy.deepcopy(metadata))
                yield smf_rspt_transcriber_obj              

class smf_rspt_transcriber:
    
    def __init__(self, csv_file, metadata):
        self.csv_file = csv_file
        self.metadata = metadata
        self.csv_filename_matcher = re.compile(
          'rsptimes_(?P<thread_id>[0-9]{2})_' + 
          '(?P<hostname>[a-zA-Z0-9\-\.]*)_' + 
          '(?P<timestamp>[0-9]+\.[0-9]{2}).csv.' + 
          '(?P<host_ip>[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})')

    def emit_actions(self):
        importdoc = {}
        # example filename:
        # rsptimes_00_li1914-80.members.linode.com_create_1542118485.44.csv.192.168.181.24
        m = self.csv_filename_matcher(os.basename(self.csv_file))
        thread_id = m.group('thread_id')
        hostname = m.group('hostname')
        md = metadata['ceph_benchmark_test']['results']
        importdoc["_index"] = "smf-rspt-%s-%s" % (thread_id, hostname)
        importdoc["_type"] = "smallfile-response-times"
        importdoc["_op_type"] = md['benchmark']['operation']
        importdoc["_source"] = self.metadata
        logger.debug("Indexing %s" % self.csv_file)
                
        importdoc["_source"]['ceph_benchmark_test']['common']['test_info']['file'] = file_name 
        
        thread_n_metric = file_name.split('.')[1]
        thread, metric_name = thread_n_metric.split('_', 1)
        
        tmp_doc = {
            'smf': {
                'rsptimes': {
                    }
                }
            }
        rsptimes = tmp_doc['smf']['rsptimes']
        
        with open(self.csv_file, 'r') as csv_f:
            lines = [ l.split(',') for l in csv_f.readlines() ]
            for tokens in lines:
                next_doc = {}
                next_doc['time_since_start'] = float(tokens[1])
                next_doc['response_time'] = float(tokens[2])
        
        with open(self.csv_file) as csvfile:
            readCSV = csv.reader(csvfile, delimiter=',')
            for row in (readCSV):

                ms = float(row[0]) + float(start_time)
                newtime = datetime.datetime.fromtimestamp(ms / 1000.0)
                importdoc["_source"]['date'] = newtime.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                
                tmp_doc['fio']['fio_logs'][metric_name]['metic_value'] = int(row[1])
                tmp_doc['fio']['fio_logs']['data direction'] = row[2]
                tmp_doc['fio']['fio_logs']['fio_thread'] = thread
                  
                #importdoc["_source"]["test_data"][metric_name] = int(row[1])
                #importdoc["_source"]["test_data"]['data direction'] = row[2]
                #importdoc['_source']['test_data']['fio_thread'] = thread 
                
                importdoc["_source"]['ceph_benchmark_test']["test_data"] = tmp_doc
                importdoc["_id"] = hashlib.md5(json.dumps(importdoc)).hexdigest()
                yield importdoc  # XXX: TODO change to yield a
                
                
                
