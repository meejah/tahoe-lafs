
import os
import sys
import json
import time
from datetime import datetime

from pycryptopp.publickey import ed25519  # perhaps NaCl instead? other code uses this though

from allmydata.scripts.common import BaseOptions
from allmydata.util.abbreviate import abbreviate_time
from twisted.python import usage
from twisted.python.filepath import FilePath
from allmydata.util import fileutil
from allmydata.util import base32
from allmydata.util import keyutil
from twisted.internet.defer import inlineCallbacks, returnValue


class CreateOptions(BaseOptions):
    description = (
        "Create a new identity key and configuration of a Grid Manager"
    )


class ShowIdentityOptions(BaseOptions):
    description = (
        "Show the public identity key of a Grid Manager\n"
        "\n"
        "This is what you give to clients to add to their configuration"
        " so they use announcements from this Grid Manager"
    )


class AddOptions(BaseOptions):
    description = (
        "Add a new storage-server's key to a Grid Manager configuration\n"
        "using NAME and PUBIC_KEY (comes from a node.pubkey file)"
    )

    def getSynopsis(self):
        return "{} add NAME PUBLIC_KEY".format(BaseOptions.getSynopsis())

    def parseArgs(self, *args, **kw):
        BaseOptions.parseArgs(self, **kw)
        if len(args) != 2:
            raise usage.UsageError(
                "Requires two arguments: name public_key"
            )
        self['name'] = unicode(args[0])
        try:
            # WTF?! why does it want 'str' and not six.text_type?
            self['storage_public_key'] = keyutil.parse_pubkey(args[1])
        except Exception as e:
            raise usage.UsageError(
                "Invalid public_key argument: {}".format(e)
            )


class RemoveOptions(BaseOptions):
    description = (
        "Remove a storage-server from a Grid Manager configuration"
    )

    def parseArgs(self, *args, **kw):
        BaseOptions.parseArgs(self, **kw)
        if len(args) != 1:
            raise usage.UsageError(
                "Requires one arguments: name"
            )
        self['name'] = unicode(args[0])


class ListOptions(BaseOptions):
    description = (
        "List all storage servers in this Grid Manager"
    )


class SignOptions(BaseOptions):
    description = (
        "Create and sign a new certificate for a storage-server"
    )

    def getSynopsis(self):
        return "{} NAME".format(super(SignOptions, self).getSynopsis())

    def parseArgs(self, *args, **kw):
        BaseOptions.parseArgs(self, **kw)
        if len(args) != 1:
            raise usage.UsageError(
                "Requires one argument: name"
            )
        self['name'] = unicode(args[0])


class GridManagerOptions(BaseOptions):
    subCommands = [
        ["create", None, CreateOptions, "Create a Grid Manager."],
        ["public-identity", None, ShowIdentityOptions, "Get the public-key for this Grid Manager."],
        ["add", None, AddOptions, "Add a storage server to this Grid Manager."],
        ["remove", None, RemoveOptions, "Remove a storage server from this Grid Manager."],
        ["list", None, ListOptions, "List all storage servers in this Grid Manager."],
        ["sign", None, SignOptions, "Create and sign a new Storage Certificate."],
    ]

    optParameters = [
        ("config", "c", None, "How to find the Grid Manager's configuration")
    ]

    def postOptions(self):
        if not hasattr(self, 'subOptions'):
            raise usage.UsageError("must specify a subcommand")
        if self['config'] is None:
            raise usage.UsageError("Must supply configuration with --config")

    description = (
        'A "grid-manager" consists of some data defining a keypair (along with '
        'some other details) and Tahoe sub-commands to manipulate the data and '
        'produce certificates to give to storage-servers. Certificates assert '
        'the statement: "Grid Manager X suggests you use storage-server Y to '
        'upload shares to" (X and Y are public-keys).'
        '\n\n'
        'Clients can use Grid Managers to decide which storage servers to '
        'upload shares to. They do this by adding one or more Grid Manager '
        'public keys to their config.'
    )


def _create_gridmanager():
    return _GridManager(ed25519.SigningKey(os.urandom(32)), {})

def _create(gridoptions, options):
    """
    Create a new Grid Manager
    """
    gm_config = gridoptions['config']

    # pre-conditions check
    fp = None
    if gm_config.strip() != '-':
        fp = FilePath(gm_config.strip())
        if fp.exists():
            raise usage.UsageError(
                "The directory '{}' already exists.".format(gm_config)
            )

    gm = _create_gridmanager()
    _save_gridmanager_config(fp, gm)


class _GridManagerStorageServer(object):
    """
    A Grid Manager's notion of a storage server
    """

    def __init__(self, name, public_key, certificates):
        self.name = name
        self._public_key = public_key
        self._certificates = [] if certificates is None else certificates

    def add_certificate(self, certificate):
        self._certificates.append(certificate)

    def public_key(self):
        return "pub-v0-" + base32.b2a(self._public_key.vk_bytes)

    def marshal(self):
        return {
            u"public_key": self.public_key(),
        }

class _GridManager(object):
    """
    A Grid Manager's configuration.
    """

    @staticmethod
    def from_config(config, config_location):
        if not config:
            raise ValueError(
                "Invalid Grid Manager config in '{}'".format(config_location)
            )
        if 'private_key' not in config:
            raise ValueError(
                "Grid Manager config from '{}' requires a 'private_key'".format(
                    config_location,
                )
            )

        private_key_str = config['private_key']
        try:
            private_key_bytes = base32.a2b(private_key_str.encode('ascii'))
            private_key = ed25519.SigningKey(private_key_bytes)
        except Exception as e:
            raise ValueError(
                "Invalid Grid Manager private_key: {}".format(e)
            )

        storage_servers = dict()
        for name, srv_config in config.get(u'storage_servers', {}).items():
            if not 'public_key' in srv_config:
                raise ValueError(
                    "No 'public_key' for storage server '{}'".format(name)
                )
            storage_servers[name] = _GridManagerStorageServer(
                name,
                keyutil.parse_pubkey(srv_config['public_key'].encode('ascii')),
                None,
            )

        gm_version = config.get(u'grid_manager_config_version', None)
        if gm_version != 0:
            raise ValueError(
                "Missing or unknown version '{}' of Grid Manager config".format(
                    gm_version
                )
            )
        return _GridManager(private_key, storage_servers)

    def __init__(self, private_key, storage_servers):
        self._storage_servers = dict() if storage_servers is None else storage_servers
        self._private_key = private_key
        self._version = 0

    @property
    def storage_servers(self):
        return self._storage_servers

    def public_identity(self):
        verify_key_bytes = self._private_key.get_verifying_key_bytes()
        return base32.b2a(verify_key_bytes)

    def sign(self, name):
        try:
            srv = self._storage_servers[name]
        except KeyError:
            raise KeyError(
                u"No storage server named '{}'".format(name)
            )
        cert_info = {
            "expires": int(time.time() + 86400),  # XXX FIXME
            "public_key": srv.public_key(),
            "version": 1,
        }
        cert_data = json.dumps(cert_info, separators=(',',':'), sort_keys=True).encode('utf8')
        sig = self._private_key.sign(cert_data)
        certificate = {
            u"certificate": cert_data,
            u"signature": base32.b2a(sig),
        }

        if True:
            verify_key_bytes = self._private_key.get_verifying_key_bytes()
            vk = ed25519.VerifyingKey(verify_key_bytes)
            assert vk.verify(sig, cert_data) is None, "cert should verify"

        return certificate

    def add_storage_server(self, name, public_key):
        """
        :param name: a user-meaningful name for the server
        :param public_key: ed25519.VerifyingKey the public-key of the
            storage provider (e.g. from the contents of node.pubkey
            for the client)
        """
        if name in self._storage_servers:
            raise KeyError(
                "Already have a storage server called '{}'".format(name)
            )
        assert public_key.vk_bytes
        ss = _GridManagerStorageServer(name, public_key, None)
        self._storage_servers[name] = ss
        return ss

    def remove_storage_server(self, name):
        """
        :param name: a user-meaningful name for the server
        """
        try:
            del self._storage_servers[name]
        except KeyError:
            raise KeyError(
                "No storage server called '{}'".format(name)
            )

    def marshal(self):
        data = {
            u"grid_manager_config_version": self._version,
            u"private_key": base32.b2a(self._private_key.sk_and_vk[:32]),
        }
        if self._storage_servers:
            data[u"storage_servers"] = {
                name: srv.marshal()
                for name, srv
                in self._storage_servers.items()
            }
        return data


def _save_gridmanager_config(file_path, grid_manager):
    """
    Writes a Grid Manager configuration.

    :param file_path: a FilePath specifying where to write the config
        (if None, stdout is used)

    :param grid_manager: a _GridManager instance
    """
    data = json.dumps(
        grid_manager.marshal(),
        indent=4,
    )

    if file_path is None:
        print("{}\n".format(data))
    else:
        fileutil.make_dirs(file_path.path, mode=0o700)
        with file_path.child("config.json").open("w") as f:
            f.write("{}\n".format(data))


def _config_to_filepath(gm_config_location):
    """
    Converts a command-line string specifying the GridManager
    configuration's location into a readable file-like object.

    :param gm_config_location str: a valid path, or '-' (a single
        dash) to use stdin.
    """


def _load_gridmanager_config(gm_config):
    """
    Loads a Grid Manager configuration and returns it (a dict) after
    validating. Exceptions if the config can't be found, or has
    problems.

    :param gm_config str: "-" (a single dash) for stdin or a filename
    """
    fp = None
    if gm_config.strip() != '-':
        fp = FilePath(gm_config.strip())
        if not fp.exists():
            raise RuntimeError(
                "No such directory '{}'".format(gm_config)
            )

    if fp is None:
        gm = json.load(sys.stdin)
    else:
        with fp.child("config.json").open("r") as f:
            gm = json.load(f)

    try:
        return _GridManager.from_config(gm, gm_config)
    except ValueError as e:
        raise usage.UsageError(str(e))


def _show_identity(gridoptions, options):
    """
    Output the public-key of a Grid Manager
    """
    gm_config = gridoptions['config'].strip()
    assert gm_config is not None

    gm = _load_gridmanager_config(gm_config)
    print("pub-v0-{}".format(gm.public_identity()))


def _add(gridoptions, options):
    """
    Add a new storage-server by name to a Grid Manager
    """
    gm_config = gridoptions['config'].strip()
    fp = FilePath(gm_config) if gm_config.strip() != '-' else None

    gm = _load_gridmanager_config(gm_config)
    try:
        gm.add_storage_server(
            options['name'],
            options['storage_public_key'],
        )
    except KeyError:
        raise usage.UsageError(
            "A storage-server called '{}' already exists".format(options['name'])
        )

    _save_gridmanager_config(fp, gm)
    return 0


def _remove(gridoptions, options):
    """
    Remove an existing storage-server by name from a Grid Manager
    """
    gm_config = gridoptions['config'].strip()
    fp = FilePath(gm_config) if gm_config.strip() != '-' else None
    gm = _load_gridmanager_config(gm_config)

    try:
        gm.remove_storage_server(options['name'])
    except KeyError:
        raise usage.UsageError(
            "No storage-server called '{}' exists".format(options['name'])
        )
    cert_count = 0
    while fp.child('{}.cert.{}'.format(options['name'], cert_count)).exists():
        fp.child('{}.cert.{}'.format(options['name'], cert_count)).remove()
        cert_count += 1

    _save_gridmanager_config(fp, gm)
    return 0


def _list(gridoptions, options):
    """
    List all storage-servers known to a Grid Manager
    """
    gm_config = gridoptions['config'].strip()
    fp = FilePath(gm_config) if gm_config.strip() != '-' else None

    gm = _load_gridmanager_config(gm_config)
    for name in sorted(gm.storage_servers.keys()):
        print("{}: {}".format(name, gm.storage_servers[name].public_key()))
        if fp:
            cert_count = 0
            while fp.child('{}.cert.{}'.format(name, cert_count)).exists():
                container = json.load(fp.child('{}.cert.{}'.format(name, cert_count)).open('r'))
                cert_data = json.loads(container['certificate'])
                expires = datetime.fromtimestamp(cert_data['expires'])
                delta = datetime.utcnow() - expires
                if delta.total_seconds() < 0:
                    print("  {}: valid until {} ({})".format(cert_count, expires, abbreviate_time(delta)))
                else:
                    print("  {}: expired ({})".format(cert_count, abbreviate_time(delta)))
                cert_count += 1


def _sign(gridoptions, options):
    """
    sign a new certificate
    """
    gm_config = gridoptions['config'].strip()
    fp = FilePath(gm_config) if gm_config.strip() != '-' else None
    gm = _load_gridmanager_config(gm_config)

    try:
        certificate = gm.sign(options['name'])
    except KeyError:
        raise usage.UsageError(
            "No storage-server called '{}' exists".format(options['name'])
        )

    certificate_data = json.dumps(certificate, indent=4)
    print(certificate_data)
    if fp is not None:
        next_serial = 0
        while fp.child("{}.cert.{}".format(options['name'], next_serial)).exists():
            next_serial += 1
        with fp.child('{}.cert.{}'.format(options['name'], next_serial)).open('w') as f:
            f.write(certificate_data)


grid_manager_commands = {
    CreateOptions: _create,
    ShowIdentityOptions: _show_identity,
    AddOptions: _add,
    RemoveOptions: _remove,
    ListOptions: _list,
    SignOptions: _sign,
}

@inlineCallbacks
def gridmanager(config):
    """
    Runs the 'tahoe grid-manager' command.
    """
    if config.subCommand is None:
        print(config)
        returnValue(1)

    try:
        f = grid_manager_commands[config.subOptions.__class__]
    except KeyError:
        print(config.subOptions, grid_manager_commands.keys())
        print("Unknown command 'tahoe grid-manager {}': no such grid-manager subcommand".format(config.subCommand))
        returnValue(2)

    x = yield f(config, config.subOptions)
    returnValue(x)

subCommands = [
    ["grid-manager", None, GridManagerOptions,
     "Grid Manager subcommands: use 'tahoe grid-manager' for a list."],
]

dispatch = {
    "grid-manager": gridmanager,
}
