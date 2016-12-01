
import sys
from os.path import join

from twisted.web.client import Agent, readBody
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.error import ProcessDone
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
def spawn_client(reactor, node_dir):
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

    @inlineCallbacks
    def await_ready():
        ready = False
        while not ready:
            print("looping")
            yield deferLater(reactor, 0.1, lambda: None)
            print("waited")
            try:
                nodeuri = join(node_dir, 'node.url')
                with open(nodeuri, 'r') as f:
                    uri = '{}is_ready'.format(f.read().strip())
                print("uri is", uri)
            except IOError as e:
                print("IOERROR", nodeuri, e)
                ready = False
            else:
                print("requesting", uri)
                resp = yield agent.request('GET', uri)
                print("got resp", resp, dir(resp))
                if resp.code == 200:
                    text = yield readBody(resp)
                    print("got text", text, uri)
                    if text.strip.lower() == 'ok':
                        ready = True

    yield await_ready()
