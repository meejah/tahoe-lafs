import time
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

# XXX FIXME just putting these here as a cheap hack at getting some
# sort of "progress of creating the fixtures". So these dummy tests
# instantiate ensure they run first and therefore print "something" on
# the console (a . or the test-name in "-v"/verbose mode)
def test_create_introducer(introducer):
    print("Created introducer")

def test_create_storage(storage_nodes):
    print("Created {} storage nodes".format(len(storage_nodes)))

def test_pair_alice_bob_magicfolder(magic_folder):
    print("Alice and Bob have paired magic-folders")

# real tests, converted from check_magicfolder_smoke.py

def test_alice_writes_bob_gets(magic_folder):
    alice_dir, bob_dir = magic_folder

    with open(join(alice_dir, "first_file"), "w") as f:
        f.write("alice wrote this")
    print("wrote alice")

    await_file_contents(join(bob_dir, "first_file"), "alice wrote this")
