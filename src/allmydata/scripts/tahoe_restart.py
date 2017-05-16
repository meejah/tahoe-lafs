import os
import sys
import time
import signal
import subprocess
from os.path import join, exists

from allmydata.scripts.common import BasedirOptions
from allmydata.scripts.default_nodedir import _default_nodedir
from allmydata.util.encodingutil import listdir_unicode, quote_local_unicode_path

from .tahoe_start import StartOptions, start
from .tahoe_stop import stop


class RestartOptions(StartOptions):
    subcommand_name = "restart"


def restart(config):
    stderr = config.stderr
    rc = stop(config)
    if rc == 2:
        print >>stderr, "ignoring couldn't-stop"
        rc = 0
    if rc:
        print >>stderr, "not restarting"
        return rc
    return start(config)
