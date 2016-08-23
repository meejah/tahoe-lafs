from __future__ import print_function

import sys
from sys import stdout as _stdout
from os import mkdir, listdir, unlink
from os.path import join, abspath, curdir, exists
from StringIO import StringIO

from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.task import deferLater
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessExitedAlready, ProcessDone

import pytest

pytest_plugins = 'pytest_twisted'

if False:
    # can't get pytest_fixture_setup to run? wanted to try to produce
    # *some* kind of "progress of setting up the grid" ...
    def pytest_fixture_post_finalizer(fixturedef):
        print("FINALIZER", fixturedef)

    def pytest_fixture_setup(fixturedef, request):
        print("fixture: {}\n".format(request))
        yield
        print("ASDFAWET")

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_setup(item):
        print("BEFORE", item)
        yield
        print("AFTER", item)


@pytest.fixture(scope='session')
def reactor():
    # this is a fixture in case we might want to try different
    # reactors for some reason.
    from twisted.internet import reactor as _reactor
    #pytest.blockon(deferLater(_reactor, 2, lambda: None))
    return _reactor


@pytest.fixture(scope='session')
def smoke_dir():
    tahoe_base = abspath(curdir)
    magic_base = join(tahoe_base, 'smoke_magicfolder')
    if not exists(magic_base):
        print("Creating", magic_base)
        mkdir(magic_base)
    return magic_base


@pytest.fixture(scope='session')
def tahoe_binary():
    """
    Finds the 'tahoe' binary, yields complete path
    """
    # FIXME
    return '/home/mike/work-lafs/src/tahoe-lafs/venv/bin/tahoe'


class _ProcessExitedProtocol(ProcessProtocol):
    """
    Internal helper that .callback()s on self.done when the process
    exits (for any reason).
    """

    def __init__(self):
        self.done = Deferred()

    def processEnded(self, reason):
        self.done.callback(None)


class CollectOutputProtocol(ProcessProtocol):
    """
    Internal helper. Collects all output (stdout + stderr) into
    self.output, and callback's on done with all of it after the
    process exits (for any reason).
    """
    def __init__(self):
        self.done = Deferred()
        self.output = StringIO()

    def processEnded(self, reason):
        self.done.callback(self.output.getvalue())

    def processExited(self, reason):
        if not isinstance(reason.value, ProcessDone):
            print("EXIT", reason.value)

    def outReceived(self, data):
        self.output.write(data)

    def errReceived(self, data):
        print("ERR", data)
        self.output.write(data)


class MagicTextProtocol(ProcessProtocol):
    """
    Internal helper. Monitors all stdout looking for a magic string,
    and then .callback()s on self.done and .errback's if the process exits
    """

    def __init__(self, magic_text):
        self.done = Deferred()
        self._magic_text = magic_text
        self._output = StringIO()

    def processEnded(self, reason):
        self.done.errback(reason)

    def outReceived(self, data):
        sys.stdout.write(data)
        self._output.write(data)
        if self._magic_text in self._output.getvalue():
            print("Saw '{}' in the logs".format(self._magic_text))
            self.done.callback(None)

    def errReceived(self, data):
        sys.stdout.write(data)

@pytest.fixture(scope='session')
def introducer(reactor, smoke_dir, tahoe_binary, request):
    config = '''
[node]
nickname = introducer0
web.port = 4560
'''
    intro_dir = join(smoke_dir, 'introducer')
    print("making introducer", intro_dir)
    
    if not exists(intro_dir):
        done_proto = _process_exited_protocol()
        reactor.spawnProcess(
            done_proto,
            tahoe_binary,
            ('tahoe', 'create-introducer', intro_dir),
        )
        pytest.blockon(done_proto.done)
        print("created")

    # over-write the config file with our stuff
    with open(join(intro_dir, 'tahoe.cfg'), 'w') as f:
        f.write(config)

    # on windows, "tahoe start" means: run forever in the foreground,
    # but on linux it means daemonize. "tahoe run" is consistent
    # between platforms.
    protocol = MagicTextProtocol('introducer running')
    process = reactor.spawnProcess(
        protocol,
        tahoe_binary,
        ('tahoe', 'run', intro_dir),
    )

    def cleanup():
        try:
            process.signalProcess('TERM')
        except ProcessExitedAlready:
            pass
    request.addfinalizer(cleanup)
    
    pytest.blockon(protocol.done)
    return process


@pytest.fixture(scope='session')
def introducer_furl(introducer, smoke_dir):
    furl_fname = join(smoke_dir, 'introducer', 'private', 'introducer.furl')
    while not exists(furl_fname):
        print("Don't see {} yet".format(furl_fname))
        time.sleep(.1)
    furl = open(furl_fname, 'r').read()
    return furl


def _run_node(reactor, tahoe_binary, node_dir, request, magic_text):
    if magic_text is None:
        magic_text = "client running"
    protocol = MagicTextProtocol(magic_text)

    # on windows, "tahoe start" means: run forever in the foreground,
    # but on linux it means daemonize. "tahoe run" is consistent
    # between platforms.
    process = reactor.spawnProcess(
        protocol,
        tahoe_binary,
        ('tahoe', 'run', node_dir),
    )

    def cleanup():
        try:
            process.signalProcess('TERM')
        except ProcessExitedAlready:
            pass
    request.addfinalizer(cleanup)

    # we return the 'process' ITransport instance
    protocol.done.addCallback(lambda _: process)
    return protocol.done
    

def _create_node(reactor, request, smoke_dir, tahoe_binary, introducer_furl, name, web_port, storage=True, magic_text=None):
    """
    Helper to create a single node, run it and return the instance
    spawnProcess returned (ITransport)
    """
    node_dir = join(smoke_dir, name)
    if web_port is None:
        web_port = ''
    if not exists(node_dir):
        print("creating", node_dir)
        mkdir(node_dir)
        done_proto = _process_exited_protocol()
        args = [
            'tahoe',
            'create-node',
            '--nickname', name,
            '--introducer', introducer_furl,
        ]
        if not storage:
            args.append('--no-storage')
        args.append(node_dir)

        reactor.spawnProcess(
            done_proto,
            tahoe_binary,
            args,
        )
        pytest.blockon(done_proto.done)

        with open(join(node_dir, 'tahoe.cfg'), 'w') as f:
            f.write('''
[node]
nickname = %(name)s
web.port = %(web_port)s
web.static = public_html

[client]
# Which services should this client connect to?
introducer.furl = %(furl)s
shares.needed = 2
shares.happy = 3
shares.total = 4
''' % {
    'name': name,
    'furl': introducer_furl,
    'web_port': web_port,
})

    return _run_node(reactor, tahoe_binary, node_dir, request, magic_text)
    

@pytest.fixture(scope='session')
def storage_nodes(reactor, smoke_dir, tahoe_binary, introducer, introducer_furl, request):
    nodes = []
    # start all 5 nodes in parallel
    for x in range(5):
        name = 'node{}'.format(x)
        # tub_port = 9900 + x
        nodes.append(
            _create_node(
                reactor, request, smoke_dir, tahoe_binary, introducer_furl, name,
                web_port=None, storage=True,
            )
        )
    nodes = pytest.blockon(DeferredList(nodes))
    return nodes


@pytest.fixture(scope='session')
def alice(reactor, smoke_dir, tahoe_binary, introducer_furl, storage_nodes, request):
    process = pytest.blockon(
        _create_node(
            reactor, request, smoke_dir, tahoe_binary, introducer_furl, "alice",
            web_port="tcp:9980:interface=localhost",
            storage=False,
        )
    )
    try:
        mkdir(join(smoke_dir, 'magic-alice'))
    except OSError:
        pass
    return process


@pytest.fixture(scope='session')
def bob(reactor, smoke_dir, tahoe_binary, introducer_furl, storage_nodes, request):
    process = pytest.blockon(
        _create_node(
            reactor, request, smoke_dir, tahoe_binary, introducer_furl, "bob",
            web_port="tcp:9981:interface=localhost",
            storage=False,
        )
    )
    try:
        mkdir(join(smoke_dir, 'magic-bob'))
    except OSError:
        pass
    return process


@pytest.fixture(scope='session')
def alice_invite(reactor, alice, tahoe_binary, smoke_dir, request):
    node_dir = join(smoke_dir, 'alice')

    # XXX need some way to find out "is grid ready for action" at this
    # point ...

    # XXX hmm, maybe we can just nuke alice's process and it'll get
    # re-started next time we ask for "alice" fixture...?

    print("creating magicfolder\n\n\n")
    proto = CollectOutputProtocol()
    transport = reactor.spawnProcess(
        proto,
        tahoe_binary,
        [
            'tahoe', 'magic-folder', 'create',
            '--basedir', node_dir, 'magik:', 'alice',
            join(smoke_dir, 'magic-alice'),
        ]
    )
    pytest.blockon(proto.done)

    print("making invite\n\n\n")
    proto = CollectOutputProtocol()
    transport = reactor.spawnProcess(
        proto,
        tahoe_binary,
        [
            'tahoe', 'magic-folder', 'invite',
            '--basedir', node_dir, 'magik:', 'bob',
        ]
    )
    pytest.blockon(proto.done)
    invite = proto.output.getvalue()
    print("invite from alice", invite)

    # before magic-folder works, we have to stop and restart (this is
    # crappy for the tests -- can we fix it in magic-folder?)
    proto = CollectOutputProtocol()
    transport = reactor.spawnProcess(
        proto,
        tahoe_binary,
        [
            'tahoe', 'stop', node_dir
        ]
    )
    pytest.blockon(proto.done)

    magic_text = 'Completed initial Magic Folder scan successfully'
    pytest.blockon(_run_node(reactor, tahoe_binary, node_dir, request, magic_text))
    return invite


@pytest.fixture(scope='session')
def magic_folder(reactor, alice_invite, alice, bob, tahoe_binary, smoke_dir, request):
    print("pairing magic-folder")
    bob_dir = join(smoke_dir, 'bob')
    proto = CollectOutputProtocol()
    transport = reactor.spawnProcess(
        proto,
        tahoe_binary,
        [
            'tahoe', 'magic-folder', 'join',
            '--basedir', bob_dir,
            alice_invite,
            join(smoke_dir, 'magic-bob'),
        ]
    )
    pytest.blockon(proto.done)

    # before magic-folder works, we have to stop and restart (this is
    # crappy for the tests -- can we fix it in magic-folder?)
    proto = CollectOutputProtocol()
    transport = reactor.spawnProcess(
        proto,
        tahoe_binary,
        [
            'tahoe', 'stop', bob_dir
        ]
    )
    pytest.blockon(proto.done)
    
    magic_text = 'Completed initial Magic Folder scan successfully'
    pytest.blockon(_run_node(reactor, tahoe_binary, bob_dir, request, magic_text))

    print("joined and shit")
    return (join(smoke_dir, 'magic-alice'), join(smoke_dir, 'magic-bob'))
