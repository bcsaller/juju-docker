#!/usr/bin/python

import argparse
import logging
import json
import shlex
import sys
import subprocess

log = logging.getLogger('election')


class O(dict):
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value


def run(cmd, **kwargs):
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    pipe = subprocess.PIPE
    fatal = kwargs.pop('fatal', False)
    inline = kwargs.pop('inline', False)
    on_failure = kwargs.pop('on_failure', None)
    stdout = kwargs.pop('stdout', inline and sys.stdout or pipe)

    cmdstr = ' '.join(cmd)
    log.debug("Exec Command: {}".format(cmdstr))

    exception = None
    process = subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=kwargs.pop('stderr', pipe),
        close_fds=kwargs.pop('close_fds', True), **kwargs)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        log.debug('Error invoking cmd: {} -> {}'.format(
            cmdstr, process.returncode))
        if fatal or on_failure:
            exception = subprocess.CalledProcessError(
                process.returncode, cmdstr)
            exception.output = ''.join(filter(None, [stdout, stderr]))
            if on_failure:
                on_failure(cmd, process, exception)
            if fatal:
                raise exception

    result = O(returncode=process.returncode,
               stdout=stdout, stderr=stderr)
    if exception:
        result['exception'] = exception
    return result


def relation_list():
    result = run("relation-list --format json")
    if result.returncode == 0:
        return json.loads(result.stdout)
    return ''


def get_peers():
    peers = relation_list()
    ips = []
    for peer in peers:
        ips.append(relation_ip(peer))
    return ips


def cli_peers(peers=None, port=29015):
    if peers is None:
        peers = get_peers()
    result = []
    for peer in peers:
        result.extend(['--join', '{}:{}'.format(peer, port)])
    return ' '.join(result)


def relation_get(key="-", unit=None):
    args = ['relation-get', key]
    if unit:
        args.append(unit)
    return run(args)


def relation_ip(unit):
    return relation_get('private-address', unit)


def relation_set(key, value):
    return run('relation-set {}="{}"'.format(key, value))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--log-level',
                        dest="log_level", default=logging.INFO)

    options = parser.parse_args()
    logging.basicConfig(level=options.log_level)

    result = cli_peers()
    if result:
        print(result)
    else:
        print('')

if __name__ == "__main__":
    main()
