
<<<<<<< HEAD
"""
This file manages the lease database, and runs the crawler which recovers
from lost-db conditions (both initial boot, DB failures, and shares being
added/removed out-of-band) by adding temporary 'starter leases'. It queries
the storage backend to enumerate existing shares (for each one it needs SI,
shnum, and size). It can also instruct the storage backend to delete a share
which has expired.
"""

import simplejson
import os, time, weakref, re
from zope.interface import implements
from twisted.application import service
from foolscap.api import Referenceable
from allmydata.interfaces import RIStorageServer
from allmydata.util import log, keyutil, dbutil
from allmydata.storage.crawler import ShareCrawler

class BadAccountName(Exception):
    pass
class BadShareID(Exception):
    pass
=======
import time, simplejson

from allmydata.util.assertutil import _assert
from allmydata.util import dbutil
from allmydata.storage.common import si_b2a


class NonExistentShareError(Exception):
    def __init__(self, si_s, shnum):
        Exception.__init__(self, si_s, shnum)
        self.si_s = si_s
        self.shnum = shnum

    def __str__(self):
        return "can't find SI=%r shnum=%r in `shares` table" % (self.si_s, self.shnum)


class LeaseInfo(object):
    def __init__(self, storage_index, shnum, owner_num, renewal_time, expiration_time):
        self.storage_index = storage_index
        self.shnum = shnum
        self.owner_num = owner_num
        self.renewal_time = renewal_time
        self.expiration_time = expiration_time

>>>>>>> Add new files for leasedb.

def int_or_none(s):
    if s is None:
        return s
    return int(s)

<<<<<<< HEAD
STATE_COMING = 0
STATE_STABLE = 1
STATE_GOING = 2

# try to get rid of all the AUTOINCREMENT keys, use things like "SI/shnum"
# and pubkey as the index
LEASE_SCHEMA_V1 = """
CREATE TABLE version
=======

SHARETYPE_IMMUTABLE  = 0
SHARETYPE_MUTABLE    = 1
SHARETYPE_CORRUPTED  = 2
SHARETYPE_UNKNOWN    = 3

SHARETYPES = { SHARETYPE_IMMUTABLE: 'immutable',
               SHARETYPE_MUTABLE:   'mutable',
               SHARETYPE_CORRUPTED: 'corrupted',
               SHARETYPE_UNKNOWN:   'unknown' }

STATE_COMING = 0
STATE_STABLE = 1
STATE_GOING  = 2


LEASE_SCHEMA_V1 = """
CREATE TABLE `version`
>>>>>>> Add new files for leasedb.
(
 version INTEGER -- contains one row, set to 1
);

<<<<<<< HEAD
CREATE TABLE shares
(
 `id` INTEGER PRIMARY KEY AUTOINCREMENT,
 `prefix` VARCHAR(2),
 `storage_index` VARCHAR(26),
 `shnum` INTEGER,
 `size` INTEGER,
 `state` INTEGER -- 0=coming, 1=stable, 2=going
);

CREATE INDEX `prefix` ON shares (`prefix`);
CREATE UNIQUE INDEX `share_id` ON shares (`storage_index`,`shnum`);

CREATE TABLE leases
(
 `id` INTEGER PRIMARY KEY AUTOINCREMENT,
 -- FOREIGN KEY (`share_id`) REFERENCES shares(id), -- not enabled?
 -- FOREIGN KEY (`account_id`) REFERENCES accounts(id),
 `share_id` INTEGER,
 `account_id` INTEGER,
 `renewal_time` INTEGER, -- duration is implicit: expiration-renewal
 `expiration_time` INTEGER -- seconds since epoch
=======
CREATE TABLE `shares`
(
 `storage_index` VARCHAR(26) not null,
 `shnum` INTEGER not null,
 `prefix` VARCHAR(2) not null,
 `backend_key` VARCHAR,         -- not used by current backends; NULL means '$prefix/$storage_index/$shnum'
 `used_space` INTEGER not null,
 `sharetype` INTEGER not null,  -- SHARETYPE_*
 `state` INTEGER not null,      -- STATE_*
 PRIMARY KEY (`storage_index`, `shnum`)
);

CREATE INDEX `prefix` ON `shares` (`prefix`);
-- CREATE UNIQUE INDEX `share_id` ON `shares` (`storage_index`,`shnum`);

CREATE TABLE `leases`
(
 `id` INTEGER PRIMARY KEY AUTOINCREMENT,
 `storage_index` VARCHAR(26) not null,
 `shnum` INTEGER not null,
 `account_id` INTEGER not null,
 `renewal_time` INTEGER not null, -- duration is implicit: expiration-renewal
 `expiration_time` INTEGER,       -- seconds since epoch; NULL means the end of time
 FOREIGN KEY (`storage_index`, `shnum`) REFERENCES `shares` (`storage_index`, `shnum`),
 FOREIGN KEY (`account_id`) REFERENCES `accounts` (`id`)
>>>>>>> Add new files for leasedb.
);

CREATE INDEX `account_id` ON `leases` (`account_id`);
CREATE INDEX `expiration_time` ON `leases` (`expiration_time`);

CREATE TABLE accounts
(
 `id` INTEGER PRIMARY KEY AUTOINCREMENT,
<<<<<<< HEAD
 -- do some performance testing. Z+DS propose using pubkey_vs as the primary
 -- key. That would increase the size of the DB and the index (repeated
 -- pubkeys instead of repeated small integers), right? Also, I think we
 -- actually want to retain the account.id as an abstraction barrier: you
 -- might have sub-accounts which are controlled by signed messages, for
 -- which there is no single pubkey associated with the account.
=======
>>>>>>> Add new files for leasedb.
 `pubkey_vs` VARCHAR(52),
 `creation_time` INTEGER
);
CREATE UNIQUE INDEX `pubkey_vs` ON `accounts` (`pubkey_vs`);

CREATE TABLE account_attributes
(
 `id` INTEGER PRIMARY KEY AUTOINCREMENT,
 `account_id` INTEGER,
 `name` VARCHAR(20),
 `value` VARCHAR(20) -- actually anything: usually string, unicode, integer
<<<<<<< HEAD
 );
=======
);
>>>>>>> Add new files for leasedb.
CREATE UNIQUE INDEX `account_attr` ON `account_attributes` (`account_id`, `name`);

INSERT INTO `accounts` VALUES (0, "anonymous", 0);
INSERT INTO `accounts` VALUES (1, "starter", 0);

<<<<<<< HEAD
=======
CREATE TABLE crawler_history
(
 `cycle` INTEGER,
 `json` TEXT
);
CREATE UNIQUE INDEX `cycle` ON `crawler_history` (`cycle`);
>>>>>>> Add new files for leasedb.
"""

DAY = 24*60*60
MONTH = 30*DAY

class LeaseDB:
<<<<<<< HEAD
    STARTER_LEASE_ACCOUNTID = 1
    STARTER_LEASE_DURATION = 2*MONTH

    # for all methods that start by setting self._dirty=True, be sure to call
    # .commit() when you're done

=======
    ANONYMOUS_ACCOUNTID = 0
    STARTER_LEASE_ACCOUNTID = 1
    STARTER_LEASE_DURATION = 2*MONTH

>>>>>>> Add new files for leasedb.
    def __init__(self, dbfile):
        (self._sqlite,
         self._db) = dbutil.get_db(dbfile, create_version=(LEASE_SCHEMA_V1, 1))
        self._cursor = self._db.cursor()
<<<<<<< HEAD
        self._dirty = False
=======
        self.debug = False
        self.retained_history_entries = 10
>>>>>>> Add new files for leasedb.

    # share management

    def get_shares_for_prefix(self, prefix):
<<<<<<< HEAD
        self._cursor.execute("SELECT `storage_index`,`shnum`"
                             " FROM `shares`"
                             " WHERE `prefix` == ?",
                             (prefix,))
        db_shares = set([(si,shnum) for (si,shnum) in self._cursor.fetchall()])
        return db_shares

    def add_new_share(self, prefix, storage_index, shnum, size):
        # XXX: when test_repairer.Repairer.test_repair_from_deletion_of_1
        # runs, it deletes the share from disk, then the repairer replaces it
        # (in the same place). That results in a duplicate entry in the
        # 'shares' table, which causes a sqlite.IntegrityError . The
        # add_new_share() code needs to tolerate surprises like this: the
        # share might have been manually deleted, and the crawler may not
        # have noticed it yet, so test for an existing entry and use it if
        # present. (and check the code paths carefully to make sure that
        # doesn't get too weird).
        print "ADD_NEW_SHARE", storage_index, shnum
        self._dirty = True
        self._cursor.execute("INSERT INTO `shares`"
                             " VALUES (?,?,?,?,?)",
                             (None, prefix, storage_index, shnum, size))
        shareid = self._cursor.lastrowid
        return shareid

    def add_starter_lease(self, shareid):
        self._dirty = True
        self._cursor.execute("INSERT INTO `leases`"
                             " VALUES (?,?,?,?)",
                             (None, shareid, self.STARTER_LEASE_ACCOUNTID,
                              int(time.time()+self.STARTER_LEASE_DURATION)))
        leaseid = self._cursor.lastrowid
        return leaseid

    def remove_deleted_shares(self, shareids):
        print "REMOVE_DELETED_SHARES", shareids
        # TODO: replace this with a sensible DELETE, join, and sub-SELECT
        shareids2 = []
        for deleted_shareid in shareids:
            storage_index, shnum = deleted_shareid
            self._cursor.execute("SELECT `id` FROM `shares`"
                                 " WHERE `storage_index`=? AND `shnum`=?",
                                 (storage_index, shnum))
            row = self._cursor.fetchone()
            if row:
                shareids2.append(row[0])
        for shareid2 in shareids2:
            self._dirty = True
            self._cursor.execute("DELETE FROM `leases`"
                                 " WHERE `share_id`=?",
                                 (shareid2,))

    def change_share_size(self, storage_index, shnum, size):
        self._dirty = True
        self._cursor.execute("UPDATE `shares` SET `size`=?"
                             " WHERE storage_index=? AND shnum=?",
                             (size, storage_index, shnum))
=======
        """
        Returns a dict mapping (si_s, shnum) pairs to (used_space, sharetype) pairs.
        """
        self._cursor.execute("SELECT `storage_index`,`shnum`, `used_space`, `sharetype`"
                             " FROM `shares`"
                             " WHERE `prefix` == ?",
                             (prefix,))
        db_sharemap = dict([((str(si_s), int(shnum)), (int(used_space), int(sharetype)))
                           for (si_s, shnum, used_space, sharetype) in self._cursor.fetchall()])
        return db_sharemap

    def add_new_share(self, storage_index, shnum, used_space, sharetype):
        si_s = si_b2a(storage_index)
        prefix = si_s[:2]
        if self.debug: print "ADD_NEW_SHARE", prefix, si_s, shnum, used_space, sharetype
        backend_key = None
        # This needs to be an INSERT OR REPLACE because it is possible for add_new_share
        # to be called when this share is already in the database (but not on disk).
        self._cursor.execute("INSERT OR REPLACE INTO `shares`"
                             " VALUES (?,?,?,?,?,?,?)",
                             (si_s, shnum, prefix, backend_key, used_space, sharetype, STATE_COMING))

    def add_starter_lease(self, storage_index, shnum):
        si_s = si_b2a(storage_index)
        if self.debug: print "ADD_STARTER_LEASE", si_s, shnum
        self._dirty = True
        renewal_time = time.time()
        self._cursor.execute("INSERT INTO `leases`"
                             " VALUES (?,?,?,?,?,?)",
                             (None, si_s, shnum, self.STARTER_LEASE_ACCOUNTID,
                              int(renewal_time), int(renewal_time + self.STARTER_LEASE_DURATION)))
        self._db.commit()

    def mark_share_as_stable(self, storage_index, shnum, used_space=None, backend_key=None):
        """
        Call this method after adding a share to backend storage.
        """
        si_s = si_b2a(storage_index)
        if self.debug: print "MARK_SHARE_AS_STABLE", si_s, shnum, used_space
        self._dirty = True
        if used_space is not None:
            self._cursor.execute("UPDATE `shares` SET `state`=?, `used_space`=?, `backend_key`=?"
                                 " WHERE `storage_index`=? AND `shnum`=? AND `state`!=?",
                                 (STATE_STABLE, used_space, backend_key, si_s, shnum, STATE_GOING))
        else:
            _assert(backend_key is None, backend_key=backend_key)
            self._cursor.execute("UPDATE `shares` SET `state`=?"
                                 " WHERE `storage_index`=? AND `shnum`=? AND `state`!=?",
                                 (STATE_STABLE, si_s, shnum, STATE_GOING))
        self._db.commit()
        if self._cursor.rowcount < 1:
            raise NonExistentShareError(si_s, shnum)

    def mark_share_as_going(self, storage_index, shnum):
        """
        Call this method and commit before deleting a share from backend storage,
        then call remove_deleted_share.
        """
        si_s = si_b2a(storage_index)
        if self.debug: print "MARK_SHARE_AS_GOING", si_s, shnum
        self._cursor.execute("UPDATE `shares` SET `state`=?"
                             " WHERE `storage_index`=? AND `shnum`=? AND `state`!=?",
                             (STATE_GOING, si_s, shnum, STATE_COMING))
        self._db.commit()
        if self._cursor.rowcount < 1:
            raise NonExistentShareError(si_s, shnum)

    def remove_deleted_share(self, storage_index, shnum):
        si_s = si_b2a(storage_index)
        if self.debug: print "REMOVE_DELETED_SHARE", si_s, shnum
        # delete leases first to maintain integrity constraint
        self._cursor.execute("DELETE FROM `leases`"
                             " WHERE `storage_index`=? AND `shnum`=?",
                             (si_s, shnum))
        try:
            self._cursor.execute("DELETE FROM `shares`"
                                 " WHERE `storage_index`=? AND `shnum`=?",
                                 (si_s, shnum))
        except Exception:
            self._db.rollback()  # roll back the lease deletion
            raise
        else:
            self._db.commit()

    def change_share_space(self, storage_index, shnum, used_space):
        si_s = si_b2a(storage_index)
        if self.debug: print "CHANGE_SHARE_SPACE", si_s, shnum, used_space
        self._cursor.execute("UPDATE `shares` SET `used_space`=?"
                             " WHERE `storage_index`=? AND `shnum`=?",
                             (used_space, si_s, shnum))
        self._db.commit()
        if self._cursor.rowcount < 1:
            raise NonExistentShareError(si_s, shnum)
>>>>>>> Add new files for leasedb.

    # lease management

    def add_or_renew_leases(self, storage_index, shnum, ownerid,
<<<<<<< HEAD
                            expiration_time):
        # shnum=None means renew leases on all shares
        self._dirty = True
        if shnum is None:
            self._cursor.execute("SELECT `id` FROM `shares`"
                                 " WHERE `storage_index`=?",
                                 (storage_index,))
        else:
            self._cursor.execute("SELECT `id` FROM `shares`"
                                 " WHERE `storage_index`=? AND `shnum`=?",
                                 (storage_index, shnum))
        rows = self._cursor.fetchall()
        if not rows:
            raise BadShareID("can't find SI=%s shnum=%s in `shares` table"
                             % (storage_index, shnum))
        for (shareid,) in rows:
            self._cursor.execute("SELECT `id` FROM `leases`"
                                 " WHERE `share_id`=? AND `account_id`=?",
                                 (shareid, ownerid))
            row = self._cursor.fetchone()
            if row:
                leaseid = row[0]
                self._cursor.execute("UPDATE `leases` SET expiration_time=?"
                                     " WHERE `id`=?",
                                     (expiration_time, leaseid))
            else:
                self._cursor.execute("INSERT INTO `leases` VALUES (?,?,?,?)",
                                     (None, shareid, ownerid, expiration_time))

    # account management

    def get_account_usage(self, accountid):
        self._cursor.execute("SELECT SUM(`size`) FROM shares"
                             " WHERE `id` IN"
                             "  (SELECT DISTINCT `share_id` FROM `leases`"
                             "   WHERE `account_id`=?)",
                             (accountid,))
        row = self._cursor.fetchone()
        if not row or not row[0]: # XXX why did I need the second clause?
            return 0
        return row[0]

    def get_account_attribute(self, accountid, name):
        self._cursor.execute("SELECT `value` FROM `account_attributes`"
                             " WHERE account_id=? AND name=?",
                             (accountid, name))
        row = self._cursor.fetchone()
        if row:
            return row[0]
        return None

    def set_account_attribute(self, accountid, name, value):
        self._cursor.execute("SELECT `id` FROM `account_attributes`"
                             " WHERE `account_id`=? AND `name`=?",
                             (accountid, name))
        row = self._cursor.fetchone()
        if row:
            attrid = row[0]
            self._cursor.execute("UPDATE `account_attributes`"
                                 " SET `value`=?"
                                 " WHERE `id`=?",
                                 (value, attrid))
        else:
            self._cursor.execute("INSERT INTO `account_attributes`"
                                 " VALUES (?,?,?,?)",
                                 (None, accountid, name, value))
        self._db.commit()

    def get_or_allocate_ownernum(self, pubkey_vs):
        if not re.search(r'^[a-zA-Z0-9+-_]+$', pubkey_vs):
            raise BadAccountName("unacceptable characters in pubkey")
        self._cursor.execute("SELECT `id` FROM `accounts` WHERE `pubkey_vs`=?",
                             (pubkey_vs,))
        row = self._cursor.fetchone()
        if row:
            return row[0]
        self._cursor.execute("INSERT INTO `accounts` VALUES (?,?,?)",
                             (None, pubkey_vs, int(time.time())))
        accountid = self._cursor.lastrowid
        self._db.commit()
        return accountid
=======
                            renewal_time, expiration_time):
        """
        shnum=None means renew leases on all shares; do nothing if there are no shares for this storage_index in the `shares` table.

        Raises NonExistentShareError if a specific shnum is given and that share does not exist in the `shares` table.
        """
        si_s = si_b2a(storage_index)
        if self.debug: print "ADD_OR_RENEW_LEASES", si_s, shnum, ownerid, renewal_time, expiration_time
        if shnum is None:
            self._cursor.execute("SELECT `storage_index`, `shnum` FROM `shares`"
                                 " WHERE `storage_index`=?",
                                 (si_s,))
            rows = self._cursor.fetchall()
        else:
            self._cursor.execute("SELECT `storage_index`, `shnum` FROM `shares`"
                                 " WHERE `storage_index`=? AND `shnum`=?",
                                 (si_s, shnum))
            rows = self._cursor.fetchall()
            if not rows:
                raise NonExistentShareError(si_s, shnum)

        for (found_si_s, found_shnum) in rows:
            _assert(si_s == found_si_s, si_s=si_s, found_si_s=found_si_s)
            # XXX can we simplify this by using INSERT OR REPLACE?
            self._cursor.execute("SELECT `id` FROM `leases`"
                                 " WHERE `storage_index`=? AND `shnum`=? AND `account_id`=?",
                                 (si_s, found_shnum, ownerid))
            row = self._cursor.fetchone()
            if row:
                # Note that unlike the pre-LeaseDB code, this allows leases to be backdated.
                # There is currently no way for a client to specify lease duration, and so
                # backdating can only happen in normal operation if there is a timequake on
                # the server and time goes backward by more than 31 days. This needs to be
                # revisited for ticket #1816, which would allow the client to request a lease
                # duration.
                leaseid = row[0]
                self._cursor.execute("UPDATE `leases` SET `renewal_time`=?, `expiration_time`=?"
                                     " WHERE `id`=?",
                                     (renewal_time, expiration_time, leaseid))
            else:
                self._cursor.execute("INSERT INTO `leases` VALUES (?,?,?,?,?,?)",
                                     (None, si_s, found_shnum, ownerid, renewal_time, expiration_time))
            self._db.commit()

    def get_leases(self, storage_index, ownerid):
        si_s = si_b2a(storage_index)
        self._cursor.execute("SELECT `shnum`, `account_id`, `renewal_time`, `expiration_time` FROM `leases`"
                             " WHERE `storage_index`=? AND `account_id`=?",
                             (si_s, ownerid))
        rows = self._cursor.fetchall()
        def _to_LeaseInfo(row):
            (shnum, account_id, renewal_time, expiration_time) = tuple(row)
            return LeaseInfo(storage_index, int(shnum), int(account_id), float(renewal_time), float(expiration_time))
        return map(_to_LeaseInfo, rows)

    def get_lease_ages(self, storage_index, shnum, now):
        si_s = si_b2a(storage_index)
        self._cursor.execute("SELECT `renewal_time` FROM `leases`"
                             " WHERE `storage_index`=? AND `shnum`=?",
                             (si_s, shnum))
        rows = self._cursor.fetchall()
        def _to_age(row):
            return now - float(row[0])
        return map(_to_age, rows)

    def get_unleased_shares_for_prefix(self, prefix):
        if self.debug: print "GET_UNLEASED_SHARES_FOR_PREFIX", prefix
        # This would be simpler, but it doesn't work because 'NOT IN' doesn't support multiple columns.
        #query = ("SELECT `storage_index`, `shnum`, `used_space`, `sharetype` FROM `shares`"
        #         " WHERE (`storage_index`, `shnum`) NOT IN (SELECT DISTINCT `storage_index`, `shnum` FROM `leases`)")

        # This "negative join" should be equivalent.
        self._cursor.execute("SELECT DISTINCT s.storage_index, s.shnum, s.used_space, s.sharetype FROM `shares` s LEFT JOIN `leases` l"
                             " ON (s.storage_index = l.storage_index AND s.shnum = l.shnum)"
                             " WHERE s.prefix = ? AND l.storage_index IS NULL",
                             (prefix,))
        db_sharemap = dict([((str(si_s), int(shnum)), (int(used_space), int(sharetype)))
                           for (si_s, shnum, used_space, sharetype) in self._cursor.fetchall()])
        return db_sharemap

    def remove_leases_by_renewal_time(self, renewal_cutoff_time):
        if self.debug: print "REMOVE_LEASES_BY_RENEWAL_TIME", renewal_cutoff_time
        self._cursor.execute("DELETE FROM `leases` WHERE `renewal_time` < ?",
                             (renewal_cutoff_time,))
        self._db.commit()

    def remove_leases_by_expiration_time(self, expiration_cutoff_time):
        if self.debug: print "REMOVE_LEASES_BY_EXPIRATION_TIME", expiration_cutoff_time
        self._cursor.execute("DELETE FROM `leases` WHERE `expiration_time` IS NOT NULL AND `expiration_time` < ?",
                             (expiration_cutoff_time,))
        self._db.commit()

    # history

    def add_history_entry(self, cycle, entry):
        if self.debug: print "ADD_HISTORY_ENTRY", cycle, entry
        json = simplejson.dumps(entry)
        self._cursor.execute("SELECT `cycle` FROM `crawler_history`")
        rows = self._cursor.fetchall()
        if len(rows) >= self.retained_history_entries:
            first_cycle_to_retain = list(sorted(rows))[-(self.retained_history_entries - 1)][0]
            self._cursor.execute("DELETE FROM `crawler_history` WHERE `cycle` < ?",
                                 (first_cycle_to_retain,))
            self._db.commit()

        try:
            self._cursor.execute("INSERT OR REPLACE INTO `crawler_history` VALUES (?,?)",
                                 (cycle, json))
        except Exception:
            self._db.rollback()  # roll back the deletion of unretained entries
            raise
        else:
            self._db.commit()

    def get_history(self):
        self._cursor.execute("SELECT `cycle`,`json` FROM `crawler_history`")
        rows = self._cursor.fetchall()
        decoded = [(row[0], simplejson.loads(row[1])) for row in rows]
        return dict(decoded)
>>>>>>> Add new files for leasedb.

    def get_account_creation_time(self, owner_num):
        self._cursor.execute("SELECT `creation_time` from `accounts`"
                             " WHERE `id`=?",
                             (owner_num,))
        row = self._cursor.fetchone()
        if row:
            return row[0]
        return None

    def get_all_accounts(self):
        self._cursor.execute("SELECT `id`,`pubkey_vs`"
                             " FROM `accounts` ORDER BY `id` ASC")
        return self._cursor.fetchall()
<<<<<<< HEAD

    def commit(self):
        if self._dirty:
            self._db.commit()
            self._dirty = False


def size_of_disk_file(filename):
    # use new fileutil.? method
    s = os.stat(filename)
    sharebytes = s.st_size
    try:
        # note that stat(2) says that st_blocks is 512 bytes, and that
        # st_blksize is "optimal file sys I/O ops blocksize", which is
        # independent of the block-size that st_blocks uses.
        diskbytes = s.st_blocks * 512
    except AttributeError:
        # the docs say that st_blocks is only on linux. I also see it on
        # MacOS. But it isn't available on windows.
        diskbytes = sharebytes
    return diskbytes



class AccountingCrawler(ShareCrawler):
    """I manage a SQLite table of which leases are owned by which ownerid, to
    support efficient calculation of total space used per ownerid. The
    sharefiles (and their leaseinfo fields) is the canonical source: the
    database is merely a speedup, generated/corrected periodically by this
    crawler. The crawler both handles the initial DB creation, and fixes the
    DB when changes have been made outside the storage-server's awareness
    (e.g. when the admin deletes a sharefile with /bin/rm).
    """

    slow_start = 7 # XXX #*60 # wait 7 minutes after startup
    minimum_cycle_time = 12*60*60 # not more than twice per day

    def __init__(self, server, statefile, leasedb):
        ShareCrawler.__init__(self, server, statefile)
        self._leasedb = leasedb
        self._expire_time = None

    def process_prefixdir(self, cycle, prefix, prefixdir, buckets, start_slice):
        # assume that we can list every bucketdir in this prefix quickly.
        # Otherwise we have to retain more state between timeslices.

        # we define "shareid" as (SI,shnum)
        disk_shares = set() # shareid
        for storage_index in buckets:
            bucketdir = os.path.join(prefixdir, storage_index)
            for sharefile in os.listdir(bucketdir):
                try:
                    shnum = int(sharefile)
                except ValueError:
                    continue # non-numeric means not a sharefile
                shareid = (storage_index, shnum)
                disk_shares.add(shareid)

        # now check the database for everything in this prefix
        db_shares = self._leasedb.get_shares_for_prefix(prefix)

        # add new shares to the DB
        new_shares = (disk_shares - db_shares)
        for shareid in new_shares:
            storage_index, shnum = shareid
            filename = os.path.join(prefixdir, storage_index, str(shnum))
            size = size_of_disk_file(filename)
            sid = self._leasedb.add_new_share(prefix, storage_index,shnum, size)
            self._leasedb.add_starter_lease(sid)

        # remove deleted shares
        deleted_shares = (db_shares - disk_shares)
        self._leasedb.remove_deleted_shares(deleted_shares)

        self._leasedb.commit()


    # these methods are for outside callers to use

    def set_lease_expiration(self, enable, expire_time=None):
        """Arrange to remove all leases that are currently expired, and to
        delete all shares without remaining leases. The actual removals will
        be done later, as the crawler finishes each prefix."""
        self._do_expire = enable
        self._expire_time = expire_time

    def db_is_incomplete(self):
        # don't bother looking at the sqlite database: it's certainly not
        # complete.
        return self.state["last-cycle-finished"] is None
=======
>>>>>>> Add new files for leasedb.
