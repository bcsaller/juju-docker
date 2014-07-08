#!/usr/bin/env python

import socket
from charmhelpers.core import hookenv
from charmhelpers.core import services
from charmhelpers.contrib import docker


class ClusterPeers(docker.DockerRelation):
    name = 'intracluster'
    interface = 'rethinkdb-cluster'
    required_keys = ['private-address']
    port = 29015

    def map(self, relation_settings):
        return [
            '--join', '{}:{}'.format(
                relation_settings['private-address'],
                self.port
            )
        ]


class WebsiteRelation(services.helpers.RelationContext):
    name = 'website'
    interface = 'http'

    def provide_data(self):
        return {'hostname': hookenv.unit_private_ip(), 'port': 80}


def install():
    docker.install_docker()
    docker.docker_pull('dockerfile/rethinkdb')


def manage():
    config = hookenv.config()
    manager = services.ServiceManager([
        {
            'service': 'dockerfile/rethinkdb',
            'ports': [80, 28015, 29015],
            'provided_data': [WebsiteRelation()],
            'required_data': [
                docker.DockerPortMappings({
                    80: 8080,
                    28015: 28015,
                    29015: 29015,
                }),
                docker.DockerVolumes(mapped_volumes={config['storage-path']: '/rethinkdb'}),
                docker.DockerContainerArgs(
                    'rethinkdb',
                    '--bind', 'all',
                    '--canonical-address', hookenv.unit_get('public-address'),
                    '--canonical-address', hookenv.unit_get('private-address'),
                    '--machine-name', socket.gethostname().replace('-', '_'),
                ),
                ClusterPeers(),
            ],
            'start': docker.docker_start,
            'stop': docker.docker_stop,
        },
    ])
    manager.manage()


if __name__ == '__main__':
    if hookenv.hook_name() == 'install':
        install()
    else:
        manage()
