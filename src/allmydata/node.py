import datetime, os.path, re, types, ConfigParser, tempfile
from base64 import b32decode, b32encode

from twisted.internet import reactor
from twisted.python import log as twlog
from twisted.application import service
from foolscap.api import Tub, app_versions
import foolscap.logging.log
from allmydata import get_package_versions, get_package_versions_string
from allmydata.util import log
from allmydata.util import fileutil, iputil
from allmydata.util.assertutil import _assert
from allmydata.util.fileutil import abspath_expanduser_unicode
from allmydata.util.encodingutil import get_filesystem_encoding, quote_output
from allmydata.util import configutil
from allmydata.util.configutil import _None, config_item

def _common_config_sections():
    return {
        "connections": (
            "tcp",
        ),
        "node": (
            "log_gatherer.furl",
            "nickname",
            "reveal-ip-address",
            "tempdir",
            "timeout.disconnect",
            "timeout.keepalive",
            "tub.location",
            "tub.port",
            "web.port",
            "web.static",
        ),
        "i2p": (
            "enabled",
            "i2p.configdir",
            "i2p.executable",
            "launch",
            "sam.port",
            "dest",
            "dest.port",
            "dest.private_key_file",
        ),
        "tor": (
            "control.port",
            "enabled",
            "launch",
            "socks.port",
            "tor.executable",
            "onion",
            "onion.local_port",
            "onion.external_port",
            "onion.private_key_file",
        ),
    }

# Add our application versions to the data that Foolscap's LogPublisher
# reports.
for thing, things_version in get_package_versions().iteritems():
    app_versions.add_version(thing, str(things_version))

# group 1 will be addr (dotted quad string), group 3 if any will be portnum (string)
ADDR_RE=re.compile("^([1-9][0-9]*\.[1-9][0-9]*\.[1-9][0-9]*\.[1-9][0-9]*)(:([1-9][0-9]*))?$")


def formatTimeTahoeStyle(self, when):
    # we want UTC timestamps that look like:
    #  2007-10-12 00:26:28.566Z [Client] rnp752lz: 'client running'
    d = datetime.datetime.utcfromtimestamp(when)
    if d.microsecond:
        return d.isoformat(" ")[:-3]+"Z"
    else:
        return d.isoformat(" ") + ".000Z"

PRIV_README="""
This directory contains files which contain private data for the Tahoe node,
such as private keys.  On Unix-like systems, the permissions on this directory
are set to disallow users other than its owner from reading the contents of
the files.   See the 'configuration.rst' documentation file for details."""

class MissingConfigEntry(Exception):
    """ A required config entry was not found. """

class OldConfigError(Exception):
    """ An obsolete config file was found. See
    docs/historical/configuration.rst. """
    def __str__(self):
        return ("Found pre-Tahoe-LAFS-v1.3 configuration file(s):\n"
                "%s\n"
                "See docs/historical/configuration.rst."
                % "\n".join([quote_output(fname) for fname in self.args[0]]))

class OldConfigOptionError(Exception):
    pass

class UnescapedHashError(Exception):
    def __str__(self):
        return ("The configuration entry %s contained an unescaped '#' character."
                % quote_output("[%s]%s = %s" % self.args))

class PrivacyError(Exception):
    """reveal-IP-address = false, but the node is configured in such a way
    that the IP address could be revealed"""


def _make_tcp_handler():
    # this is always available
    from foolscap.connections.tcp import default
    return default()

def _create_foolscap_handlers(config, i2p_prov, tor_prov):
    """
    returns a dict of handlers and a dict of 'default handlers'
    """
    # XXX could cache this here if it's worth it to only produce once
    # (instead of ~3 times)
    # We store handlers for everything. None means we were unable to
    # create that handler, so hints which want it will be ignored.
    handlers = {
        "tcp": _make_tcp_handler(),
        "tor": tor_prov.get_tor_handler(),
        "i2p": i2p_prov.get_i2p_handler(),
        }
    log.msg(
        format="built Foolscap connection handlers for: %(known_handlers)s",
        known_handlers=sorted([k for k,v in handlers.items() if v]),
        facility="tahoe.node",
        umid="PuLh8g",
    )

    # then we remember the default mappings from tahoe.cfg
    default_connection_handlers = {
        "tor": "tor",
        "i2p": "i2p",
    }
    tcp_handler_name = configutil.config_item(config, "connections", "tcp", "tcp").lower()
    if tcp_handler_name == "disabled":
        default_connection_handlers["tcp"] = None
    else:
        if tcp_handler_name not in handlers:
            raise ValueError("'tahoe.cfg [connections] tcp='"
                             " uses unknown handler type '%s'"
                             % tcp_handler_name)
        if not handlers[tcp_handler_name]:
            raise ValueError("'tahoe.cfg [connections] tcp=' uses "
                             "unavailable/unimportable handler type '%s'. "
                             "Please pip install tahoe-lafs[%s] to fix."
                             % (tcp_handler_name, tcp_handler_name))
        default_connection_handlers["tcp"] = tcp_handler_name

    if not configutil.config_item(config, "node", "reveal-IP-address", True, boolean=True):
        if default_connection_handlers.get("tcp") == "tcp":
            raise PrivacyError("tcp = tcp, must be set to 'tor' or 'disabled'")
    return default_connection_handlers


def _tub_options_from_config(config):
    tub_options = {
        "logLocalFailures": True,
        "logRemoteFailures": True,
        "expose-remote-exception-types": False,
        "accept-gifts": False,
    }

    # see #521 for a discussion of how to pick these timeout values.
    keepalive_timeout_s = configutil.config_item(config, "node", "timeout.keepalive", "")
    if keepalive_timeout_s:
        tub_options["keepaliveTimeout"] = int(keepalive_timeout_s)
    disconnect_timeout_s = configutil.config_item(config, "node", "timeout.disconnect", "")
    if disconnect_timeout_s:
        # N.B.: this is in seconds, so use "1800" to get 30min
        tub_options["disconnectTimeout"] = int(disconnect_timeout_s)
    return tub_options


def _create_tub(tub_options, handlers, **kwargs):
    # Create a Tub with the right options and handlers. It will be
    # ephemeral unless the caller provides certFile=
    tub = Tub(**kwargs)
    for (name, value) in tub_options.items():
        tub.setOption(name, value)
    tub.removeAllConnectionHintHandlers()
    for hint_type, handler_name in handlers.items():
        # XXX this was self._foolscap_connection_handlers originally,
        # which leads me to believe it was *always* using the
        # 'default' ones?
        handler = handlers[handler_name]
        if handler:
            tub.addConnectionHintHandler(hint_type, handler)
    return tub


def _convert_tub_port(self, s):
    if re.search(r'^\d+$', s):
        return "tcp:%d" % int(s)
    return s

def _tub_portlocation(cfg_tubport, cfg_location, portnumfile):
    """
    return None, or tuple of (port, location)
    """

    tubport_disabled = False
    if cfg_tubport is not None:
        cfg_tubport = cfg_tubport.strip()
        if cfg_tubport == "":
            raise ValueError("tub.port must not be empty")
        if cfg_tubport == "disabled":
            tubport_disabled = True

    location_disabled = False
    if cfg_location is not None:
        cfg_location = cfg_location.strip()
        if cfg_location == "":
            raise ValueError("tub.location must not be empty")
        if cfg_location == "disabled":
            location_disabled = True

    if tubport_disabled and location_disabled:
        return None
    if tubport_disabled and not location_disabled:
        raise ValueError("tub.port is disabled, but not tub.location")
    if location_disabled and not tubport_disabled:
        raise ValueError("tub.location is disabled, but not tub.port")

    if cfg_tubport is None:
        # For 'tub.port', tahoe.cfg overrides the individual file on
        # disk. So only read _portnumfile if tahoe.cfg doesn't
        # provide a value.
        if os.path.exists(portnumfile):
            file_tubport = fileutil.read(portnumfile).strip()
            tubport = _convert_tub_port(file_tubport)
        else:
            tubport = "tcp:%d" % iputil.allocate_tcp_port()
            fileutil.write_atomically(portnumfile, tubport + "\n",
                                      mode="")
    else:
        tubport = _convert_tub_port(cfg_tubport)

    if cfg_location is None:
        cfg_location = "AUTO"

    reveal_ip = configutil.config_item(config, "node", "reveal-IP-address", True, boolean=True)
    # Replace the location "AUTO", if present, with the detected local
    # addresses. Don't probe for local addresses unless necessary.
    split_location = cfg_location.split(",")
    if "AUTO" in split_location:
        if not reveal_ip:
            raise PrivacyError("tub.location uses AUTO")
        local_addresses = iputil.get_local_addresses_sync()
        # tubport must be like "tcp:12345" or "tcp:12345:morestuff"
        local_portnum = int(tubport.split(":")[1])
    new_locations = []
    for loc in split_location:
        if loc == "AUTO":
            new_locations.extend(["tcp:%s:%d" % (ip, local_portnum)
                                  for ip in local_addresses])
        else:
            if not reveal_ip:
                # Legacy hints are "host:port". We use Foolscap's utility
                # function to convert all hints into the modern format
                # ("tcp:host:port") because that's what the receiving
                # client will probably do. We test the converted hint for
                # TCP-ness, but publish the original hint because that
                # was the user's intent.
                from foolscap.connections.tcp import convert_legacy_hint
                converted_hint = convert_legacy_hint(loc)
                hint_type = converted_hint.split(":")[0]
                if hint_type == "tcp":
                    raise PrivacyError("tub.location includes tcp: hint")
            new_locations.append(loc)
    location = ",".join(new_locations)

    return tubport, location


def create_main_tub(config, basedir, i2p_prov, tor_prov,
                    handler_overrides=dict(),
                    certfile='node.pem',
                    portnum_file='client.port'):
    certfile = os.path.join(basedir, "private", certfile)

    # pulled handler_overrides up out of create_tub which used to be in node
    handlers = _create_foolscap_handlers(config, i2p_prov, tor_prov)
    handlers.update(handler_overrides)
    tub_options = _tub_options_from_config(config)
    tub = _create_tub(tub_options, handlers, certFile=certfile)

    # can probably put the next two lines in _tub_portlocation...
    cfg_tubport = configutil.config_item(config, "node", "tub.port", None)
    cfg_location = configutil.config_item(config, "node", "tub.location", None)
    portnumfile = os.path.join(basedir, portnumfile)
    portlocation = _tub_portlocation(cfg_tubport, cfg_location)
    if portlocation:
        tubport, location = portlocation
        for port in tubport.split(","):
            if port in ("0", "tcp:0"):
                raise ValueError("tub.port cannot be 0: you must choose")
            tub.listenOn(port)
        tub.setLocation(location)

    return tub


class Node(service.MultiService):
    # this implements common functionality of both Client nodes and Introducer
    # nodes.
    NODETYPE = "unknown NODETYPE"
    PORTNUMFILE = None
    CERTFILE = "node.pem"
    GENERATED_FILES = []

    def __init__(self, main_tub, i2p_prov, tor_prov, basedir=u"."):
        service.MultiService.__init__(self)
        self.basedir = abspath_expanduser_unicode(unicode(basedir))
        self.config_fname = os.path.join(self.basedir, "tahoe.cfg")
        self._portnumfile = os.path.join(self.basedir, self.PORTNUMFILE)
        fileutil.make_dirs(os.path.join(self.basedir, "private"), 0700)
        with open(os.path.join(self.basedir, "private", "README"), "w") as f:
            f.write(PRIV_README)

        self.config = configutil.read_node_config(basedir)
        nickname_utf8 = self.get_config("node", "nickname", "<unspecified>")
        self.nickname = nickname_utf8.decode("utf-8")
        assert type(self.nickname) is unicode

        self.init_tempdir()
        self.check_privacy()

        self.create_log_tub()
        self.logSource="Node"
        self.setup_logging()

        self._i2p_provider = i2p_prov
        self._i2p_provider.setServiceParent(self)

        self._tor_provider = tor_prov
        self._tor_provider.setServiceParent(self)

        # the "Node-specific" parts of what used to be create_main_tub
        self.tub = main_tub
        self.nodeid = b32decode(self.tub.tubID.upper()) # binary format
        self.write_config("my_nodeid", b32encode(self.nodeid).lower() + "\n")
        self.short_nodeid = b32encode(self.nodeid).lower()[:8] # for printing
        self.tub.setServiceParent(self)
        self._tub_is_listening = bool(len(self.tub.getListeners()) > 0)
        if self._tub_is_listening:
            log("Tub location set to %s" % (self.tub.locationHints[0],))
        else:
            self.log("Tub is not listening")

        #self.init_connections()
        #self.set_tub_options()
        #self.create_main_tub()
        self.create_control_tub()

        self.log("Node constructed. " + get_package_versions_string())
        iputil.increase_rlimits()

    def init_tempdir(self):
        tempdir_config = self.get_config("node", "tempdir", "tmp").decode('utf-8')
        tempdir = abspath_expanduser_unicode(tempdir_config, base=self.basedir)
        if not os.path.exists(tempdir):
            fileutil.make_dirs(tempdir)
        tempfile.tempdir = tempdir
        # this should cause twisted.web.http (which uses
        # tempfile.TemporaryFile) to put large request bodies in the given
        # directory. Without this, the default temp dir is usually /tmp/,
        # which is frequently too small.
        test_name = tempfile.mktemp()
        _assert(os.path.dirname(test_name) == tempdir, test_name, tempdir)

    def get_config(self, section, option, default=_None, boolean=False):
        return config_item(
            self.config, section, option,
            default=default,
            boolean=boolean,
            fname=os.path.join(self.basedir, u"tahoe.cfg"),
        )

    def check_privacy(self):
        self._reveal_ip = self.get_config("node", "reveal-IP-address", True,
                                          boolean=True)

    def create_control_tub(self):
        # the control port uses a localhost-only ephemeral Tub, with no
        # control over the listening port or location
        self.control_tub = Tub()
        portnum = iputil.allocate_tcp_port()
        port = "tcp:%d:interface=127.0.0.1" % portnum
        location = "tcp:127.0.0.1:%d" % portnum
        self.control_tub.listenOn(port)
        self.control_tub.setLocation(location)
        self.log("Control Tub location set to %s" % (location,))
        self.control_tub.setServiceParent(self)

    def create_log_tub(self):
        # The logport uses a localhost-only ephemeral Tub, with no control
        # over the listening port or location. This might change if we
        # discover a compelling reason for it in the future (e.g. being able
        # to use "flogtool tail" against a remote server), but for now I
        # think we can live without it.
        self.log_tub = Tub()
        portnum = iputil.allocate_tcp_port()
        port = "tcp:%d:interface=127.0.0.1" % portnum
        location = "tcp:127.0.0.1:%d" % portnum
        self.log_tub.listenOn(port)
        self.log_tub.setLocation(location)
        self.log("Log Tub location set to %s" % (location,))
        self.log_tub.setServiceParent(self)

    def get_config_from_file(self, name, required=False):
        """Get the (string) contents of a config file, or None if the file
        did not exist. If required=True, raise an exception rather than
        returning None. Any leading or trailing whitespace will be stripped
        from the data."""
        fn = os.path.join(self.basedir, name)
        try:
            return fileutil.read(fn).strip()
        except EnvironmentError:
            if not required:
                return None
            raise

    def write_private_config(self, name, value):
        """Write the (string) contents of a private config file (which is a
        config file that resides within the subdirectory named 'private'), and
        return it.
        """
        privname = os.path.join(self.basedir, "private", name)
        with open(privname, "w") as f:
            f.write(value)

    def get_private_config(self, name, default=_None):
        """Read the (string) contents of a private config file (which is a
        config file that resides within the subdirectory named 'private'),
        and return it. Return a default, or raise an error if one was not
        given.
        """
        privname = os.path.join(self.basedir, "private", name)
        try:
            return fileutil.read(privname).strip()
        except EnvironmentError:
            if os.path.exists(privname):
                raise
            if default is _None:
                raise MissingConfigEntry("The required configuration file %s is missing."
                                         % (quote_output(privname),))
            return default

    def get_or_create_private_config(self, name, default=_None):
        """Try to get the (string) contents of a private config file (which
        is a config file that resides within the subdirectory named
        'private'), and return it. Any leading or trailing whitespace will be
        stripped from the data.

        If the file does not exist, and default is not given, report an error.
        If the file does not exist and a default is specified, try to create
        it using that default, and then return the value that was written.
        If 'default' is a string, use it as a default value. If not, treat it
        as a zero-argument callable that is expected to return a string.
        """
        privname = os.path.join(self.basedir, "private", name)
        try:
            value = fileutil.read(privname)
        except EnvironmentError:
            if os.path.exists(privname):
                raise
            if default is _None:
                raise MissingConfigEntry("The required configuration file %s is missing."
                                         % (quote_output(privname),))
            if isinstance(default, basestring):
                value = default
            else:
                value = default()
            fileutil.write(privname, value)
        return value.strip()

    def write_config(self, name, value, mode="w"):
        """Write a string to a config file."""
        fn = os.path.join(self.basedir, name)
        try:
            fileutil.write(fn, value, mode)
        except EnvironmentError, e:
            self.log("Unable to write config file '%s'" % fn)
            self.log(e)

    def startService(self):
        # Note: this class can be started and stopped at most once.
        self.log("Node.startService")
        # Record the process id in the twisted log, after startService()
        # (__init__ is called before fork(), but startService is called
        # after). Note that Foolscap logs handle pid-logging by itself, no
        # need to send a pid to the foolscap log here.
        twlog.msg("My pid: %s" % os.getpid())
        try:
            os.chmod("twistd.pid", 0644)
        except EnvironmentError:
            pass

        service.MultiService.startService(self)
        self.log("%s running" % self.NODETYPE)
        twlog.msg("%s running" % self.NODETYPE)

    def stopService(self):
        self.log("Node.stopService")
        return service.MultiService.stopService(self)

    def shutdown(self):
        """Shut down the node. Returns a Deferred that fires (with None) when
        it finally stops kicking."""
        self.log("Node.shutdown")
        return self.stopService()

    def setup_logging(self):
        # we replace the formatTime() method of the log observer that
        # twistd set up for us, with a method that uses our preferred
        # timestamp format.
        for o in twlog.theLogPublisher.observers:
            # o might be a FileLogObserver's .emit method
            if type(o) is type(self.setup_logging): # bound method
                ob = o.im_self
                if isinstance(ob, twlog.FileLogObserver):
                    newmeth = types.UnboundMethodType(formatTimeTahoeStyle, ob, ob.__class__)
                    ob.formatTime = newmeth
        # TODO: twisted >2.5.0 offers maxRotatedFiles=50

        lgfurl_file = os.path.join(self.basedir, "private", "logport.furl").encode(get_filesystem_encoding())
        if os.path.exists(lgfurl_file):
            os.remove(lgfurl_file)
        self.log_tub.setOption("logport-furlfile", lgfurl_file)
        lgfurl = self.get_config("node", "log_gatherer.furl", "")
        if lgfurl:
            # this is in addition to the contents of log-gatherer-furlfile
            self.log_tub.setOption("log-gatherer-furl", lgfurl)
        self.log_tub.setOption("log-gatherer-furlfile",
                               os.path.join(self.basedir, "log_gatherer.furl"))

        incident_dir = os.path.join(self.basedir, "logs", "incidents")
        foolscap.logging.log.setLogDir(incident_dir.encode(get_filesystem_encoding()))
        twlog.msg("Foolscap logging initialized")
        twlog.msg("Note to developers: twistd.log does not receive very much.")
        twlog.msg("Use 'flogtool tail -c NODEDIR/private/logport.furl' instead")
        twlog.msg("and read docs/logging.rst")

    def log(self, *args, **kwargs):
        return log.msg(*args, **kwargs)

    def add_service(self, s):
        s.setServiceParent(self)
        return s
