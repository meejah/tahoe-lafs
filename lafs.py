"""
Writing down some thoughts on a 'greenfield' Tahoe-LAFS API
"""



async def create_client(reactor, introducer_uri, cached_servers=None):
    """
    :returns: object that implements ITahoeClient and connects to an introducer (only)

    Can optionally provide 'cached_servers' to seed the server list
    before we've contacted the Introducer successfully.
    """
    return _TahoeClient(
        reactor,
        introducer_uri=introducer_uri,
        storage_servers=cached_servers,
    )


async def create_client_static(reactor, storage_servers):
    """
    :returns: object that implements ITahoeClient and connects **only** to
        the provided storage servers.
    """
    return _TahoeClient(
        reactor,
        introducer=None,
        storage_servers=storage_servers,
    )


async def create_client_ipfs(reactor, ipfs_hash):
    """
    :returns: object that implements ITahoeClient connecting to the
        server specified by the JSON at the given IPFS hash
    """
    ipfs_data = await ipfs_client.get(ipfs_hash)  # made-up call
    data = json.loads(ipfs_data)
    # depending on the data received, we could do an "introducer" or a
    # "static storage servers" based grid by calling one of the above
    # create_* methods or by instantiating _TahoeClient() directly.


class ITahoeClient(Interface):
    """
    A Tahoe-LAFS Grid client.
    """

    async def verify(capability_string, progress=None):
        """verify the existence of an item in this Grid

        :param capability_string: any capability-string (write, read
            or verify)

        :param progress: (optional) IProgress instance

        :returns: some kind of verify information? (probably a dict?)
        """
        # Do we need verify vs. verify_immutable? or could just base
        # that on "did we get a writecap or not"...? or can we
        # distinguish "immutable verify cap" and "mutable verify cap"?
        # In any case, we create something like
        # immutable.checker.Checker and .start() it...I think.


    async def get(capability_string, progress=None):
        """retrieve a single item from this Grid

        :param capability_string: the capability to retrieve; will not
            work if its a Verify capability.

        :returns: some sort of streaming thing? IPushProducer instance?
        """

    # XXX probably "more Twisted" to make 'filelike' in all of the
    # below be an IPullProducer implementer? e.g. so we get end-to-end
    # backpressure if we're feeding data to this from some other
    # network-thing.

    # XXX maybe the return-values for the below should be "some dict,
    # which includes 'capability' at least but also some status
    # information and things"...? or it's a 2-tuple of:
    # (capability-string, dict-of-meta-information)
    # (or would it be better to have an IStatus or something [like
    # IProgress] and we optionally forward status information (in
    # real-time, then) to the IStatus object .. thinking 'what would
    # GUIs do?' here)

    async def put_immutable(filelike, progress=None):
    # or: async def put_immutable(pull_producer, progress=None):
    # or: async def put_immutable(pull_producer, progress=None, status=None):
        """
        put a single value into the Grid

        :returns: a read-only capability string
        """

    async def put_mutable(filelike, progress=None):
        """
        put a single **mutable** value into the Grid

        :returns: a write capability string
        """

    async def write_mutable(capability_string, filelike, progress=None):
        """
        overwrite the contents of an existing mutable object

        :returns: true/false? anything?
        """
        # XXX could this just offered as a "capability_string=None"
        # optional arg to put_mutable() instead?


# XXX I was tempted to put a "start" or "run" method on the client,
# but I don't think that's a thing that should exist: the client could
# do on-demand storage-server connections and work just fine, **or**
# it could setup and cache connections, etc -- so all that can be
# hidden behind the above async methods (e.g. if we've decided that
# we've failed to connect to anything and gave up, all the above can
# error-out)


@implementer(ITahoeClient)
class _TahoeClient(object):
    """
    The client of a single Tahoe-LAFS Grid
    """

    def __init__(self, reactor, introducer_uri=None, storage_servers=None):
        """:param introducer_uri: (optional) the Foolscap URI of the Introducer (if using).

        :param storage_servers: (optional) configuration for all
            available Storage servers. If an Introducer is also
            supplied, this serves as an initial value for the
            storage-servers cache. If no Introducer is supplied, this
            serves as the only source of storage-server connection
            information.

        """
        self._reactor = reactor

    # implements all the ITahoeClient methods in terms of calls into
    # allmydata.* existing classes etc. (mostly probably by sucking
    # code out of 'tahoe put', 'tahoe get', etc)


# More random thoughts: we could make an adaptor that converts the
# "more-familiar" key-value store API where you get to decide the keys
# (i.e. "put(key, value)") with a thing that promises to save the
# capabilities for you.
#
# e.g. this could directly drop into anything that speaks memcached
# wire protocol (which is "a lot of things")
#
# This could be a GREAT thing for "Enterprise integrations":
# 'Security people' get to control the "shim" thing (and hence the
# storage layer) BUT can pass off "run us some storage servers" to Ops
# (and not have to trust them to implement security procedures, since
# storage-servers are untrusted) while at the same time giving "the
# other parts of the org" a very familiar API: memcached. This API has
# tons of implementations in all kinds of languages so shouldn't limit
# other development groups very much. The "shim" laywer is
# horizontally scalable (i.e. can add infinite shim servers), up to
# the limit of what the Grid can sustain in write/read capacity
# (e.g. could use ETCD to store key->capabilities mappings and share
# amongst all nodes implementing the 'shim' layer)
#
# This lets Security rapidly deep-six any screwup by deleting the ETCD
# mapping (or changing it to a known-good capability). Issue: we can't
# yet delete particular shares.
