import os
import urllib2
import urlparse

from charmhelpers.fetch import (
    BaseFetchHandler,
    UnhandledSource
)
from charmhelpers.payload.archive import (
    get_archive_handler,
    extract,
)
from charmhelpers.core.host import mkdir


class ArchiveUrlFetchHandler(BaseFetchHandler):
    """Handler for archives via generic URLs"""
    def can_handle(self, source):
        url_parts = self.parse_url(source)
        if url_parts.scheme not in ('http', 'https', 'ftp', 'file'):
            return "Wrong source type"
        if get_archive_handler(self.base_url(source)):
            return True
        return False

    def download(self, source, dest):
        # propogate all exceptions
        # URLError, OSError, etc
        proto, netloc, path, params, query, fragment = urlparse.urlparse(source)
        if proto in ('http', 'https'):
            auth, barehost = urllib2.splituser(netloc)
            if auth is not None:
                source = urlparse.urlunparse((proto, barehost, path, params, query, fragment))
                username, password = urllib2.splitpasswd(auth)
                passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
                # Realm is set to None in add_password to force the username and password
                # to be used whatever the realm
                passman.add_password(None, source, username, password)
                authhandler = urllib2.HTTPBasicAuthHandler(passman)
                opener = urllib2.build_opener(authhandler)
                urllib2.install_opener(opener)
        response = urllib2.urlopen(source)
        try:
            with open(dest, 'w') as dest_file:
                dest_file.write(response.read())
        except Exception as e:
            if os.path.isfile(dest):
                os.unlink(dest)
            raise e

    def install(self, source):
        url_parts = self.parse_url(source)
        dest_dir = os.path.join(os.environ.get('CHARM_DIR'), 'fetched')
        if not os.path.exists(dest_dir):
            mkdir(dest_dir, perms=0755)
        dld_file = os.path.join(dest_dir, os.path.basename(url_parts.path))
        try:
            self.download(source, dld_file)
        except urllib2.URLError as e:
            raise UnhandledSource(e.reason)
        except OSError as e:
            raise UnhandledSource(e.strerror)
        return extract(dld_file)
