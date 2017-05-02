import sys
import time
import shutil
from os import mkdir, unlink, listdir
from os.path import join, exists

from twisted.internet import defer, reactor, task
from twisted.internet.error import ProcessTerminated

import util

import pytest


@pytest.inlineCallbacks
def test_upload_immutable(reactor, temp_dir, introducer_furl, flog_gatherer, storage_nodes, request):

    # hmm, for some reason this still gets storage enabled ...
    process = yield util._create_node(
        reactor, request, temp_dir, introducer_furl, flog_gatherer, "edna",
        web_port="tcp:9983:interface=localhost",
        storage=False,
        needed=3,
        happy=7,
        total=9,
    )


    node_dir = join(temp_dir, 'edna')

    print("waiting 5 seconds unil we're maybe ready")
    yield task.deferLater(reactor, 5, lambda: None)

    # upload a file, which should fail because we have don't have 7
    # storage servers (but happiness is set to 7)
    proto = util._CollectOutputProtocol()
    transport = reactor.spawnProcess(
        proto,
        sys.executable,
        [
            sys.executable, '-m', 'allmydata.scripts.runner',
            '-d', node_dir,
            'put', __file__,
        ]
    )
    try:
        yield proto.done
        assert False, "should raise exception"
    except Exception as e:
        assert isinstance(e, ProcessTerminated)

    output = proto.output.getvalue()
    assert "shares could be placed on only 6 server" in output
