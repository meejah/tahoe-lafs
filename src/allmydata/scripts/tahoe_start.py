from allmydata.util.encodingutil import listdir_unicode, quote_local_unicode_path


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
    # Now prepare to turn into a twistd process. This os.chdir is the point
    # of no return.
    os.chdir(basedir)
    twistd_args = []
    if (nodetype in ("client", "introducer")
        and "--nodaemon" not in config.twistd_args
        and "--syslog" not in config.twistd_args
        and "--logfile" not in config.twistd_args):
        fileutil.make_dirs(os.path.join(basedir, u"logs"))
        twistd_args.extend(["--logfile", os.path.join("logs", "twistd.log")])
    twistd_args.extend(config.twistd_args)
    twistd_args.append("DaemonizeTahoeNode") # point at our DaemonizeTahoeNodePlugin

    twistd_config = MyTwistdConfig()
    try:
        twistd_config.parseOptions(twistd_args)
    except usage.error, ue:
        # these arguments were unsuitable for 'twistd'
        print >>err, config
        print >>err, "tahoe %s: usage error from twistd: %s\n" % (config.subcommand_name, ue)
        return 1
    twistd_config.loadedPlugins = {"DaemonizeTahoeNode": DaemonizeTahoeNodePlugin(nodetype, basedir)}

    # On Unix-like platforms:
    #   Unless --nodaemon was provided, the twistd.runApp() below spawns off a
    #   child process, and the parent calls os._exit(0), so there's no way for
    #   us to get control afterwards, even with 'except SystemExit'. If
    #   application setup fails (e.g. ImportError), runApp() will raise an
    #   exception.
    #
    #   So if we wanted to do anything with the running child, we'd have two
    #   options:
    #
    #    * fork first, and have our child wait for the runApp() child to get
    #      running. (note: just fork(). This is easier than fork+exec, since we
    #      don't have to get PATH and PYTHONPATH set up, since we're not
    #      starting a *different* process, just cloning a new instance of the
    #      current process)
    #    * or have the user run a separate command some time after this one
    #      exits.
    #
    #   For Tahoe, we don't need to do anything with the child, so we can just
    #   let it exit.
    #
    # On Windows:
    #   twistd does not fork; it just runs in the current process whether or not
    #   --nodaemon is specified. (As on Unix, --nodaemon does have the side effect
    #   of causing us to log to stdout/stderr.)

    if "--nodaemon" in twistd_args or sys.platform == "win32":
        verb = "running"
    else:
        verb = "starting"

    runner = twistd._SomeApplicationRunner(twistd_config)
    print("RUNNER", runner, dir(runner))

    def post_application():
        import os
        os.write(2, "hello {}\n".format(hash(self)))
        return runner.postApplication()
    runner.postApplication = post_application
    print >>out, "%s node in %s" % (verb, quoted_basedir)

    runner.run()
    # we should only reach here if --nodaemon or equivalent was used
    return 0

