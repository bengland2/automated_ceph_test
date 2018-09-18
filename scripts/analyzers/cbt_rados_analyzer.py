import os, sys, json, time, types, csv, copy
import logging, statistics, yaml 
import datetime, socket, itertools
from scribes import *
import cbt_pbench_analyzer
from datetime import timedelta
from ansible.modules.system import hostname

logger = logging.getLogger("index_cbt")

def analyze_cbt_rados_results(tdir, cbt_config_obj, test_metadata):

    logger.info("Processing Rados benchmark results.")
    
    metadata = {}
    metadata = test_metadata
    for dirpath, dirs, files in os.walk(tdir):
        for filename in files:
            fname = os.path.join(dirpath, filename)
            if 'benchmark_config.yaml' in fname:
                benchmark_data = yaml.load(open(fname))
                metadata['ceph_benchmark_test']['test_config'] = benchmark_data['cluster']
                
                if metadata['ceph_benchmark_test']['test_config']['op_size']: metadata['ceph_benchmark_test']['test_config']['op_size'] = int(metadata['ceph_benchmark_test']['test_config']['op_size']) / 1024
                
                if "radosbench" in metadata['ceph_benchmark_test']['test_config']['benchmark']:
                    
                    write_path = "%s/write" % dirpath
                    metadata['ceph_benchmark_test']['test_config']['mode'] = "write"
                    #analyze rados output files
                    
                    analyze_cbt_rados_files_generator = analyze_cbt_rados_files(write_path, cbt_config_obj, copy.deepcopy(metadata))
                    for cbt_rados_obj in analyze_cbt_rados_files_generator:
                        yield cbt_rados_obj
                    
                    #analyze rados wrtie pbench logs
#                     analyze_cbt_Pbench_data_generator = cbt_pbench_analyzer.analyze_cbt_Pbench_data(write_path, cbt_config_obj, copy.deepcopy(metadata))
#                     for pbench_obj in analyze_cbt_Pbench_data_generator:
#                         yield pbench_obj
                    
                    if not metadata['ceph_benchmark_test']['test_config']['write_only']:
                        read_path = "%s/seq" % dirpath
                        metadata['ceph_benchmark_test']['test_config']['mode'] = "read"
                        
                        analyze_cbt_rados_files_generator = analyze_cbt_rados_files(read_path, cbt_config_obj, copy.deepcopy(metadata))
                        for cbt_rados_obj in analyze_cbt_rados_files_generator:
                            yield cbt_rados_obj
                        
#                         analyze_cbt_Pbench_data_generator = cbt_pbench_analyzer.analyze_cbt_Pbench_data(read_path, cbt_config_obj, copy.deepcopy(metadata))
#                         for pbench_obj in analyze_cbt_Pbench_data_generator:
#                             yield pbench_obj
                            
def analyze_cbt_rados_files(tdir, cbt_config_obj, metadata):
    logger.info("Processing rados json files...")
    for dirpath, dirs, files in os.walk(tdir):
        for filename in files:
            fname = os.path.join(dirpath, filename)
            if "output" in fname and "json" not in fname:
                #get raw output file and seperated json file and pass them to a transcriber object
                
                #strip out hostname or ipaddress
                file_name = os.path.basename(fname)
                dir_name = os.path.dirname(fname)
                json_file = "json_%s" % file_name, 
                json_file = "%s/%s" % (dir_name, file_name)
                print json_file
                junk, rados_instance, hostname = file_name.split(".", 2)
                
                metadata['ceph_benchmark_test']['common']['hardware'] = {"host": hostname}
                metadata['ceph_benchmark_test']["test_data"] = {"rados": {}}
                metadata['ceph_benchmark_test']["test_data"]['rados_instance'] = rados_instance
                rados_transcriber_obj = cbt_rados_scribe.rados_transcriber(fname, json_file, metadata)
                yield rados_transcriber_obj              
                
     