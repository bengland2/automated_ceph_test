#!/usr/bin/bash +x

try_ceph_install() {
  (/bin/bash +x ./launch.sh --ceph-ansible /usr/share/ceph-ansible && \
   ansible -i $inventory_file -m script -a \
     "$script_dir/scripts/utils/check_cluster_status.py" mon-000)
}

# this script implements the Jenkins job by the same name,
# just call it in the "Execute shell" field 
# in the job configuration
# because bash doesn't throw exceptions, 
# the script doesn't stop automatically because of a 
# fatal error, we have to check for errors and exit 
# with an error status if one is seen, 
# Jenkins will stop the pipeline immediately,
# this makes troubleshooting a pipeline much easier for the user

echo "test test test"
systemctl stop firewalld 
systemctl stop iptables
script_dir=$HOME/automated_ceph_test
inventory_file=$HOME/ceph-linode/ansible_inventory

sudo yum remove ceph-ansible -y
rm -rf /usr/share/ceph-ansible

cd $script_dir/staging_area/rhcs_latest/
new_ceph_iso_file="$(ls)"

sudo rm -rf /ceph-ansible-keys
sudo mkdir -m0777 /ceph-ansible-keys

#mount ISO and create rhcs yum repo file 
sudo cp $script_dir/staging_area/repo_files/rhcs.repo /etc/yum.repos.d/
sudo mkdir -p /mnt/rhcs_latest/
sudo umount /mnt/rhcs_latest/
sudo mount $script_dir/staging_area/rhcs_latest/RHCEPH* /mnt/rhcs_latest/
sudo yum clean all


#install ceph-ansible
sudo yum install ceph-ansible -y

sudo sed -i 's/gpgcheck=1/gpgcheck=0/g' /usr/share/ceph-ansible/roles/ceph-common/templates/redhat_storage_repo.j2

mkdir -p $script_dir/staging_area/tmp
#setup all.yml
echo "$ceph_ansible_all_config" > $script_dir/staging_area/tmp/all.yml
sed -i "s/<ceph_iso_file>/$new_ceph_iso_file/g" $script_dir/staging_area/tmp/all.yml
sudo cp $script_dir/staging_area/tmp/all.yml /usr/share/ceph-ansible/group_vars/all.yml


#setup osd.yml
echo "$ceph_ansible_osds_config" > $script_dir/staging_area/tmp/osds.yml
sudo cp $script_dir/staging_area/tmp/osds.yml /usr/share/ceph-ansible/group_vars/osds.yml


#copy site.yml
sudo cp /usr/share/ceph-ansible/site.yml.sample /usr/share/ceph-ansible/site.yml


#Start Ceph-linode deployment
cd $HOME/ceph-linode
echo "$Linode_Cluster_Configuration" > cluster.json
virtualenv-2 linode-env && source linode-env/bin/activate && pip install linode-python
export LINODE_API_KEY=$Linode_API_KEY
try_ceph_install

# if it fails and we have a version adjustment repo, 
# use that and retry ceph-ansible
# this is a hack to work around the lack of correct ansible version and/or
# and lack of latest versions of selinux-policy RPMs in centos
# when a new RHEL version is released.
# it only is used if ceph-ansible fails.  This isn't so bad because
# running it again doesn't take as long the 2nd time.
# the extra repo we insert is given by version_adjust_repo URL parameter
# also passed to preceding job

if [ $? != 0 -a -n "$version_adjust_repo" ] ; then 
    version_adjust_name=`basename $version_adjust_repo`
	yum clean all
	yum install -y libselinux-python || yum upgrade -y libselinux-python
	export ANSIBLE_INVENTORY=~/ceph-linode/ansible_inventory
    ansible -m shell -a "rm -rf $version_adjust_name" all
	ansible -m copy -a "src=~/$version_adjust_name dest=./" all
    ansible -m shell -a \
      "ln -svf ~/$version_adjust_name/version_adjust.repo /etc/yum.repos.d/" all
    ansible -m shell -a \
      'yum clean all ; yum install -y libselinux-python || yum upgrade -y libselinux-python' all
    try_ceph_install
fi
