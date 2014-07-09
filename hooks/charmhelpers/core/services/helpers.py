from charmhelpers.core import hookenv
from charmhelpers.core import templating

from charmhelpers.core.services.base import ManagerCallback


__all__ = ['RelationContext', 'TemplateCallback',
           'render_template', 'template']


class RelationContext(dict):
    """
    Base class for a context generator that gets relation data from juju.

    Subclasses must provide `interface`, which is the interface type of interest,
    and `required_keys`, which is the set of keys required for the relation to
    be considered complete.  The first relation for the interface that is complete
    will be used to populate the data for template.

    The generated context will be namespaced under the interface type, to prevent
    potential naming conflicts.
    """
    name = None
    interface = None
    required_keys = []

    def __init__(self, *args, **kwargs):
        super(RelationContext, self).__init__(*args, **kwargs)
        self.get_data()

    def __bool__(self):
        """
        Returns True if all of the required_keys are available.
        """
        return self.is_ready()

    __nonzero__ = __bool__

    def __repr__(self):
        return super(RelationContext, self).__repr__()

    def is_ready(self):
        """
        Returns True if all of the `required_keys` are available from any units.
        """
        ready = len(self.get(self.name, [])) > 0
        if not ready:
            hookenv.log('Incomplete relation: {}'.format(self.__class__.__name__), hookenv.DEBUG)
        return ready

    def _is_ready(self, unit_data):
        """
        Helper method that tests a set of relation data and returns True if
        all of the `required_keys` are present.
        """
        return set(unit_data.keys()).issuperset(set(self.required_keys))

    def get_data(self):
        """
        Retrieve the relation data for each unit involved in a realtion and,
        if complete, store it in a list under `self[self.name]`.  This
        is automatically called when the RelationContext is instantiated.

        The units are sorted lexographically first by the service ID, then by
        the unit ID.  Thus, if an interface has two other services, 'db:1'
        and 'db:2', with 'db:1' having two units, 'wordpress/0' and 'wordpress/1',
        and 'db:2' having one unit, 'mediawiki/0', all of which have a complete
        set of data, the relation data for the units will be stored in the
        order: 'wordpress/0', 'wordpress/1', 'mediawiki/0'.

        If you only care about a single unit on the relation, you can just
        access it as `{{ interface[0]['key'] }}`.  However, if you can at all
        support multiple units on a relation, you should iterate over the list,
        like:

            {% for unit in interface -%}
                {{ unit['key'] }}{% if not loop.last %},{% endif %}
            {%- endfor %}

        Note that since all sets of relation data from all related services and
        units are in a single list, if you need to know which service or unit a
        set of data came from, you'll need to extend this class to preserve
        that information.
        """
        if not hookenv.relation_ids(self.name):
            return

        ns = self.setdefault(self.name, [])
        for rid in sorted(hookenv.relation_ids(self.name)):
            for unit in sorted(hookenv.related_units(rid)):
                reldata = hookenv.relation_get(rid=rid, unit=unit)
                if self._is_ready(reldata):
                    ns.append(reldata)

    def provide_data(self):
        """
        Return data to be relation_set for this interface.
        """
        return {}


class TemplateCallback(ManagerCallback):
    """
    Callback class that will render a template, for use as a ready action.

    The `target` param, if omitted, will default to `/etc/init/<service name>`.
    """
    def __init__(self, source, target, owner='root', group='root', perms=0444):
        self.source = source
        self.target = target
        self.owner = owner
        self.group = group
        self.perms = perms

    def __call__(self, manager, service_name, event_name):
        service = manager.get_service(service_name)
        context = {}
        for ctx in service.get('required_data', []):
            context.update(ctx)
        templating.render(self.source, self.target, context,
                          self.owner, self.group, self.perms)


# Convenience aliases for templates
render_template = template = TemplateCallback
