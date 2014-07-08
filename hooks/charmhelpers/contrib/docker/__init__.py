
import os
import subprocess

from charmhelpers import fetch
from charmhelpers.core import host
from charmhelpers.core import hookenv
from charmhelpers.core.services.base import ManagerCallback
from charmhelpers.core.services.helpers import RelationContext


def install_docker():
    fetch.apt_install(['docker.io'])
    if os.path.exists('/usr/local/bin/docker'):
        os.unlink('/usr/local/bin/docker')
    os.symlink('/usr/bin/docker.io', '/usr/local/bin/docker')
    with open('/etc/bash_completion.d/docker.io', 'a') as fp:
        fp.write('\ncomplete -F _docker docker')


def install_docker_unstable():
    fetch.add_source('deb https://get.docker.io/ubuntu docker main',
                     key='36A1D7869245C8950F966E92D8576A8BA88D21E9')
    fetch.apt_update(fatal=True)
    fetch.apt_install(['lxc-docker'])


def docker_pull(container_name):
    subprocess.check_call(['docker', 'pull', container_name])


class DockerCallback(ManagerCallback):
    """
    ServiceManager callback to manage starting up a Docker container.

    Can be referenced as `docker_start` or `docker_stop`, and performs
    the appropriate action.  Requires one or more of `DockerPortMappings`,
    `DockerVolumes`, `DockerContainerArgs`, and `DockerRelation` to be
    included in the `required_data` section of the services definition.

    Example:

        manager = services.ServiceManager([{
            'service': 'dockerfile/rethinkdb',
            'required_data': [
                DockerPortMappings({
                    80: 8080,
                    28015: 28015,
                    29015: 29015,
                }),
                DockerVolumes(mapped_volumes={'data': '/rethinkdb'}),
                DockerContainerArgs(
                    '--bind', 'all',
                    '--canonical-address', hookenv.unit_get('public-address'),
                    '--canonical-address', hookenv.unit_get('private-address'),
                    '--machine-name', socket.gethostname().replace('-', '_'),
                ),
            ],
            'start': docker_start,
            'stop': docker_stop,
        }])
    """
    def __call__(self, manager, service_name, event_name):
        container_id_file = os.path.join(hookenv.charm_dir(), 'CONTAINER_ID')
        if os.path.exists(container_id_file):
            container_id = host.read_file(container_id_file)
            subprocess.check_call(['docker', 'stop', container_id])
            os.remove(container_id_file)
        if event_name == 'start':
            subprocess.check_call(
                ['docker', 'run', '-d', '-cidfile', container_id_file] +
                self.get_volume_args(manager, service_name) +
                self.get_port_args(manager, service_name) +
                [service_name] +
                self.get_container_args(manager, service_name))

    def _get_args(self, manager, service_name, arg_type):
        args = []
        service = manager.get_service(service_name)
        for provider in service['required_data']:
            if isinstance(provider, arg_type):
                args.extend(provider.build_args())
        return args

    def get_port_args(self, manager, service_name):
        return self._get_args(manager, service_name, DockerPortMappings)

    def get_container_args(self, manager, service_name):
        return self._get_args(manager, service_name, DockerContainerArgs)

    def get_volume_args(self, manager, service_name):
        return self._get_args(manager, service_name, DockerVolumes)


class DockerPortMappings(dict):
    """
    Subclass of `dict` representing a mapping of ports from the host to the container.
    """
    def build_args(self):
        ports = []
        for src, dst in self.iteritems():
            ports.extend(['-p', '{}:{}'.format(src, dst)])
        return ports


class DockerVolumes(object):
    """
    Class representing Docker volumes.
    """
    def __init__(self, volumes=None, named_volumes=None, mapped_volumes=None):
        """
        :param volumes: List of mutable data volumes to create.
        :type volumes: list
        :param named_volumes: Mapping of names to mutable data volumes to create.
        :type volumes: dict
        :param mapped_volumes: Mapping of host paths to container paths.
        :type volumes: dict
        """
        assert any([volumes, named_volumes, mapped_volumes]),\
            'Must provide at least one of: volumes, named_volumes, mapped_volumes'
        self.volumes = volumes or []
        self.named_volumes = named_volumes or {}
        self.mapped_volumes = mapped_volumes or {}

    def build_args(self):
        args = []
        for volume in self.volumes:
            args.extend(['-v', volume])
        for name, volume in self.named_volumes.iteritems():
            args.extend(['-v', volume, '--name', name])
        for host_path, volume in self.mapped_volumes.iteritems():
            if not os.path.isabs(host_path):
                host_path = os.path.join(hookenv.charm_dir(), host_path)
            host.mkdir(host_path)
            args.extend(['-v', ':'.join([host_path, volume])])
        return args


class DockerContainerArgs(object):
    """
    Class representing arguments to be passed to the Docker container.
    """
    def __init__(self, *args, **kwargs):
        """
        Can accept either a list of arg strings, or a kwarg mapping of arg
        names to values.  If kwargs are given, the names are prepended
        with '--' and have any underscores converted to dashes.

        For example, `DockerContainerArgs(my_opt='foo')` becomes `['--my-opt', 'foo']`.

        If you need to run a specific command other than the container default, it
        should be the first argument.
        """
        self.args = list(args)
        for key, value in kwargs.iteritems():
            self.args.extend(['--'+key.replace('_', '-'), value])

    def build_args(self):
        return self.args


class DockerRelation(RelationContext, DockerContainerArgs):
    """
    Class representing a relation to another Docker container, which could be
    another service, or a peer within the same service.
    """
    name = None
    interface = None
    required_keys = []

    def map(self, relation_settings):
        """
        Translate the relation settings from a single unit into a list of
        arguments to be passed to the Docker container.  This may be called
        multiple times, once for each unit, and the resulting arguments will
        all be passed to the container.

        The default implementation simple appends '--' to the relation setting
        name, so that `{'private-address': '10.0.0.1'}` is transformed
        to `['--private-address', '10.0.0.1']`.

        For example, the following subclass would translate the 'private-address'
        value from each peer to a '--join' argument for each connected peer:

            class ClusterPeers(DockerRelation):
                name = 'cluster'
                interface = 'cluster'
                required_keys = ['private-address']
                port = 29015

                def map(self, relation_settings):
                    return [
                        '--join', '{}:{}'.format(
                            relation_settings['private-address'],
                            self.port
                        )
                    ]
        """
        args = []
        for key, value in relation_settings.iteritems():
            args.extend(['--{}'.format(key), str(value)])
        return args

    def build_args(self):
        args = []
        for unit in self.get(self.name, []):
            args.extend(self.map(unit))
        return args


# Convenience aliases for Docker
docker_start = docker_stop = DockerCallback()
