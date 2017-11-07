import sys
import time
from os import mkdir
from os.path import exists, join
from StringIO import StringIO

from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessExitedAlready, ProcessDone

from allmydata.util.configutil import (
    get_config,
    set_config,
    write_config,
)

import pytest


class _ProcessExitedProtocol(ProcessProtocol):
    """
    Internal helper that .callback()s on self.done when the process
    exits (for any reason).
    """

    def __init__(self):
        self.done = Deferred()

    def processEnded(self, reason):
        self.done.callback(None)


class _CollectOutputProtocol(ProcessProtocol):
    """
    Internal helper. Collects all output (stdout + stderr) into
    self.output, and callback's on done with all of it after the
    process exits (for any reason).
    """
    def __init__(self):
        self.done = Deferred()
        self.output = StringIO()

    def processEnded(self, reason):
        if not self.done.called:
            self.done.callback(self.output.getvalue())

    def processExited(self, reason):
        if not isinstance(reason.value, ProcessDone):
            self.done.errback(reason)

    def outReceived(self, data):
        self.output.write(data)

    def errReceived(self, data):
        print("ERR: {}".format(data))
        self.output.write(data)


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
            self.magic_seen.callback(self)

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

    def got_proto(proto):
        process._protocol = proto
        process._node_dir = node_dir
        return process
    protocol.magic_seen.addCallback(got_proto)
    return protocol.magic_seen


def _create_node(reactor, request, temp_dir, introducer_furl, flog_gatherer, name, web_port,
                 storage=True,
                 magic_text=None,
                 needed=2,
                 happy=3,
                 total=4):
    """
    Helper to create a single node, run it and return the instance
    spawnProcess returned (ITransport)
    """
    node_dir = join(temp_dir, name)
    if web_port is None:
        web_port = ''
    if exists(node_dir):
        created_d = succeed(None)
    else:
        print("creating", node_dir)
        mkdir(node_dir)
        done_proto = _ProcessExitedProtocol()
        args = [
            sys.executable, '-m', 'allmydata.scripts.runner',
            'create-node',
            '--nickname', name,
            '--introducer', introducer_furl,
            '--hostname', 'localhost',
            '--listen', 'tcp',
            '--webport', web_port,
            '--shares-needed', unicode(needed),
            '--shares-happy', unicode(happy),
            '--shares-total', unicode(total),
        ]
        if not storage:
            args.append('--no-storage')
        args.append(node_dir)

        reactor.spawnProcess(
            done_proto,
            sys.executable,
            args,
        )
        created_d = done_proto.done

        def created(_):
            config_path = join(node_dir, 'tahoe.cfg')
            config = get_config(config_path)
            set_config(config, 'node', 'log_gatherer.furl', flog_gatherer)
            write_config(config_path, config)
        created_d.addCallback(created)

    d = Deferred()
    d.callback(None)
    d.addCallback(lambda _: created_d)
    d.addCallback(lambda _: _run_node(reactor, node_dir, request, magic_text))
    return d


def await_file_contents(path, contents, timeout=15):
    start_time = time.time()
    while time.time() - start_time < timeout:
        print("  waiting for '{}'".format(path))
        if exists(path):
            try:
                with open(path, 'r') as f:
                    current = f.read()
            except IOError:
                print("IOError; trying again")
            else:
                if current == contents:
                    return True
                print("  file contents still mismatched")
                print("  wanted: {}".format(contents.replace('\n', ' ')))
                print("     got: {}".format(current.replace('\n', ' ')))
        time.sleep(1)
    if exists(path):
        raise Exception("Contents of '{}' mismatched after {}s".format(path, timeout))
    raise Exception("Didn't find '{}' after {}s".format(path, timeout))


def await_file_vanishes(path, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        print("  waiting for '{}' to vanish".format(path))
        if not exists(path):
            return
        time.sleep(1)
    raise Exception("'{}' still exists after {}s".format(path, timeout))
