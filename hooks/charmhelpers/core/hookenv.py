"Interactions with the Juju environment"
# Copyright 2013 Canonical Ltd.
#
# Authors:
#  Charm Helpers Developers <juju@lists.ubuntu.com>

import os
import json
import yaml
import subprocess
import sys
import UserDict
from subprocess import CalledProcessError

CRITICAL = "CRITICAL"
ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"
DEBUG = "DEBUG"
MARKER = object()

cache = {}


def cached(func):
    """Cache return values for multiple executions of func + args

    For example::

        @cached
        def unit_get(attribute):
            pass

        unit_get('test')

    will cache the result of unit_get + 'test' for future calls.
    """
    def wrapper(*args, **kwargs):
        global cache
        key = str((func, args, kwargs))
        try:
            return cache[key]
        except KeyError:
            res = func(*args, **kwargs)
            cache[key] = res
            return res
    return wrapper


def flush(key):
    """Flushes any entries from function cache where the
    key is found in the function+args """
    flush_list = []
    for item in cache:
        if key in item:
            flush_list.append(item)
    for item in flush_list:
        del cache[item]


def log(message, level=None):
    """Write a message to the juju log"""
    command = ['juju-log']
    if level:
        command += ['-l', level]
    command += [message]
    subprocess.call(command)


class Serializable(UserDict.IterableUserDict):
    """Wrapper, an object that can be serialized to yaml or json"""

    def __init__(self, obj):
        # wrap the object
        UserDict.IterableUserDict.__init__(self)
        self.data = obj

    def __getattr__(self, attr):
        # See if this object has attribute.
        if attr in ("json", "yaml", "data"):
            return self.__dict__[attr]
        # Check for attribute in wrapped object.
        got = getattr(self.data, attr, MARKER)
        if got is not MARKER:
            return got
        # Proxy to the wrapped object via dict interface.
        try:
            return self.data[attr]
        except KeyError:
            raise AttributeError(attr)

    def __getstate__(self):
        # Pickle as a standard dictionary.
        return self.data

    def __setstate__(self, state):
        # Unpickle into our wrapper.
        self.data = state

    def json(self):
        """Serialize the object to json"""
        return json.dumps(self.data)

    def yaml(self):
        """Serialize the object to yaml"""
        return yaml.dump(self.data)


def execution_environment():
    """A convenient bundling of the current execution context"""
    context = {}
    context['conf'] = config()
    if relation_id():
        context['reltype'] = relation_type()
        context['relid'] = relation_id()
        context['rel'] = relation_get()
    context['unit'] = local_unit()
    context['rels'] = relations()
    context['env'] = os.environ
    return context


def in_relation_hook():
    """Determine whether we're running in a relation hook"""
    return 'JUJU_RELATION' in os.environ


def relation_type():
    """The scope for the current relation hook"""
    return os.environ.get('JUJU_RELATION', None)


def relation_id():
    """The relation ID for the current relation hook"""
    return os.environ.get('JUJU_RELATION_ID', None)


def local_unit():
    """Local unit ID"""
    return os.environ['JUJU_UNIT_NAME']


def remote_unit():
    """The remote unit for the current relation hook"""
    return os.environ['JUJU_REMOTE_UNIT']


def service_name():
    """The name service group this unit belongs to"""
    return local_unit().split('/')[0]


def hook_name():
    """The name of the currently executing hook"""
    return os.path.basename(sys.argv[0])


class Config(dict):
    """A Juju charm config dictionary that can write itself to
    disk (as json) and track which values have changed since
    the previous hook invocation.

    Do not instantiate this object directly - instead call
    ``hookenv.config()``

    Example usage::

        >>> # inside a hook
        >>> from charmhelpers.core import hookenv
        >>> config = hookenv.config()
        >>> config['foo']
        'bar'
        >>> config['mykey'] = 'myval'
        >>> config.save()


        >>> # user runs `juju set mycharm foo=baz`
        >>> # now we're inside subsequent config-changed hook
        >>> config = hookenv.config()
        >>> config['foo']
        'baz'
        >>> # test to see if this val has changed since last hook
        >>> config.changed('foo')
        True
        >>> # what was the previous value?
        >>> config.previous('foo')
        'bar'
        >>> # keys/values that we add are preserved across hooks
        >>> config['mykey']
        'myval'
        >>> # don't forget to save at the end of hook!
        >>> config.save()

    """
    CONFIG_FILE_NAME = '.juju-persistent-config'

    def __init__(self, *args, **kw):
        super(Config, self).__init__(*args, **kw)
        self._prev_dict = None
        self.path = os.path.join(charm_dir(), Config.CONFIG_FILE_NAME)
        if os.path.exists(self.path):
            self.load_previous()

    def load_previous(self, path=None):
        """Load previous copy of config from disk so that current values
        can be compared to previous values.

        :param path:

            File path from which to load the previous config. If `None`,
            config is loaded from the default location. If `path` is
            specified, subsequent `save()` calls will write to the same
            path.

        """
        self.path = path or self.path
        with open(self.path) as f:
            self._prev_dict = json.load(f)

    def changed(self, key):
        """Return true if the value for this key has changed since
        the last save.

        """
        if self._prev_dict is None:
            return True
        return self.previous(key) != self.get(key)

    def previous(self, key):
        """Return previous value for this key, or None if there
        is no "previous" value.

        """
        if self._prev_dict:
            return self._prev_dict.get(key)
        return None

    def save(self):
        """Save this config to disk.

        Preserves items in _prev_dict that do not exist in self.

        """
        if self._prev_dict:
            for k, v in self._prev_dict.iteritems():
                if k not in self:
                    self[k] = v
        with open(self.path, 'w') as f:
            json.dump(self, f)


@cached
def config(scope=None):
    """Juju charm configuration"""
    config_cmd_line = ['config-get']
    if scope is not None:
        config_cmd_line.append(scope)
    config_cmd_line.append('--format=json')
    try:
        config_data = json.loads(subprocess.check_output(config_cmd_line))
        if scope is not None:
            return config_data
        return Config(config_data)
    except ValueError:
        return None


@cached
def relation_get(attribute=None, unit=None, rid=None):
    """Get relation information"""
    _args = ['relation-get', '--format=json']
    if rid:
        _args.append('-r')
        _args.append(rid)
    _args.append(attribute or '-')
    if unit:
        _args.append(unit)
    try:
        return json.loads(subprocess.check_output(_args))
    except ValueError:
        return None
    except CalledProcessError, e:
        if e.returncode == 2:
            return None
        raise


def relation_set(relation_id=None, relation_settings={}, **kwargs):
    """Set relation information for the current unit"""
    relation_cmd_line = ['relation-set']
    if relation_id is not None:
        relation_cmd_line.extend(('-r', relation_id))
    for k, v in (relation_settings.items() + kwargs.items()):
        if v is None:
            relation_cmd_line.append('{}='.format(k))
        else:
            relation_cmd_line.append('{}={}'.format(k, v))
    subprocess.check_call(relation_cmd_line)
    # Flush cache of any relation-gets for local unit
    flush(local_unit())


@cached
def relation_ids(reltype=None):
    """A list of relation_ids"""
    reltype = reltype or relation_type()
    relid_cmd_line = ['relation-ids', '--format=json']
    if reltype is not None:
        relid_cmd_line.append(reltype)
        return json.loads(subprocess.check_output(relid_cmd_line)) or []
    return []


@cached
def related_units(relid=None):
    """A list of related units"""
    relid = relid or relation_id()
    units_cmd_line = ['relation-list', '--format=json']
    if relid is not None:
        units_cmd_line.extend(('-r', relid))
    return json.loads(subprocess.check_output(units_cmd_line)) or []


@cached
def relation_for_unit(unit=None, rid=None):
    """Get the json represenation of a unit's relation"""
    unit = unit or remote_unit()
    relation = relation_get(unit=unit, rid=rid)
    for key in relation:
        if key.endswith('-list'):
            relation[key] = relation[key].split()
    relation['__unit__'] = unit
    return relation


@cached
def relations_for_id(relid=None):
    """Get relations of a specific relation ID"""
    relation_data = []
    relid = relid or relation_ids()
    for unit in related_units(relid):
        unit_data = relation_for_unit(unit, relid)
        unit_data['__relid__'] = relid
        relation_data.append(unit_data)
    return relation_data


@cached
def relations_of_type(reltype=None):
    """Get relations of a specific type"""
    relation_data = []
    reltype = reltype or relation_type()
    for relid in relation_ids(reltype):
        for relation in relations_for_id(relid):
            relation['__relid__'] = relid
            relation_data.append(relation)
    return relation_data


@cached
def relation_types():
    """Get a list of relation types supported by this charm"""
    charmdir = os.environ.get('CHARM_DIR', '')
    mdf = open(os.path.join(charmdir, 'metadata.yaml'))
    md = yaml.safe_load(mdf)
    rel_types = []
    for key in ('provides', 'requires', 'peers'):
        section = md.get(key)
        if section:
            rel_types.extend(section.keys())
    mdf.close()
    return rel_types


@cached
def relations():
    """Get a nested dictionary of relation data for all related units"""
    rels = {}
    for reltype in relation_types():
        relids = {}
        for relid in relation_ids(reltype):
            units = {local_unit(): relation_get(unit=local_unit(), rid=relid)}
            for unit in related_units(relid):
                reldata = relation_get(unit=unit, rid=relid)
                units[unit] = reldata
            relids[relid] = units
        rels[reltype] = relids
    return rels


@cached
def is_relation_made(relation, keys='private-address'):
    '''
    Determine whether a relation is established by checking for
    presence of key(s).  If a list of keys is provided, they
    must all be present for the relation to be identified as made
    '''
    if isinstance(keys, str):
        keys = [keys]
    for r_id in relation_ids(relation):
        for unit in related_units(r_id):
            context = {}
            for k in keys:
                context[k] = relation_get(k, rid=r_id,
                                          unit=unit)
            if None not in context.values():
                return True
    return False


def open_port(port, protocol="TCP"):
    """Open a service network port"""
    _args = ['open-port']
    _args.append('{}/{}'.format(port, protocol))
    subprocess.check_call(_args)


def close_port(port, protocol="TCP"):
    """Close a service network port"""
    _args = ['close-port']
    _args.append('{}/{}'.format(port, protocol))
    subprocess.check_call(_args)


@cached
def unit_get(attribute):
    """Get the unit ID for the remote unit"""
    _args = ['unit-get', '--format=json', attribute]
    try:
        return json.loads(subprocess.check_output(_args))
    except ValueError:
        return None


def unit_private_ip():
    """Get this unit's private IP address"""
    return unit_get('private-address')


class UnregisteredHookError(Exception):
    """Raised when an undefined hook is called"""
    pass


class Hooks(object):
    """A convenient handler for hook functions.

    Example::

        hooks = Hooks()

        # register a hook, taking its name from the function name
        @hooks.hook()
        def install():
            pass  # your code here

        # register a hook, providing a custom hook name
        @hooks.hook("config-changed")
        def config_changed():
            pass  # your code here

        if __name__ == "__main__":
            # execute a hook based on the name the program is called by
            hooks.execute(sys.argv)
    """

    def __init__(self):
        super(Hooks, self).__init__()
        self._hooks = {}

    def register(self, name, function):
        """Register a hook"""
        self._hooks[name] = function

    def execute(self, args):
        """Execute a registered hook based on args[0]"""
        hook_name = os.path.basename(args[0])
        if hook_name in self._hooks:
            self._hooks[hook_name]()
        else:
            raise UnregisteredHookError(hook_name)

    def hook(self, *hook_names):
        """Decorator, registering them as hooks"""
        def wrapper(decorated):
            for hook_name in hook_names:
                self.register(hook_name, decorated)
            else:
                self.register(decorated.__name__, decorated)
                if '_' in decorated.__name__:
                    self.register(
                        decorated.__name__.replace('_', '-'), decorated)
            return decorated
        return wrapper


def charm_dir():
    """Return the root directory of the current charm"""
    return os.environ.get('CHARM_DIR')
