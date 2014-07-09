import os
from charmhelpers.fetch import (
    BaseFetchHandler,
    UnhandledSource
)
from charmhelpers.core.host import mkdir
from bzrlib.branch import Branch


class BzrUrlFetchHandler(BaseFetchHandler):
    """Handler for bazaar branches via generic and lp URLs"""
    def can_handle(self, source):
        url_parts = self.parse_url(source)
        if url_parts.scheme not in ('bzr+ssh', 'lp'):
            return False
        else:
            return True

    def branch(self, source, dest):
        url_parts = self.parse_url(source)
        # If we use lp:branchname scheme we need to load plugins
        if not self.can_handle(source):
            raise UnhandledSource("Cannot handle {}".format(source))
        if url_parts.scheme == "lp":
            from bzrlib.plugin import load_plugins
            load_plugins()
        try:
            remote_branch = Branch.open(source)
            remote_branch.bzrdir.sprout(dest).open_branch()
        except Exception as e:
            raise e

    def install(self, source):
        url_parts = self.parse_url(source)
        branch_name = url_parts.path.strip("/").split("/")[-1]
        dest_dir = os.path.join(os.environ.get('CHARM_DIR'), "fetched",
                                branch_name)
        if not os.path.exists(dest_dir):
            mkdir(dest_dir, perms=0755)
        try:
            self.branch(source, dest_dir)
        except OSError as e:
            raise UnhandledSource(e.strerror)
        return dest_dir
