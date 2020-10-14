
from twisted.internet.defer import (
    DeferredList,
    inlineCallbacks,
    returnValue,
)

import attr


@inlineCallbacks
def create(base, storage_names, client_names):
    """
    Create a new Grid in the given directory (which should not already
    exist).

    :param FilePath base: where our grid is
    """
    base.makedirs()
    with base.child(u"README").open("w") as f:
        f.write(
            "Tahoe Grid\n"
            "\n"
            "This was created with the 'tu' command:\n"
            "\n"
            "    tu grid create '{}' --storage {} {}\n"
            "\n"
            "It can be managed with other 'tu grid' commands\n"
            "\n".format(
                base.dirname(),
                len(storage_names),
                " ".join("--client {}".format(c) for c in client_names),
            )
        )

    # all Grids have an Introducer
    introducer = yield create_introducer(base.child("introducer"))

    # create all the storage nodes in parallel
    storage_nodes = yield DeferredList([
        create_storage(
            base.child(storage_name),
            storage_name,
            introducer.furl,
        )
        for storage_name in storage_names
    ])

    # create all the clients in parallel
    client_nodes = yield DeferredList([
        create_client(
            base.child(client_name),
            client_name,
            introducer_furl,
        )
        for client_name in client_names
    ])

    returnValue(
        _Grid(
            introducer=introducer,
            storage_nodes=storage_nodes,
            client_nodes=client_nodes,
        )
    )


@inlineCallbacks
def create_introducer(base):
    """
    """
    base.makedirs()
    yield
    returnValue(
        _Introducer(base)
    )


@attr.s
class _Introducer(object):
    base = attr.ib()

    @property
    def furl(self):
        with self.base.child("private").child("introducer.furl").open("r") as f:
            return f.read().strip()


@inlineCallbacks
def create_storage(base, name, introducer_furl):
    """
    """
    yield


@inlineCallbacks
def create_client(base, name, introducer_furl):
    """
    """
    yield


@attr.s
class _Grid(object):
    """
    A Grid
    """
    introducer = attr.ib()
    storage_nodes = attr.ib()
    client_nodes = attr.ib()
