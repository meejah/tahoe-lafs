
import sys
from os.path import join

from twisted.web.client import Agent, readBody
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.error import ProcessDone, ConnectionRefusedError
from twisted.internet.task import deferLater



class _DumpOutputProtocol(ProcessProtocol):
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


@inlineCallbacks
def spawn_client(reactor, node_dir, mode='client'):
    """
    :param mode: 'client (the default) or 'storage' or 'introducer'
    """
    print("spawn_client", node_dir, mode)
    assert mode in ('client', 'storage', 'introducer')
    protocol = _DumpOutputProtocol(None)

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
    process.exited = protocol.done
    agent = Agent(reactor)

    while True:
        print("looping")
        yield deferLater(reactor, 0.1, lambda: None)
        print("waited")
        try:
            nodeuri = join(node_dir, 'node.url')
            with open(nodeuri, 'r') as f:
                uri = '{}is_ready?mode={}'.format(f.read().strip(), mode)
            print("uri is", uri)
        except IOError as e:
            print("IOERROR", nodeuri, e)
        else:
            print("requesting", uri)
            try:
                resp = yield agent.request('GET', uri)
            except ConnectionRefusedError:
                continue
            print("got resp", resp, dir(resp))
            if resp.code == 200:
                text = yield readBody(resp)
                print("got text", text, uri)
                if isinstance(text, str):
                    if text.strip().lower() == 'ok':
                        break

    returnValue(process)
