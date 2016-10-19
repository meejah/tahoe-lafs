
import os
import urllib
from sys import stderr
from types import NoneType
from cStringIO import StringIO
from datetime import datetime

import simplejson

from twisted.python import usage

from allmydata.util.assertutil import precondition

from .common import BaseOptions, BasedirOptions, get_aliases
import tahoe_mv
from allmydata.util.encodingutil import argv_to_abspath, argv_to_unicode, to_str, \
    quote_local_unicode_path
from allmydata.scripts.common_http import do_http, BadResponse
from allmydata.util import fileutil
from allmydata.util import configutil
from allmydata import uri
from allmydata.util.abbreviate import abbreviate_space, abbreviate_time


def _get_json_for_fragment(options, fragment, method='GET', post_args=None):
    nodeurl = options['node-url']
    if nodeurl.endswith('/'):
        nodeurl = nodeurl[:-1]

    url = u'%s/%s' % (nodeurl, fragment)
    if method == 'POST':
        if post_args is None:
            raise ValueError("Must pass post_args= for POST method")
        body = urllib.urlencode(post_args)
    else:
        body = ''
        if post_args is not None:
            raise ValueError("post_args= only valid for POST method")
    resp = do_http(method, url, body=body)
    if isinstance(resp, BadResponse):
        # specifically NOT using format_http_error() here because the
        # URL is pretty sensitive (we're doing /uri/<key>).
        raise RuntimeError(
            "Failed to get json from '%s': %s" % (nodeurl, resp.error)
        )

    data = resp.read()
    parsed = simplejson.loads(data)
    if parsed is None:
        raise RuntimeError("No data from '%s'" % (nodeurl,))
    return parsed


def _get_json_for_cap(options, cap):
    return _get_json_for_fragment(
        options,
        'uri/%s?t=json' % urllib.quote(cap),
    )

def pretty_progress(percent, size=10, ascii=False):
    """
    Displays a unicode or ascii based progress bar of a certain
    length. Should we just depend on a library instead?

    (Originally from txtorcon)
    """

    curr = int(percent / 100.0 * size)
    part = (percent / (100.0 / size)) - curr

    if ascii:
        part = int(part * 4)
        part = '.oO%'[part]
        block_chr = '#'

    else:
        block_chr = u'\u2588'
        # there are 8 unicode characters for vertical-bars/horiz-bars
        part = int(part * 8)

        # unicode 0x2581 -> 2589 are vertical bar chunks, like rainbarf uses
        # and following are narrow -> wider bars
        part = unichr(0x258f - part) # for smooth bar
        # part = unichr(0x2581 + part) # for neater-looking thing

    # hack for 100+ full so we don't print extra really-narrow/high bar
    if percent >= 100.0:
        part = ''
    curr = int(curr)
    return '%s%s%s' % ((block_chr * curr), part, (' ' * (size - curr - 1)))


def do_status(options):
    nodedir = options.global_options["node-directory"]
    with open(os.path.join(nodedir, u'private', u'api_auth_token'), 'rb') as f:
        token = f.read()
    with open(os.path.join(nodedir, u'node.url'), 'r') as f:
        options['node-url'] = f.read().strip()

    # do *all* our data-retrievals first in case there's an error
    try:
        status_data = _get_json_for_fragment(
            options,
            'status?t=json',
            method='POST',
            post_args=dict(
                t='json',
                token=token,
            )
        )
    except Exception as e:
        print >>stderr, "failed to retrieve data: %s" % str(e)
        return 2

    if status_data.get('active', None):
        print("Active operations:")
        for op in status_data['active']:
            hash_prog = int(op['progress-hash'] * 5.0)
            hash_prog_str = ('H' * hash_prog) + ((5 - hash_prog) * '.')
            cipher_prog = int(op['progress-ciphertext'] * 10)
            cipher_prog_str = ('X' * cipher_prog) + ((10 - cipher_prog) * '.')
            push_prog = int(op['progress-encode-push'] * 10)
            push_prog_str = ('U' * push_prog) + ((10 - push_prog) * '.')
            total = (op['progress-hash'] + op['progress-ciphertext'] + op['progress-encode-push']) / 3.0
            print(
                " * {storage-index-string}: {progress} ({total:3}%) {status}".format(
                    progress='[{}|{}|{}]'.format(
                        # click.style(
                        #     pretty_progress(op['progress-hash'] * 100.0, size=5).encode('utf8'), fg='red',
                        # ),
                        # click.style(
                        #     pretty_progress(op['progress-ciphertext'] * 100.0, size=10).encode('utf8'), fg='green',
                        # ),
                        # click.style(
                        #     pretty_progress(op['progress-encode-push'] * 100.0, size=10).encode('utf8'), fg='magenta',
                        # ),
                        hash_prog_str,
                        cipher_prog_str,
                        push_prog_str
                    ),
                    total=int(total * 100.0),
                    **op
                )
            )
    else:
        print("No active operations.")
        return 1  # hmmm...
            
    return 0


class TahoeStatusCommand(BaseOptions):

    optFlags = [
        ["debug", "d", "Print full stack-traces"],
    ]

    def getSynopsis(self):
        return "Usage: tahoe [global-options] status [options]"

    def getUsage(self, width=None):
        t = BaseOptions.getUsage(self, width)
        t += "Various status information"
        return t


subCommands = [
    ["status", None, TahoeStatusCommand,
     "Status."],
]

dispatch = {
    "status": do_status,
}
