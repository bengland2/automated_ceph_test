#!/bin/bash -x

# replace with $script_dir/scripts/run-smallfile.sh

script_dir=$HOME/automated_ceph_test
mon_port=6789
mountpoint=/mnt/cephfs
NOTOK=1

# this subroutine installs software from github
# if it's a branch rather than master, you
# have to do a couple of extra steps

clone_branch() {
	cd
	git_url=$1
	echo $git_url | grep '/tree/'
	if [ $? = 0 ] ; then
		git_branch_name=`basename $git_url`
		git_branch_tree=`dirname $git_url`
		git_site=`dirname $git_branch_tree`
	else
		git_site=$git_url
	fi
	git_dirname=`basename $git_site`
	rm -rf $git_dirname
	git clone $git_site || exit $NOTOK
	cd $git_dirname
	if [ -n "$git_branch_name" ] ; then
		git fetch $git_site $git_branch_name
		git checkout $git_branch_name
	fi
	rm -rf .git
	cd
	ansible -m synchronize -a "src=~/$git_dirname delete=yes dest=./" clients || exit $NOTOK
}

hostname | grep -q linode.com
if [ $? = 0 ]; then
        inventory_file=$HOME/ceph-linode/ansible_inventory
else
        inventory_file=$script_dir/ansible_inventory
fi
export ANSIBLE_INVENTORY=$inventory_file

rm -rf $archive_dir
mkdir -v $archive_dir

# need rsync for ansible synchronize module
# need numpy for fs-drift fsop.py random number generation
ansible -m shell -a 'yum install -y rsync numpy' clients || exit $NOTOK

clone_branch $fs_drift_url

ln -svf ~/fs-drift/fs-drift.py /usr/local/bin
# fs-drift-remote.py must be in PATH on remote hosts
ansible -m shell -a "ln -svf ~/fs-drift/fs-drift-remote.py /usr/local/bin/" clients || exit $NOTOK


# get monitor IP address, we'll need that to mount Cephfs

mon_ip=`grep '^mon host' /etc/ceph/ceph.conf | awk '{ print $NF }' | awk -F, '{ print $1 }'`

# distribute client key to Cephfs clients in expected format

(rm -f /etc/ceph/cephfs.key && \
 awk '/==/{ print $NF }' /etc/ceph/ceph.client.admin.keyring > /etc/ceph/cephfs.key && \
 ansible -m copy -a 'src=/etc/ceph/cephfs.key dest=/etc/ceph/' clients) \
  || exit $NOTOK

# it's ok if unmounting fails because it's not already mounted

ansible -m shell -a "umount -v $mountpoint" clients

# if we can't mount Cephfs, bail out right away

ansible -m shell -a \
 "mkdir -pv $mountpoint && mount -v -t ceph -o name=admin,secretfile=/etc/ceph/cephfs.key $mon_ip:$mon_port:/ $mountpoint && mkdir -pv $mountpoint/smf" clients \
   || exit $NOTOK

# must mount cephfs from test driver as well

umount $mountpoint
(mkdir -pv $mountpoint && \
 mount -v -t ceph -o name=admin,secretfile=/etc/ceph/cephfs.key $mon_ip:$mon_port:/ $mountpoint && \
 mkdir -pv $mountpoint/fs_drift ) \
 || exit $NOTOK

# run the test and save results in archive_dir

source /etc/profile.d/pbench-agent.sh
rm -rf $archive_dir/fs_drift_results
mkdir -pv $archive_dir/fs_drift_results
benchyaml=$archive_dir/benchmark.yaml
echo "$fs_drift_yaml" | tee $benchyaml

# need to get indentation right for YAML, next cmd copies indentation
grep 'duration:' $benchyaml | sed 's#duration:.*$#top: /mnt/cephfs/fs_drift#' >> $benchyaml
cl=`ansible --list-hosts clients | tail -n +2`
fs_drift_clients=`echo $cl | sed 's/ /,/g'`
grep 'duration:' $benchyaml | sed 's#duration:.*$#host-set:#' > /tmp/hs
sed "s/$/ $fs_drift_clients/" < /tmp/hs >> $benchyaml
$script_dir/scripts/utils/addhost_to_jobfile.sh $archive_dir/benchmark.yaml $ANSIBLE_INVENTORY
echo "################ CBT YAML input ################"
cat $archive_dir/benchmark.yaml

pbench-user-benchmark -- python ~/fs-drift/fs-drift.py --output-json $archive_dir/fs-drift.json --input-yaml $benchyaml
rc=$?
umount -v $mountpoint
rm -fv /etc/ceph/cephfs.key smf-clients.list

exit $rc
