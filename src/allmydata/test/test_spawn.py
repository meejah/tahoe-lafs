

from twisted.trial import unittest
from twisted.internet import reactor



class SpawnTests(unittest.TestCase):

    def test_spawn_client(self):
        spawn_client(reactor, node_dir)
