from __future__ import print_function

import os, sys
from six.moves import StringIO

from twisted.python import usage
from twisted.internet import defer, task, threads

from allmydata.scripts.common import get_default_nodedir
from allmydata.scripts import debug, create_node, cli, \
    stats_gatherer, admin, magic_folder_cli, tahoe_daemonize, tahoe_start, \
    tahoe_stop, tahoe_restart, tahoe_run, tahoe_invite, tahoe_grid_manager
from allmydata.util.encodingutil import quote_output, quote_local_unicode_path, get_io_encoding
from allmydata.util.eliotutil import (
    opt_eliot_destination,
    opt_help_eliot_destinations,
    eliot_logging_service,
)

_default_nodedir = get_default_nodedir()

NODEDIR_HELP = ("Specify which Tahoe node directory should be used. The "
                "directory should either contain a full Tahoe node, or a "
                "file named node.url that points to some other Tahoe node. "
                "It should also contain a file named '"
                + os.path.join('private', 'aliases') +
                "' which contains the mapping from alias name to root "
                "dirnode URI.")
if _default_nodedir:
    NODEDIR_HELP += " [default for most commands: " + quote_local_unicode_path(_default_nodedir) + "]"


# XXX all this 'dispatch' stuff needs to be unified + fixed up
_control_node_dispatch = {
    "daemonize": tahoe_daemonize.daemonize,
    "start": tahoe_start.start,
    "run": tahoe_run.run,
    "stop": tahoe_stop.stop,
    "restart": tahoe_restart.restart,
}

process_control_commands = [
    ["daemonize", None, tahoe_daemonize.DaemonizeOptions, "run a node in the background"],
    ["start", None, tahoe_start.StartOptions, "start a node in the background and confirm it started"],
    ["run", None, tahoe_run.RunOptions, "run a node without daemonizing"],
    ["stop", None, tahoe_stop.StopOptions, "stop a node"],
    ["restart", None, tahoe_restart.RestartOptions, "restart a node"],
]


class Options(usage.Options):
    # unit tests can override these to point at StringIO instances
    stdin = sys.stdin
    stdout = sys.stdout
    stderr = sys.stderr

    subCommands = (     create_node.subCommands
                    +   stats_gatherer.subCommands
                    +   admin.subCommands
                    +   process_control_commands
                    +   debug.subCommands
                    +   cli.subCommands
                    +   magic_folder_cli.subCommands
                    +   tahoe_invite.subCommands
                    +   tahoe_grid_manager.subCommands
                    )

    optFlags = [
        ["quiet", "q", "Operate silently."],
        ["version", "V", "Display version numbers."],
        ["version-and-path", None, "Display version numbers and paths to their locations."],
    ]
    optParameters = [
        ["node-directory", "d", None, NODEDIR_HELP],
        ["wormhole-server", None, u"ws://wormhole.tahoe-lafs.org:4000/v1", "The magic wormhole server to use.", unicode],
        ["wormhole-invite-appid", None, u"tahoe-lafs.org/invite", "The appid to use on the wormhole server.", unicode],
    ]

    def opt_version(self):
        import allmydata
        print(allmydata.get_package_versions_string(debug=True), file=self.stdout)
        self.no_command_needed = True

    def opt_version_and_path(self):
        import allmydata
        print(allmydata.get_package_versions_string(show_paths=True, debug=True), file=self.stdout)
        self.no_command_needed = True

    opt_eliot_destination = opt_eliot_destination
    opt_help_eliot_destinations = opt_help_eliot_destinations

    def __str__(self):
        return ("\nUsage: tahoe [global-options] <command> [command-options]\n"
                + self.getUsage())

    synopsis = "\nUsage: tahoe [global-options]" # used only for subcommands

    def getUsage(self, **kwargs):
        t = usage.Options.getUsage(self, **kwargs)
        t = t.replace("Options:", "\nGlobal options:", 1)
        return t + "\nPlease run 'tahoe <command> --help' for more details on each command.\n"

    def postOptions(self):
        if not hasattr(self, 'subOptions'):
            if not hasattr(self, 'no_command_needed'):
                raise usage.UsageError("must specify a command")
            sys.exit(0)


create_dispatch = {}
for module in (create_node, stats_gatherer):
    create_dispatch.update(module.dispatch)

def parse_options(argv, config=None):
    if not config:
        config = Options()
    config.parseOptions(argv) # may raise usage.error
    return config

def parse_or_exit_with_explanation(argv, stdout=sys.stdout):
    config = Options()
    try:
        parse_options(argv, config=config)
    except usage.error as e:
        c = config
        while hasattr(c, 'subOptions'):
            c = c.subOptions
        print(str(c), file=stdout)
        try:
            msg = e.args[0].decode(get_io_encoding())
        except Exception:
            msg = repr(e)
        print("%s:  %s\n" % (sys.argv[0], quote_output(msg, quotemarks=False)), file=stdout)
        sys.exit(1)
    return config

def dispatch(config,
             stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr):
    command = config.subCommand
    so = config.subOptions
    if config['quiet']:
        stdout = StringIO()
    so.stdout = stdout
    so.stderr = stderr
    so.stdin = stdin

    if command in create_dispatch:
        f = create_dispatch[command]
    elif command in _control_node_dispatch:
        f = _control_node_dispatch[command]
    elif command in debug.dispatch:
        f = debug.dispatch[command]
    elif command in admin.dispatch:
        f = admin.dispatch[command]
    elif command in cli.dispatch:
        # these are blocking, and must be run in a thread
        f0 = cli.dispatch[command]
        f = lambda so: threads.deferToThread(f0, so)
    elif command in magic_folder_cli.dispatch:
        # same
        f0 = magic_folder_cli.dispatch[command]
        f = lambda so: threads.deferToThread(f0, so)
    elif command in tahoe_grid_manager.dispatch:
        f = tahoe_grid_manager.dispatch[command]
    elif command in tahoe_invite.dispatch:
        f = tahoe_invite.dispatch[command]
    else:
        raise usage.UsageError()

    d = defer.maybeDeferred(f, so)
    # the calling convention for CLI dispatch functions is that they either:
    # 1: succeed and return rc=0
    # 2: print explanation to stderr and return rc!=0
    # 3: raise an exception that should just be printed normally
    # 4: return a Deferred that does 1 or 2 or 3
    def _raise_sys_exit(rc):
        sys.exit(rc)

    def _error(f):
        f.trap(usage.UsageError)
        print("Error: {}".format(f.value.message))
        sys.exit(1)
    d.addCallback(_raise_sys_exit)
    d.addErrback(_error)
    return d

def _maybe_enable_eliot_logging(options, reactor):
    if options.get("destinations"):
        service = eliot_logging_service(reactor, options["destinations"])
        # There is no Twisted "Application" around to hang this on so start
        # and stop it ourselves.
        service.startService()
        reactor.addSystemEventTrigger("after", "shutdown", service.stopService)
    # Pass on the options so we can dispatch the subcommand.
    return options

def run():
    assert sys.version_info < (3,), ur"Tahoe-LAFS does not run under Python 3. Please use Python 2.7.x."

    if sys.platform == "win32":
        from allmydata.windows.fixups import initialize
        initialize()
    # doesn't return: calls sys.exit(rc)
    task.react(_run_with_reactor)


def _register_coverage_shutdown_handler(options, reactor):
    """
    see also comment in allmydata/__init__.py

    if COVERAGE_PROCESS_START is set, and "coverage" is installed then
    we're "doing coverage" and should write out the files. However,
    Python doesn't run "atexit" handlers on TERM (unless we register a
    signal handler) and also (for as yet unknown reasons) doesn't seem
    to do so on SIGINT (under Twisted?). So, we make sure coverage
    gets a chance to write files by registering our own handler.
    """

    def save_coverage_data():
        try:
            import coverage
        except ImportError:
            return
        # this tells us if coverage decided to start; it is a Coverage
        # instance if available
        if coverage.process_startup.coverage:
            coverage.process_startup.coverage.stop()
            coverage.process_startup.coverage.save()
    reactor.addSystemEventTrigger("after", "shutdown", save_coverage_data)
    return options


def _run_with_reactor(reactor):
    d = defer.maybeDeferred(parse_or_exit_with_explanation, sys.argv[1:])
    d.addCallback(_maybe_enable_eliot_logging, reactor)
    d.addCallback(_register_coverage_shutdown_handler, reactor)
    d.addCallback(dispatch)
    def _show_exception(f):
        # when task.react() notices a non-SystemExit exception, it does
        # log.err() with the failure and then exits with rc=1. We want this
        # to actually print the exception to stderr, like it would do if we
        # weren't using react().
        if f.check(SystemExit):
            return f # dispatch function handled it
        f.printTraceback(file=sys.stderr)
        sys.exit(1)
    d.addErrback(_show_exception)
    return d

if __name__ == "__main__":
    run()
