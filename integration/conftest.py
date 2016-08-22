from __future__ import print_function

import sys
from os import mkdir, listdir, unlink
from os.path import join, abspath, curdir, exists

from twisted.internet.defer import Deferred
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessExitedAlready

import pytest

pytest_plugins = 'pytest_twisted'


@pytest.fixture(scope='session')
def reactor():
    # this is a fixture in case we might want to try different
    # reactors for some reason.
    from twisted.internet import reactor as _reactor
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


def _process_exited_protocol():
    class Exited(ProcessProtocol):
        done = Deferred()
        def processEnded(self, reason):
            self.done.callback(None)
    return Exited()

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
            
        

    done = Deferred()

    class Daemon(ProcessProtocol):
        def processEnded(self, reason):
            done.errback(reason)
        def outReceived(self, data):
            sys.stdout.write(data)
            sys.stdout.flush()
            if 'introducer running' in data:
                print("Saw 'introducer running' in the logs")
                done.callback(None)
        def errReceived(self, data):
            sys.stdout.write(data)
            sys.stdout.flush()

    # over-write the config file with our stuff
    with open(join(intro_dir, 'tahoe.cfg'), 'w') as f:
        f.write(config)

    # on windows, "tahoe start" means: run forever in the foreground,
    # but on linux it means daemonize. "tahoe run" is consistent
    # between platforms.
    process = reactor.spawnProcess(
        Daemon(),
        tahoe_binary,
        ('tahoe', 'run', intro_dir),
    )

    def cleanup():
        try:
            process.signalProcess('TERM')
        except ProcessExitedAlready:
            pass
    request.addfinalizer(cleanup)
    
    pytest.blockon(done)
    
    return process


@pytest.fixture(scope='session')
def introducer_furl(introducer, smoke_dir):
    furl_fname = join(smoke_dir, 'introducer', 'private', 'introducer.furl')
    while not exists(furl_fname):
        print("Don't see {} yet".format(furl_fname))
        time.sleep(.1)
    furl = open(furl_fname, 'r').read()
    return furl


def _create_node(reactor, request, smoke_dir, tahoe_binary, introducer_furl, name, web_port, storage=True):
    """
    Helper to create a single node, run it and return the process
    instance (IProcessProtocol)
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

        print("doing the thing", args)
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
    else:
        print("re-using alice")

    daemon_d = Deferred()

    class Daemon(ProcessProtocol):
        def processEnded(self, reason):
            daemon_d.errback(reason)
        def outReceived(self, data):
            sys.stdout.write(data)
            sys.stdout.flush()
            if 'client running' in data:
                print("Saw 'client running' in logs")
                daemon_d.callback(None)
        def errReceived(self, data):
            sys.stdout.write(data)
            sys.stdout.flush()

    # on windows, "tahoe start" means: run forever in the foreground,
    # but on linux it means daemonize. "tahoe run" is consistent
    # between platforms.
    process = reactor.spawnProcess(
        Daemon(),
        tahoe_binary,
        ('tahoe', 'run', node_dir),
    )

    def cleanup():
        try:
            process.signalProcess('TERM')
        except ProcessExitedAlready:
            pass
    request.addfinalizer(cleanup)
    
    pytest.blockon(daemon_d)
    
    return process
    

@pytest.fixture(scope='session')
def storage_nodes(reactor, smoke_dir, tahoe_binary, introducer, introducer_furl, request):
    nodes = []
    # technically, we could start all these in parallel ..
    for x in range(5):
        name = 'node{}'.format(x)
        # tub_port = 9900 + x
        process = _create_node(reactor, request, smoke_dir, tahoe_binary, introducer_furl, name, web_port=None, storage=True)
        nodes.append(process)
    return nodes


@pytest.fixture(scope='session')
def alice(reactor, smoke_dir, tahoe_binary, introducer_furl, storage_nodes, request):
    process = _create_node(reactor, request, smoke_dir, tahoe_binary, introducer_furl, "alice", 
                           web_port="tcp:9980:interface=localhost", storage=False)
    print("alice", process)
