import os

from ConfigParser import SafeConfigParser, NoOptionError, NoSectionError


class UnknownConfigError(Exception):
    """
    An unknown config item was found.

    This is possibly raised by validate_config()
    """


class _None:  # used as a marker in get_config()
    pass


def _maybe_error_about_old_config_files(basedir, generated_files=[]):
    """
    If any old configuration files are detected, raise OldConfigError.
    """

    oldfnames = set()
    for name in [
        'nickname', 'webport', 'keepalive_timeout', 'log_gatherer.furl',
        'disconnect_timeout', 'advertised_ip_addresses', 'introducer.furl',
        'helper.furl', 'key_generator.furl', 'stats_gatherer.furl',
        'no_storage', 'readonly_storage', 'sizelimit',
        'debug_discard_storage', 'run_helper']:
        if name not in generated_files:
            fullfname = os.path.join(basedir, name)
            if os.path.exists(fullfname):
                oldfnames.add(fullfname)
    if oldfnames:
        e = OldConfigError(oldfnames)
        twlog.msg(e)
        raise e


def read_node_config(basedir):
    """
    read and return Tahoe's configuration as a ConfigParser
    """
    config_fname = os.path.join(basedir, "tahoe.cfg")

    _maybe_error_about_old_config_files(basedir)
    config = SafeConfigParser()

    try:
        config = get_config(config_fname)
    except EnvironmentError:
        if os.path.exists(config_fname):
            raise
    return config


def get_config(tahoe_cfg):
    config = SafeConfigParser()
    f = open(tahoe_cfg, "rb")
    try:
        # Skip any initial Byte Order Mark. Since this is an ordinary file, we
        # don't need to handle incomplete reads, and can assume seekability.
        if f.read(3) != '\xEF\xBB\xBF':
            f.seek(0)
        config.readfp(f)
    finally:
        f.close()
    return config


def _contains_unescaped_hash(item):
    characters = iter(item)
    for c in characters:
        if c == '\\':
            characters.next()
        elif c == '#':
            return True

    return False


def config_item(config, section, option, default=_None, boolean=False, fname=''):
    try:
        if boolean:
            return config.getboolean(section, option)

        item = config.get(section, option)
        if option.endswith(".furl") and _contains_unescaped_hash(item):
            raise UnescapedHashError(section, option, item)

        return item
    except (NoOptionError, NoSectionError):
        if default is _None:
            raise MissingConfigEntry("%s is missing the [%s]%s entry"
                                     % (quote_output(fname), section, option))
        return default


def set_config(config, section, option, value):
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, option, value)
    assert config.get(section, option) == value


def write_config(tahoe_cfg, config):
    f = open(tahoe_cfg, "wb")
    try:
        config.write(f)
    finally:
        f.close()


def validate_config(fname, cfg, valid_sections):
    """
    raises UnknownConfigError if there are any unknown sections or config
    values.
    """
    for section in cfg.sections():
        try:
            valid_in_section = valid_sections[section]
        except KeyError:
            raise UnknownConfigError(
                "'{fname}' contains unknown section [{section}]".format(
                    fname=fname,
                    section=section,
                )
            )
        for option in cfg.options(section):
            if option not in valid_in_section:
                raise UnknownConfigError(
                    "'{fname}' section [{section}] contains unknown option '{option}'".format(
                        fname=fname,
                        section=section,
                        option=option,
                    )
                )
