

from allmydata.testing.web import create_fake_tahoe_root

import pytest


def test_retrieve_cap():
    """
    WebUI Fake can serve a read-capability back
    """

    root = create_fake_tahoe_root(
        capabilities=[
            "URI:CHK:7temc4rarxsffz4zrvze3feifi:7rclszi4oz42szvs7ntoimkfj52527ng3gttvqzdo7hr4duwtgcq:1:5:353911",
        ]
    )
    print(root)
