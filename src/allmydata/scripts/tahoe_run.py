import os
import sys
import time
import signal
import subprocess
from os.path import join, exists

from allmydata.scripts.common import BasedirOptions
from allmydata.scripts.default_nodedir import _default_nodedir
from allmydata.util.encodingutil import listdir_unicode, quote_local_unicode_path

from .tahoe_daemonize import daemonize, DaemonizeOptions


class RunOptions(DaemonizeOptions):
    subcommand_name = "run"


def run(config):
    config.twistd_args = config.twistd_args + ("--nodaemon",)
    # Previously we would do the equivalent of adding ("--logfile",
    # "tahoesvc.log"), but that redirects stdout/stderr which is often
    # unhelpful, and the user can add that option explicitly if they want.

    return daemonize(config)
