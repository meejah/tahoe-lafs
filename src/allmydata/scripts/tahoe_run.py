from .tahoe_daemonize import daemonize, DaemonizeOptions


class RunOptions(DaemonizeOptions):
    subcommand_name = "run"


def run(config):
    config.twistd_args = config.twistd_args + ("--nodaemon",)
    # Previously we would do the equivalent of adding ("--logfile",
    # "tahoesvc.log"), but that redirects stdout/stderr which is often
    # unhelpful, and the user can add that option explicitly if they want.

    return daemonize(config)
