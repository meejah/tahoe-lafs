import os
import sys
import time
import subprocess
from os.path import join, exists

from allmydata.scripts.common import BasedirOptions
from allmydata.scripts.default_nodedir import _default_nodedir
from allmydata.util.encodingutil import listdir_unicode, quote_local_unicode_path

from .tahoe_daemonize import MyTwistdConfig, identify_node_type


class StartOptions(BasedirOptions):
    subcommand_name = "start"
    optParameters = [
        ("basedir", "C", None,
         "Specify which Tahoe base directory should be used."
         " This has the same effect as the global --node-directory option."
         " [default: %s]" % quote_local_unicode_path(_default_nodedir)),
        ]

    def parseArgs(self, basedir=None, *twistd_args):
        # This can't handle e.g. 'tahoe start --nodaemon', since '--nodaemon'
        # looks like an option to the tahoe subcommand, not to twistd. So you
        # can either use 'tahoe start' or 'tahoe start NODEDIR
        # --TWISTD-OPTIONS'. Note that 'tahoe --node-directory=NODEDIR start
        # --TWISTD-OPTIONS' also isn't allowed, unfortunately.

        BasedirOptions.parseArgs(self, basedir)
        self.twistd_args = twistd_args

    def getSynopsis(self):
        return ("Usage:  %s [global-options] %s [options]"
                " [NODEDIR [twistd-options]]"
                % (self.command_name, self.subcommand_name))

    def getUsage(self, width=None):
        t = BasedirOptions.getUsage(self, width) + "\n"
        twistd_options = str(MyTwistdConfig()).partition("\n")[2].partition("\n\n")[0]
        t += twistd_options.replace("Options:", "twistd-options:", 1)
        t += """

Note that if any twistd-options are used, NODEDIR must be specified explicitly
(not by default or using -C/--basedir or -d/--node-directory), and followed by
the twistd-options.
"""
        return t


def start(config):

    out = config.stdout
    err = config.stderr
    basedir = config['basedir']
    quoted_basedir = quote_local_unicode_path(basedir)
    print >>out, "STARTING", quoted_basedir
    if not os.path.isdir(basedir):
        print >>err, "%s does not look like a directory at all" % quoted_basedir
        return 1
    nodetype = identify_node_type(basedir)
    if not nodetype:
        print >>err, "%s is not a recognizable node directory" % quoted_basedir
        return 1

    # 'Originally', "tahoe start" was the command that daemonized. In
    # order to support async startup, we introduced "tahoe daemonize"
    # which does more-or-less what "tahoe start" used to. Now, "tahoe
    # start" spawns "tahoe daemonize" and then determines whether
    # tahoe has started successfully or hasn't (within 5 seconds).

    # before we spawn tahoe, we check if "the log file" exists or not,
    # and if so remember how big it is -- essentially, we're doing
    # "tail -f" to see what "this" incarnation of "tahoe daemonize"
    # spews forth.
    starting_offset = 0
    log_fname = join(basedir, 'logs', 'twistd.log')
    if exists(log_fname):
        with open(log_fname, 'r') as f:
            f.seek(0, 2)
            starting_offset = f.tell()

    # spawn tahoe. Note that since this daemonizes, it should return
    # "pretty fast" and with a zero return-code, or else something
    # Very Bad has happened.
    try:
        subprocess.check_call(['tahoe', 'daemonize'] + sys.argv[2:])
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)

    # now, we have to determine if tahoe has actually started up
    # successfully or not. so, we start sucking up log files and
    # looking for "the magic string", which depends on the node type.

    magic_string = '{} running'.format(nodetype)
    with open(log_fname, 'r') as f:
        f.seek(starting_offset)

        collected = u''
        start = time.time()
        while time.time() - start < 5:
            collected += f.read()
            if magic_string in collected:
                print("Node has started successfully")
                sys.exit(0)
            time.sleep(0.1)

        print("Something has gone wrong starting the node.")
        print("Logs are available in '{}'".format(log_fname))
        print("Collected for this run:")
        print(collected)
        sys.exit(1)
