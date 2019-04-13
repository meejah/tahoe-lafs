import sys
import time
import json
import shutil
from os import mkdir, unlink, listdir, utime
from os.path import join, exists, getmtime, abspath

from allmydata.util import keyutil
from allmydata.util import base32
from allmydata.util import configutil

import util

import pytest_twisted


@pytest_twisted.inlineCallbacks
def test_create_certificate(reactor, request):
    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "create",
        coverage=request.config.getoption("coverage"),
    )
    privkey_bytes = json.loads(gm_config)['private_key'].encode('ascii')
    privkey, pubkey_bytes = keyutil.parse_privkey(privkey_bytes)
    pubkey = keyutil.parse_pubkey(pubkey_bytes)

    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "add",
        "alice", "pub-v0-kzug3ut2m7ziihf3ndpqlquuxeie4foyl36wn54myqc4wmiwe4ga",
        stdin=gm_config,
        coverage=request.config.getoption("coverage"),
    )
    alice_cert_bytes = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "sign", "alice",
        stdin=gm_config,
        coverage=request.config.getoption("coverage"),
    )
    alice_cert = json.loads(alice_cert_bytes)

    # confirm that alice's certificate is made by the Grid Manager
    # (.verify returns None on success, raises exception on error)
    pubkey.verify(
        base32.a2b(alice_cert['signature'].encode('ascii')),
        alice_cert['certificate'].encode('ascii'),
    )


@pytest_twisted.inlineCallbacks
def test_remove_client(reactor, request):
    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "create",
        coverage=request.config.getoption("coverage"),
    )

    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "add",
        "alice", "pub-v0-kzug3ut2m7ziihf3ndpqlquuxeie4foyl36wn54myqc4wmiwe4ga",
        stdin=gm_config,
        coverage=request.config.getoption("coverage"),
    )
    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "add",
        "bob", "pub-v0-kvxhb3nexybmipkrar2ztfrwp4uxxsmrjzkpzafit3ket4u5yldq",
        stdin=gm_config,
        coverage=request.config.getoption("coverage"),
    )
    assert json.loads(gm_config)['storage_servers'].has_key("alice")
    assert json.loads(gm_config)['storage_servers'].has_key("bob")
    return

    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "remove",
        "alice",
        stdin=gm_config,
        coverage=request.config.getoption("coverage"),
    )
    assert not json.loads(gm_config)['storage_servers'].has_key('alice')
    assert json.loads(gm_config)['storage_servers'].has_key('bob')


@pytest_twisted.inlineCallbacks
def test_remove_last_client(reactor, request):
    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "create",
        coverage=request.config.getoption("coverage"),
    )

    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "add",
        "alice", "pub-v0-kzug3ut2m7ziihf3ndpqlquuxeie4foyl36wn54myqc4wmiwe4ga",
        stdin=gm_config,
        coverage=request.config.getoption("coverage"),
    )
    assert json.loads(gm_config)['storage_servers'].has_key("alice")

    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "remove",
        "alice",
        stdin=gm_config,
        coverage=request.config.getoption("coverage"),
    )
    # there are no storage servers left at all now
    assert not json.loads(gm_config).has_key('storage_servers')


@pytest_twisted.inlineCallbacks
def test_reject_storage_server(reactor, request, storage_nodes, temp_dir, introducer_furl, flog_gatherer):
    gm_config = yield util.run_tahoe(
        reactor, "grid-manager", "--config", "-", "create",
        coverage=request.config.getoption("coverage"),
    )
    privkey_bytes = json.loads(gm_config)['private_key'].encode('ascii')
    privkey, pubkey_bytes = keyutil.parse_privkey(privkey_bytes)
    pubkey = keyutil.parse_pubkey(pubkey_bytes)

    # create certificates for first 2 storage-servers
    for idx, storage in enumerate(storage_nodes[:2]):
        pubkey_fname = join(storage._node_dir, "node.pubkey")
        with open(pubkey_fname, 'r') as f:
            pubkey = f.read().strip()

        gm_config = yield util.run_tahoe(
            reactor, "grid-manager", "--config", "-", "add",
            "storage{}".format(idx), pubkey,
            stdin=gm_config,
            coverage=request.config.getoption("coverage"),
        )
    assert sorted(json.loads(gm_config)['storage_servers'].keys()) == ['storage0', 'storage1']

    # XXX FIXME need to shut-down and nuke carol when we're done this
    # test (i.d. request.addfinalizer)
    carol = yield util._create_node(
        reactor, request, temp_dir, introducer_furl, flog_gatherer, "carol",
        web_port="tcp:9982:interface=localhost",
        storage=False,
    )

    print("inserting certificates")
    # insert their certificates
    for idx, storage in enumerate(storage_nodes[:2]):
        print(idx, storage)
        cert = yield util.run_tahoe(
            reactor, "grid-manager", "--config", "-", "sign",
            "storage{}".format(idx),
            stdin=gm_config,
            coverage=request.config.getoption("coverage"),
        )
        with open(join(storage._node_dir, "gridmanager.cert"), "w") as f:
            f.write(cert)
        from allmydata import client
        config = client.read_config(storage._node_dir, "portnum")
        config.set_config("storage", "grid_management", "True")
        config.set_config("grid_manager_certificates", "default", "gridmanager.cert")

        # re-start this storage server
        storage.signalProcess('TERM')
        yield storage._protocol.exited
        time.sleep(1)
        storage_nodes[idx] = yield util._run_node(
            reactor, storage._node_dir, request, None,
            request.config.getoption('coverage')
        )

    # now only two storage-servers have certificates .. configure
    # carol to have the grid-manager certificate

    config = configutil.get_config(join(carol._node_dir, "tahoe.cfg"))
    print(dir(config))
    config.add_section("grid_managers")
    config.set("grid_managers", "test", pubkey_bytes)
    config.write(open(join(carol._node_dir, "tahoe.cfg"), "w"))
    carol.signalProcess('TERM')
    yield carol._protocol.exited
    time.sleep(1)
    carol = yield util._run_node(
        reactor, carol._node_dir, request, None,
        request.config.getoption('coverage')
    )
    time.sleep(5)

    # try to put something into the grid, which should fail (because
    # carol has happy=3 but should only find storage0, storage1 to be
    # acceptable to upload to)

    try:
        yield util.run_tahoe(
            reactor, "--node-directory", carol._node_dir,
            "put", "-",
            stdin="some content" * 200,
            coverage=request.config.getoption("coverage"),
        )
        assert False, "Should get a failure"
    except Exception as e:
        # depending on the full output being in the error-message
        # here; see util.py
        assert 'UploadUnhappinessError' in str(e)
        print("found expected UploadUnhappinessError")
