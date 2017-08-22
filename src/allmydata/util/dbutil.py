
import os, sys

from twisted.internet import defer
from twisted.enterprise import adbapi


class DBError(Exception):
    pass

def get_db(dbfile, stderr=sys.stderr,
           create_version=(None, None), updaters={}, just_create=False, dbname="db"):
    """Open or create the given db file. The parent directory must exist.
    create_version=(SCHEMA, VERNUM), and SCHEMA must have a 'version' table.
    Updaters is a {newver: commands} mapping, where e.g. updaters[2] is used
    to get from ver=1 to ver=2. Returns a (sqlite,db) tuple, or raises
    DBError.
    """

    try:
        import sqlite3
        sqlite = sqlite3 # pyflakes whines about 'import sqlite3 as sqlite' ..
    except ImportError:
        from pysqlite2 import dbapi2
        sqlite = dbapi2 # .. when this clause does it too
        # This import should never fail, because setuptools requires that the
        # "pysqlite" distribution is present at start time (if on Python < 2.5).
    must_create = not os.path.exists(dbfile)
    try:
        db = sqlite.connect(dbfile)
    except EnvironmentError as e:
        raise DBError("Unable to create/open db file %s: %s" % (dbfile, e))

    schema, target_version = create_version
    c = db.cursor()

    # Enabling foreign keys allows stricter integrity checking.
    # The default is unspecified according to <http://www.sqlite.org/foreignkeys.html#fk_enable>.
    c.execute("PRAGMA foreign_keys = ON;")

    if must_create:
        c.executescript(schema)
        c.execute("INSERT INTO version (version) VALUES (?)", (target_version,))
        db.commit()

    try:
        c.execute("SELECT version FROM version")
        version = c.fetchone()[0]
    except sqlite.DatabaseError as e:
        # this indicates that the file is not a compatible database format.
        # Perhaps it was created with an old version, or it might be junk.
        raise DBError("db file is unusable: %s" % e)

    if just_create: # for tests
        return (sqlite, db)

    while version < target_version:
        c.executescript(updaters[version+1])
        db.commit()
        version = version+1
    if version != target_version:
        raise DBError("Unable to handle db version %s" % version)

    return (sqlite, db)


def script_to_statements(script):
    """
    convert a SQL script into a list of statements

    this one liner doesn't work because SQL scripts can have
    comments with semicolons in them:

    map(lambda x: x+";", filter(lambda y: len(y) != 0, script.split(';')))

    """
    statement_lines = []
    statements = []
    for line in script.split("\n"):
        statement_lines.append(line)
        l = line.split("--")
        if len(l) == 1 and ';' in line:
            statements.append("\n".join(statement_lines))
            statement_lines = []
    return statements

@defer.inlineCallbacks
def execute_script(connection_pool, script):
    """
    execute all the sql statements.
    connection_pool is the adbapi ConnectionPool
    scripts is a string containing one or more SQL statements separated by ';'
    """
    statements = script_to_statements(script)
    for statement in statements:
        yield connection_pool.runOperation(statement)


@defer.inlineCallbacks
def get_async_db(dbfile_name, stderr=sys.stderr,
           create_version=(None, None), updaters={}, just_create=False, dbname="db",
           journal_mode=None):
    """Open or create the given db file. The parent directory must exist.
    create_version=(SCHEMA, VERNUM), and SCHEMA must have a 'version' table.
    Updaters is a {newver: commands} mapping, where e.g. updaters[2] is used
    to get from ver=1 to ver=2. Returns a (sqlite3,db) tuple, or raises
    DBError.
    """
    must_create = not os.path.exists(dbfile_name)
    try:
        conn = adbapi.ConnectionPool("sqlite3", dbfile_name, check_same_thread=False)
    except EnvironmentError as e:
        raise DBError("Unable to create/open %s file %s: %s" % (dbname, dbfile_name, e))
    except Exception as e:
        print "wtf %s" % e
    schema, target_version = create_version

    # Enabling foreign keys allows stricter integrity checking.
    # The default is unspecified according to <http://www.sqlite.org/foreignkeys.html#fk_enable>.
    yield conn.runOperation("PRAGMA foreign_keys = ON;")

    if journal_mode is not None:
        yield conn.runOperation("PRAGMA journal_mode = %s;" % (journal_mode,))

    if must_create:
        yield execute_script(conn, schema)
        yield conn.runOperation("INSERT INTO version (version) VALUES (?)", (target_version,))

    try:
        fetchall_val = yield conn.runQuery("SELECT version FROM version")
        version = fetchall_val[0][0]
    except Exception as e:
        # this indicates that the file is not a compatible database format.
        # Perhaps it was created with an old version, or it might be junk.
        raise DBError("%s file is unusable: %s" % (dbname, e))

    if just_create: # for tests
        import sqlite3
        defer.returnValue((sqlite3, conn))

    while version < target_version and version+1 in updaters:
        execute_script(conn, updaters[version+1])
        version = version+1
    if version != target_version:
        raise DBError("Unable to handle %s version %s" % (dbname, version))

    import sqlite3
    defer.returnValue((sqlite3, conn))
