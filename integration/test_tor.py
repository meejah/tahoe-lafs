from __future__ import print_function

import sys
import time
import shutil
from os import mkdir, unlink, listdir
from os.path import join, exists
from StringIO import StringIO

from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessExitedAlready, ProcessDone
from twisted.internet.defer import inlineCallbacks, Deferred
import pytest

import util

# see "conftest.py" for the fixtures (e.g. "magic_folder")

class _ProcessExitedProtocol(ProcessProtocol):
    """
    Internal helper that .callback()s on self.done when the process
    exits (for any reason).
    """

    def __init__(self):
        self.done = Deferred()

    def processEnded(self, reason):
        self.done.callback(None)


class _DumpOutputProtocol(ProcessProtocol):
    """
    Internal helper.
    """
    def __init__(self, f):
        self.done = Deferred()
        self._out = f if f is not None else sys.stdout

    def processEnded(self, reason):
        if not self.done.called:
            self.done.callback(None)

    def processExited(self, reason):
        if not isinstance(reason.value, ProcessDone):
            self.done.errback(reason)

    def outReceived(self, data):
        self._out.write(data)

    def errReceived(self, data):
        self._out.write(data)


class _MagicTextProtocol(ProcessProtocol):
    """
    Internal helper. Monitors all stdout looking for a magic string,
    and then .callback()s on self.done and .errback's if the process exits
    """

    def __init__(self, magic_text):
        self.magic_seen = Deferred()
        self.exited = Deferred()
        self._magic_text = magic_text
        self._output = StringIO()

    def processEnded(self, reason):
        self.exited.callback(None)

    def outReceived(self, data):
        sys.stdout.write(data)
        self._output.write(data)
        if not self.magic_seen.called and self._magic_text in self._output.getvalue():
            print("Saw '{}' in the logs".format(self._magic_text))
            self.magic_seen.callback(None)

    def errReceived(self, data):
        sys.stdout.write(data)


def _run_node(reactor, node_dir, request, magic_text):
    if magic_text is None:
        magic_text = "client running"
    protocol = _MagicTextProtocol(magic_text)

    # on windows, "tahoe start" means: run forever in the foreground,
    # but on linux it means daemonize. "tahoe run" is consistent
    # between platforms.
    process = reactor.spawnProcess(
        protocol,
        sys.executable,
        (
            sys.executable, '-m', 'allmydata.scripts.runner',
            'run',
            node_dir,
        ),
    )
    process.exited = protocol.exited

    def cleanup():
        try:
            process.signalProcess('TERM')
            pytest.blockon(protocol.exited)
        except ProcessExitedAlready:
            pass
    request.addfinalizer(cleanup)

    # we return the 'process' ITransport instance
    # XXX abusing the Deferred; should use .when_magic_seen() or something?
    protocol.magic_seen.addCallback(lambda _: process)
    return protocol.magic_seen



@pytest.inlineCallbacks
def test_onion_service_storage(reactor, request, temp_dir, flog_gatherer, tor_network, introducer_furl):

    name = 'carol'
    node_dir = join(temp_dir, name)
    web_port = ''

    if True:
        print("creating", node_dir)
        mkdir(node_dir)
        proto = _DumpOutputProtocol(None)
        reactor.spawnProcess(
            proto,
            sys.executable,
            (
                sys.executable, '-m', 'allmydata.scripts.runner',
                'create-node',
                '--nickname', name,
                '--introducer', introducer_furl,
                '--hide-ip',
                '--tor-control-port', 'tcp:localhost:8008',
                '--listen', 'tor',
                node_dir,
            )
        )
        yield proto.done

    with open(join(node_dir, 'tahoe.cfg'), 'w') as f:
        f.write('''
[node]
nickname = %(name)s
web.port = %(web_port)s
web.static = public_html
log_gatherer.furl = %(log_furl)s

[tor]
control.port = tcp:localhost:8008
onion.external_port = 3457
onion.local_port = 55767
onion = true
onion.private_key_file = private/tor_onion.privkey

[client]
# Which services should this client connect to?
introducer.furl = %(furl)s
shares.needed = 1
shares.happy = 1
shares.total = 2

''' % {
    'name': name,
    'furl': introducer_furl,
    'web_port': web_port,
    'log_furl': flog_gatherer,
})

    _run_node(reactor, node_dir, request, None)
    yield Deferred()
