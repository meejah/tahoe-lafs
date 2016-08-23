import time
import shutil
from os import mkdir, unlink, listdir
from os.path import join, exists

import util

# tests converted from check_magicfolder_smoke.py


def test_alice_writes_bob_receives(magic_folder):
    alice_dir, bob_dir = magic_folder

    with open(join(alice_dir, "first_file"), "w") as f:
        f.write("alice wrote this")

    util.await_file_contents(join(bob_dir, "first_file"), "alice wrote this")
    return


def test_bob_writes_alice_receives(magic_folder):
    alice_dir, bob_dir = magic_folder

    with open(join(bob_dir, "second_file"), "w") as f:
        f.write("bob wrote this")

    util.await_file_contents(join(alice_dir, "second_file"), "bob wrote this")
    return


def test_alice_deletes(magic_folder):
    # alice writes a file, waits for bob to get it and then deletes it.
    alice_dir, bob_dir = magic_folder

    with open(join(alice_dir, "delfile"), "w") as f:
        f.write("alice wrote this")

    util.await_file_contents(join(bob_dir, "delfile"), "alice wrote this")

    # bob has the file; now alices deletes it
    unlink(join(alice_dir, "delfile"))

    # bob should remove his copy, but preserve a backup
    util.await_file_vanishes(join(bob_dir, "delfile"))
    util.await_file_contents(join(bob_dir, "delfile.backup"), "alice wrote this")
    return


def test_alice_creates_bob_edits(magic_folder):
    alice_dir, bob_dir = magic_folder

    # alice writes a file
    with open(join(alice_dir, "editfile"), "w") as f:
        f.write("alice wrote this")

    util.await_file_contents(join(bob_dir, "editfile"), "alice wrote this")

    # now bob edits it
    with open(join(bob_dir, "editfile"), "w") as f:
        f.write("bob says foo")

    util.await_file_contents(join(alice_dir, "editfile"), "bob says foo")


def test_bob_creates_sub_directory(magic_folder):
    alice_dir, bob_dir = magic_folder

    # bob makes a sub-dir, with a file in it
    mkdir(join(bob_dir, "subdir"))
    with open(join(bob_dir, "subdir", "a_file"), "w") as f:
        f.write("bob wuz here")

    # alice gets it
    util.await_file_contents(join(alice_dir, "subdir", "a_file"), "bob wuz here")

    # now bob deletes it again
    shutil.rmtree(join(bob_dir, "subdir"))

    # alice should delete it as well
    util.await_file_vanishes(join(alice_dir, "subdir", "a_file"))
    # i *think* it's by design that the subdir won't disappear,
    # because a "a_file.backup" should appear...
    util.await_file_contents(join(alice_dir, "subdir", "a_file.backup"), "bob wuz here")


def test_bob_creates_alice_deletes_bob_restores(magic_folder):
    alice_dir, bob_dir = magic_folder

    # bob creates a file
    with open(join(bob_dir, "boom"), "w") as f:
        f.write("bob wrote this")

    util.await_file_contents(
        join(alice_dir, "boom"),
        "bob wrote this"
    )

    # alice deletes it (so bob should as well
    unlink(join(alice_dir, "boom"))
    util.await_file_vanishes(join(bob_dir, "boom"))

    # bob restore it, with new contents
    with open(join(bob_dir, "boom"), "w") as f:
        f.write("bob wrote this again, because reasons")

    # XXX double-check this behavior is correct!

    # alice sees bob's update, but marks it as a conflict (because
    # .. she previously deleted it? does that really make sense)

    util.await_file_contents(
        join(alice_dir, "boom.conflict"),
        "bob wrote this again, because reasons",
    )

    # fix the conflict
    shutil.move(join(alice_dir, "boom.conflict"), join(alice_dir, "boom"))
