#! /usr/bin/python

import sys
import ast
import types
from singledispatch import singledispatch

from unidiff import PatchSet


"""
We want to discover if a given PR/branch has introduced (or
edited) and functions or methods that don't have a docstring.

Method:

 - look at every file changed on the branch
 - parse it (with "ast")
 - for every function-def:
   - look at the line-numbers
   - if its inside any diff-hunk:
      - check if it has a docstring (error if not)
"""


def find_missing_docstrings_in_file(fname):
    """
    returns all functions in fname that have no docstrings
    """
    with open(fname, 'r') as f:
        x = ast.parse(f.read(), fname)
        things = []
        find_docstring(x, things)

    missing = []
    for x in things:
        docstring = ast.get_docstring(x)
        if docstring is None or not docstring.strip():
            missing.append((x.lineno, x.name))
    return missing


@singledispatch
def find_docstring(thing, found):
    pass

@find_docstring.register(ast.FunctionDef)
def _(thing, found):
    found.append(thing)

@find_docstring.register(ast.ClassDef)
def _(thing, found):
    found.append(thing)
    for b in thing.body:
        find_docstring(b, found)

@find_docstring.register(ast.Module)
def _(thing, found):
    for x in thing.body:
        find_docstring(x, found)


ps = PatchSet(sys.stdin)
print(dir(ps))
for x in ps.modified_files:
#    print(dir(x))
    print(x.path)
    for y in x:
        print("  {}".format(dir(y)))
        for line in y.target_lines():
            print(line.target_line_no, line.source_line_no)
missing = find_missing_docstrings_in_file("src/allmydata/node.py")
#for lineno, name in missing:
#    print("{}: {}".format(lineno, name))
