import time
import shutil
from os import mkdir, unlink
from os.path import join, exists


def await_file_contents(path, contents, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        print("  waiting for '{}'".format(path))
        if exists(path):
            with open(path, 'r') as f:
                current = f.read()
            if current == contents:
                return True
            print("  file contents still mismatched")
            print("  wanted: {}".format(contents.replace('\n', ' ')))
            print("     got: {}".format(current.replace('\n', ' ')))
        time.sleep(1)
    raise Exception("Didn't find '{}' after {}s".format(path, timeout))

def await_file_vanishes(path, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        print("  waiting for '{}' to vanish".format(path))
        if not exists(path):
            return
        time.sleep(1)
    raise Exception("'{}' still exists after {}s".format(path, timeout))


# XXX FIXME just putting these here as a cheap hack at getting some
# sort of "progress of creating the fixtures". So these dummy tests
# run first and instantiate the pre-requisites first (e.g. introducer)
# and therefore print "something" on the console as we go (a . or the
# test-name in "-v"/verbose mode)
def test_create_introducer(introducer):
    print("Created introducer")

def test_create_storage(storage_nodes):
    print("Created {} storage nodes".format(len(storage_nodes)))

def test_create_alice_bob_magicfolder(magic_folder):
    print("Alice and Bob have paired magic-folders")

    
# tests converted from check_magicfolder_smoke.py


def test_alice_writes_bob_receives(magic_folder):
    alice_dir, bob_dir = magic_folder

    with open(join(alice_dir, "first_file"), "w") as f:
        f.write("alice wrote this")

    await_file_contents(join(bob_dir, "first_file"), "alice wrote this")
    return


def test_bob_writes_alice_receives(magic_folder):
    alice_dir, bob_dir = magic_folder

    with open(join(bob_dir, "second_file"), "w") as f:
        f.write("bob wrote this")

    await_file_contents(join(alice_dir, "second_file"), "bob wrote this")
    return


def test_alice_deletes(magic_folder):
    # alice writes a file, waits for bob to get it and then deletes it.
    alice_dir, bob_dir = magic_folder

    with open(join(alice_dir, "delfile"), "w") as f:
        f.write("alice wrote this")

    await_file_contents(join(bob_dir, "delfile"), "alice wrote this")

    # bob has the file; now alices deletes it
    unlink(join(alice_dir, "delfile"))

    # bob should remove his copy, but preserve a backup
    await_file_vanishes(join(bob_dir, "delfile"))
    await_file_contents(join(bob_dir, "delfile.backup"), "alice wrote this")
    return


def test_alice_creates_bob_edits(magic_folder):
    alice_dir, bob_dir = magic_folder

    # alice writes a file
    with open(join(alice_dir, "editfile"), "w") as f:
        f.write("alice wrote this")

    await_file_contents(join(bob_dir, "editfile"), "alice wrote this")

    # now bob edits it
    with open(join(bob_dir, "editfile"), "w") as f:
        f.write("bob says foo")

    await_file_contents(join(alice_dir, "editfile"), "bob says foo")


def test_bob_creates_sub_directory(magic_folder):
    alice_dir, bob_dir = magic_folder

    # bob makes a sub-dir, with a file in it
    mkdir(join(bob_dir, "subdir"))
    with open(join(bob_dir, "subdir", "a_file"), "w") as f:
        f.write("bob wuz here")

    # alice gets it
    await_file_contents(join(alice_dir, "subdir", "a_file"), "bob wuz here")

    # now bob deletes it again
    shutil.rmtree(join(bob_dir, "subdir"))

    # alice should delete it as well
    await_file_vanishes(join(alice_dir, "subdir", "a_file"))
    # i *think* it's by design that the subdir won't disappear,
    # because a "a_file.backup" should appear...
    await_file_contents(join(alice_dir, "subdir", "a_file.backup"), "bob wuz here")
