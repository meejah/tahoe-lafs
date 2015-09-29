import os.path
import re

from mock import Mock, MagicMock, patch

from twisted.trial import unittest
from twisted.internet import defer

from allmydata.interfaces import IDirectoryNode
from allmydata.util import fileutil
from allmydata.scripts.common import get_aliases
from allmydata.test.no_network import GridTestMixin
from .test_cli import CLITestMixin
from allmydata.scripts import magic_folder_cli
from allmydata.util.fileutil import abspath_expanduser_unicode
from allmydata.frontends.magic_folder import MagicFolder, Uploader, Downloader
from allmydata import uri

from zope.interface import implementer


@implementer(IDirectoryNode)
class FakeDirectoryNode(object):
    unknown = False
    readonly = False

    def is_unknown(self):
        return self.unknown
    def is_readonly(self):
        return self.readonly


class FakeINotify(object):
    def __init__(self, *args, **kw):
        self.watches = []

    def watch(self, *args, **kw):
        self.watches.append((args, kw))

    def startReading(self, *args, **kw):
        pass


fake_inotify = MagicMock()
fake_inotify.INotify = FakeINotify


class MagicFolderUnitTests(unittest.TestCase):
    """
    Some unit-tests for magic-folder things.

    All MagicFolder itself does is create and hold a Downloader and
    Uploader and start them both.
    """

    @patch('allmydata.frontends.magic_folder.get_inotify_module', MagicMock(return_value=fake_inotify))
    def setUp(self):
        self.reactor = Mock()
        self.client = Mock()
        self.client.name = 'test-client'
        self.client.nickname = 'test-nick'
        self.db = Mock()
        self.upload_dircap = uri.DirectoryURI()
        self.collective_dircap = uri.ReadonlyDirectoryURI()
        self.tempdir = unicode(os.path.abspath(self.mktemp()))
        os.mkdir(self.tempdir)

        self.upload_node = FakeDirectoryNode()
        self.client.create_node_from_uri = MagicMock(return_value=self.upload_node)
        self.uploader = Uploader(self.client, self.tempdir, self.db, self.upload_dircap, 0.0, self.reactor)

        self.collective_node = FakeDirectoryNode()
        self.collective_node.readonly = True
        self.client.create_node_from_uri = MagicMock(return_value=self.collective_node)
        self.downloader = Downloader(self.client, self.tempdir, self.db, self.collective_dircap, self.reactor)

    @defer.inlineCallbacks
    def test_create_file(self):
        yield self.uploader.start_monitoring()

