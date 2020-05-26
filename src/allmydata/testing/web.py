import io
import os

import attr

from twisted.internet import defer
from twisted.python.filepath import (
    FilePath,
)
from twisted.web.resource import (
    Resource,
)
from twisted.web.client import (
    Agent,
    FileBodyProducer,
)

from treq.client import (
    HTTPClient,
)
from treq.testing import (
    RequestTraversalAgent,
    RequestSequence,
    StubTreq,
)


class _FakeTahoeRoot(Resource):
    """
    This is a sketch of how an in-memory 'fake' of a Tahoe
    WebUI. Ultimately, this will live in Tahoe
    """


@attr.s
class _FakeCapability(object):
    """
    """
    data=attr.ib()


# XXX want to make all kinds of caps, like
# URI:CHK:... URI:DIR2:... etc

import allmydata.uri
KNOWN_CAPABILITES = [
    getattr(allmydata.uri, t).BASE_STRING
    for t in dir(allmydata.uri)
    if hasattr(getattr(allmydata.uri, t), 'BASE_STRING')
]


from allmydata.immutable.upload import BaseUploadable, IUplodable
from os import urandom

@implementer(IUploadable)
class DataUploadable(BaseUploadable):
    # Base gives us:
    # set_upload_status
    # set_default_encoding_parameters
    # get_all_encoding_parameters

    def __init__(self, data, key=None):
        self._data = data
        self._where = 0
        self._key = key if key is not None else urandom(16)

    def get_encryption_key(self):
        return self._key

    def get_size(self):
        return len(self._data)

    @inlineCallbacks
    def read(self, amount):
        data = self._data[self._where : self._where + amount]
        self._where += amount
        returnValue(data)

    def close(self):
        pass

@inlineCallbacks
def create_fake_capability(kind, data):
    assert kind in KNOWN_CAPABILITIES

    # XXX to use a allmydata.immutable.upload.CHKUploader directly,
    # we'd need to instantiate:
    uploader = CHKUploader(storage_broker, secret_holder, progress=None, reactor=None)
    uploadable = DataUploadable(data)
    encrypted_uploadable = EncryptAnUploadable(uploadable)

    results = yield uploader.start(encrypted_uploadable)


    # allmydata.immutable.upload.Uploader is a Service that 'does an upload'?
    # has def upload(uploadable)

    return _FakeCapability(
        data=u"fake data for capability {}".format(cap)
    )


class _FakeTahoeUriHandler(Resource):
    """
    """

    isLeaf = True

    def __init__(self, capabilities):
        self.capabilities = {
            cap: create_fake_capability(cap)
            for cap in capabilities
        }

    def render_GET(self, request):
        print(request)
        print(request.uri)
        return b"URI:DIR2-CHK:some capability"


def create_fake_tahoe_root(capabilities=None):
    """
    Probably should take some params to control what this fake does:
    return errors, pre-populate capabilities, ...
    """
    root = _FakeTahoeRoot()
    root.putChild(
        b"uri",
        _FakeTahoeUriHandler(capabilities),
    )
    return root
