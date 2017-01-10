# -*- coding: utf-8 -*-

from twisted.trial import unittest
from allmydata.immutable import happiness_upload
from allmydata.util.happinessutil import augmenting_path_for, residual_network


class HappinessUtils(unittest.TestCase):
    """
    test-cases for utility functions augmenting_path_for and residual_network
    """

    def test_residual_0(self):
        graph = happiness_upload._servermap_flow_graph(
            ['peer0'],
            ['share0'],
            servermap={
                'peer0': ['share0'],
            }
        )
        flow = [[0 for _ in graph] for _ in graph]

        residual, capacity = residual_network(graph, flow)

        # XXX no idea if these are right; hand-verify
        self.assertEqual(residual, [[1], [2], [3], []])
        self.assertEqual(capacity, [[0, 1, 0, 0], [-1, 0, 1, 0], [0, -1, 0, 1], [0, 0, -1, 0]])



class Happiness(unittest.TestCase):

    def test_original_easy(self):
        shares = {'share0', 'share1', 'share2'}
        peers = {'peer0', 'peer1'}
        readonly_peers = set()
        servermap = {
            'peer0': {'share0'},
            'peer1': {'share2'},
        }
        places0 = happiness_upload.HappinessUpload(peers, readonly_peers, shares, servermap).generate_mappings()

        self.assertTrue('peer0' in places0['share0'])
        self.assertTrue('peer1' in places0['share2'])

    def test_placement_simple(self):

        shares = {'share0', 'share1', 'share2'}
        peers = {
            'peer0',
            'peer1',
        }
        readonly_peers = {'peer0'}
        peers_to_shares = {
            'peer0': {'share2'},
            'peer1': [],
        }

        places0 = happiness_upload.share_placement(peers, readonly_peers, shares, peers_to_shares)
        places1 = happiness_upload.HappinessUpload(peers, readonly_peers, shares).generate_mappings()

        if False:
            print("places0")
            for k, v in places0.items():
                print("  {} -> {}".format(k, v))
            print("places1")
            for k, v in places1.items():
                print("  {} -> {}".format(k, v))

        self.assertEqual(
            places0,
            {
                'share0': {'peer1'},
                'share1': {'peer1'},
                'share2': {'peer0'},
            }
        )
