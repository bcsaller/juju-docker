"""Tools for working with the host system"""
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  Nick Moffitt <nick.moffitt@canonical.com>
#  Matthew Wedgwood <matthew.wedgwood@canonical.com>

import os
import pwd
import grp
import random
import string
import subprocess
import hashlib
import shutil
from contextlib import contextmanager

from collections import OrderedDict

from hookenv import log
from fstab import Fstab


def service_start(service_name):
    """Start a system service"""
    return service('start', service_name)


def service_stop(service_name):
    """Stop a system service"""
    return service('stop', service_name)


def service_restart(service_name):
    """Restart a system service"""
    return service('restart', service_name)


def service_reload(service_name, restart_on_failure=False):
    """Reload a system service, optionally falling back to restart if
    reload fails"""
    service_result = service('reload', service_name)
    if not service_result and restart_on_failure:
        service_result = service('restart', service_name)
    return service_result


def service(action, service_name):
    """Control a system service"""
    cmd = ['service', service_name, action]
    return subprocess.call(cmd) == 0


def service_running(service):
    """Determine whether a system service is running"""
    try:
        output = subprocess.check_output(['service', service, 'status'], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        return False
    else:
        if ("start/running" in output or "is running" in output):
            return True
        else:
            return False


def service_available(service_name):
    """Determine whether a system service is available"""
    try:
        subprocess.check_output(['service', service_name, 'status'], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        return False
    else:
        return True


def adduser(username, password=None, shell='/bin/bash', system_user=False):
    """Add a user to the system"""
    try:
        user_info = pwd.getpwnam(username)
        log('user {0} already exists!'.format(username))
    except KeyError:
        log('creating user {0}'.format(username))
        cmd = ['useradd']
        if system_user or password is None:
            cmd.append('--system')
        else:
            cmd.extend([
                '--create-home',
                '--shell', shell,
                '--password', password,
            ])
        cmd.append(username)
        subprocess.check_call(cmd)
        user_info = pwd.getpwnam(username)
    return user_info


def add_user_to_group(username, group):
    """Add a user to a group"""
    cmd = [
        'gpasswd', '-a',
        username,
        group
    ]
    log("Adding user {} to group {}".format(username, group))
    subprocess.check_call(cmd)


def rsync(from_path, to_path, flags='-r', options=None):
    """Replicate the contents of a path"""
    options = options or ['--delete', '--executability']
    cmd = ['/usr/bin/rsync', flags]
    cmd.extend(options)
    cmd.append(from_path)
    cmd.append(to_path)
    log(" ".join(cmd))
    return subprocess.check_output(cmd).strip()


def symlink(source, destination):
    """Create a symbolic link"""
    log("Symlinking {} as {}".format(source, destination))
    cmd = [
        'ln',
        '-sf',
        source,
        destination,
    ]
    subprocess.check_call(cmd)


def mkdir(path, owner='root', group='root', perms=0555, force=False):
    """Create a directory"""
    log("Making dir {} {}:{} {:o}".format(path, owner, group,
                                          perms))
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    realpath = os.path.abspath(path)
    if os.path.exists(realpath):
        if force and not os.path.isdir(realpath):
            log("Removing non-directory file {} prior to mkdir()".format(path))
            os.unlink(realpath)
    else:
        os.makedirs(realpath, perms)
    os.chown(realpath, uid, gid)


def write_file(path, content, owner='root', group='root', perms=0444):
    """Create or overwrite a file with the contents of a string"""
    log("Writing file {} {}:{} {:o}".format(path, owner, group, perms))
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    with open(path, 'w') as target:
        os.fchown(target.fileno(), uid, gid)
        os.fchmod(target.fileno(), perms)
        target.write(content)


def copy_file(src, dst, owner='root', group='root', perms=0444):
    """Create or overwrite a file with the contents of another file"""
    log("Writing file {} {}:{} {:o} from {}".format(dst, owner, group, perms, src))
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    shutil.copyfile(src, dst)
    os.chown(dst, uid, gid)
    os.chmod(dst, perms)


def read_file(path):
    with open(path) as fp:
        return fp.read()


def fstab_remove(mp):
    """Remove the given mountpoint entry from /etc/fstab
    """
    return Fstab.remove_by_mountpoint(mp)


def fstab_add(dev, mp, fs, options=None):
    """Adds the given device entry to the /etc/fstab file
    """
    return Fstab.add(dev, mp, fs, options=options)


def mount(device, mountpoint, options=None, persist=False, filesystem="ext3"):
    """Mount a filesystem at a particular mountpoint"""
    cmd_args = ['mount']
    if options is not None:
        cmd_args.extend(['-o', options])
    cmd_args.extend([device, mountpoint])
    try:
        subprocess.check_output(cmd_args)
    except subprocess.CalledProcessError, e:
        log('Error mounting {} at {}\n{}'.format(device, mountpoint, e.output))
        return False

    if persist:
        return fstab_add(device, mountpoint, filesystem, options=options)
    return True


def umount(mountpoint, persist=False):
    """Unmount a filesystem"""
    cmd_args = ['umount', mountpoint]
    try:
        subprocess.check_output(cmd_args)
    except subprocess.CalledProcessError, e:
        log('Error unmounting {}\n{}'.format(mountpoint, e.output))
        return False

    if persist:
        return fstab_remove(mountpoint)
    return True


def mounts():
    """Get a list of all mounted volumes as [[mountpoint,device],[...]]"""
    with open('/proc/mounts') as f:
        # [['/mount/point','/dev/path'],[...]]
        system_mounts = [m[1::-1] for m in [l.strip().split()
                                            for l in f.readlines()]]
    return system_mounts


def file_hash(path):
    """Generate a md5 hash of the contents of 'path' or None if not found """
    if os.path.exists(path):
        h = hashlib.md5()
        with open(path, 'r') as source:
            h.update(source.read())  # IGNORE:E1101 - it does have update
        return h.hexdigest()
    else:
        return None


def restart_on_change(restart_map, stopstart=False):
    """Restart services based on configuration files changing

    This function is used a decorator, for example::

        @restart_on_change({
            '/etc/ceph/ceph.conf': [ 'cinder-api', 'cinder-volume' ]
            })
        def ceph_client_changed():
            pass  # your code here

    In this example, the cinder-api and cinder-volume services
    would be restarted if /etc/ceph/ceph.conf is changed by the
    ceph_client_changed function.
    """
    def wrap(f):
        def wrapped_f(*args):
            checksums = {}
            for path in restart_map:
                checksums[path] = file_hash(path)
            f(*args)
            restarts = []
            for path in restart_map:
                if checksums[path] != file_hash(path):
                    restarts += restart_map[path]
            services_list = list(OrderedDict.fromkeys(restarts))
            if not stopstart:
                for service_name in services_list:
                    service('restart', service_name)
            else:
                for action in ['stop', 'start']:
                    for service_name in services_list:
                        service(action, service_name)
        return wrapped_f
    return wrap


def lsb_release():
    """Return /etc/lsb-release in a dict"""
    d = {}
    with open('/etc/lsb-release', 'r') as lsb:
        for l in lsb:
            k, v = l.split('=')
            d[k.strip()] = v.strip()
    return d


def pwgen(length=None):
    """Generate a random pasword."""
    if length is None:
        length = random.choice(range(35, 45))
    alphanumeric_chars = [
        l for l in (string.letters + string.digits)
        if l not in 'l0QD1vAEIOUaeiou']
    random_chars = [
        random.choice(alphanumeric_chars) for _ in range(length)]
    return(''.join(random_chars))


def list_nics(nic_type):
    '''Return a list of nics of given type(s)'''
    if isinstance(nic_type, basestring):
        int_types = [nic_type]
    else:
        int_types = nic_type
    interfaces = []
    for int_type in int_types:
        cmd = ['ip', 'addr', 'show', 'label', int_type + '*']
        ip_output = subprocess.check_output(cmd).split('\n')
        ip_output = (line for line in ip_output if line)
        for line in ip_output:
            if line.split()[1].startswith(int_type):
                interfaces.append(line.split()[1].replace(":", ""))
    return interfaces


def set_nic_mtu(nic, mtu):
    '''Set MTU on a network interface'''
    cmd = ['ip', 'link', 'set', nic, 'mtu', mtu]
    subprocess.check_call(cmd)


def get_nic_mtu(nic):
    cmd = ['ip', 'addr', 'show', nic]
    ip_output = subprocess.check_output(cmd).split('\n')
    mtu = ""
    for line in ip_output:
        words = line.split()
        if 'mtu' in words:
            mtu = words[words.index("mtu") + 1]
    return mtu


def get_nic_hwaddr(nic):
    cmd = ['ip', '-o', '-0', 'addr', 'show', nic]
    ip_output = subprocess.check_output(cmd)
    hwaddr = ""
    words = ip_output.split()
    if 'link/ether' in words:
        hwaddr = words[words.index('link/ether') + 1]
    return hwaddr


def cmp_pkgrevno(package, revno, pkgcache=None):
    '''Compare supplied revno with the revno of the installed package

    *  1 => Installed revno is greater than supplied arg
    *  0 => Installed revno is the same as supplied arg
    * -1 => Installed revno is less than supplied arg

    '''
    import apt_pkg
    if not pkgcache:
        apt_pkg.init()
        pkgcache = apt_pkg.Cache()
    pkg = pkgcache[package]
    return apt_pkg.version_compare(pkg.current_ver.ver_str, revno)


@contextmanager
def chdir(d):
    cur = os.getcwd()
    try:
        yield os.chdir(d)
    finally:
        os.chdir(cur)


def chownr(path, owner, group):
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid

    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            full = os.path.join(root, name)
            broken_symlink = os.path.lexists(full) and not os.path.exists(full)
            if not broken_symlink:
                os.chown(full, uid, gid)
