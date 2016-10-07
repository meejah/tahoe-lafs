import sys
import json
from os.path import join

from twisted.python import usage
from twisted.internet import defer

from allmydata.scripts.default_nodedir import _default_nodedir
from allmydata.util.encodingutil import listdir_unicode, quote_local_unicode_path
from allmydata.util import configutil


INVITE_SEPARATOR = "+"

class InviteOptions(usage.Options):
    synopsis = "[options] [NODEDIR]"
    description = "Create a client-only Tahoe-LAFS node (no storage server)."

    optParameters = [
        ("total", "t", None, "Total number of shares new node will upload"),
        ("happy", "H", None, "Distinct storage servers new node will upload shares to"),
        ("needed", "n", None, "How many shares are needed to reconstruct files from this node"),
        ("basedir", "C", quote_local_unicode_path(_default_nodedir),
         "Specify which Tahoe base directory should be used."
         " This has the same effect as the global --node-directory option."
         " [default: %s]" % quote_local_unicode_path(_default_nodedir)),
    ]

    def parseArgs(self, *args):
        if len(args) != 1:
            raise usage.UsageError(
                "Provide a single argument: the new node's nickname"
            )
        self['nick'] = args[0].strip()


def identify_node_type(basedir):
    for fn in listdir_unicode(basedir):
        if fn.endswith(u".tac"):
            tac = str(fn)
            break
    else:
        return None

    for t in ("client", "introducer", "key-generator", "stats-gatherer"):
        if t in tac:
            return t
    return None


@defer.inlineCallbacks
def invite(options):
    basedir = unicode(options['basedir'])
    nodetype = identify_node_type(basedir)
    config = configutil.get_config(join(basedir, 'tahoe.cfg'))

    introducer_furl = config.get('client', 'introducer.furl')
    nick = options['nick']

    code_d = defer.Deferred()
    config = {
        "needed": options["needed"] or config.get('client', 'shares.needed'),
        "total": options["total"] or config.get('client', 'shares.total'),
        "happy": options["happy"] or config.get('client', 'shares.happy'),
        "nickname": nick,
        "introducer": introducer_furl,
    }
    
    from twisted.internet import reactor
    import wormhole.xfer_util
    done = wormhole.xfer_util.send(
        reactor,
        appid=u"testing some stuff",
        relay_url=u"ws://wormhole-relay.lothar.com:4000/v1",
        data=json.dumps(config),
        code=None,
        on_code=code_d.callback,
    )
    code = yield code_d
    print(code)
    sys.stdout.flush()
    yield done

    
subCommands = [
    ("invite", None, InviteOptions,
     "Invite a new node to this grid"),
]

dispatch = {
    "invite": invite,
}
