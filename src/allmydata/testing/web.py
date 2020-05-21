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


def create_fake_capability(cap):
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
