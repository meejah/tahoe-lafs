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
