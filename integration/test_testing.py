

from allmydata.testing.web import create_fake_tahoe_root

import pytest


def test_retrieve_cap():
    """
    WebUI Fake can serve a read-capability back
    """

    root = create_fake_tahoe_root()
    print(root)

