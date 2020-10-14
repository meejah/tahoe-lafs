
from twisted.internet.task import (
    react,
)
from twisted.internet.defer import (
    inlineCallbacks,
)

from twisted.python.filepath import (
    FilePath,
)

import click

from tu.grid import (
    create as tu_grid_create,
)


@click.group()
def tu():
    """
    Tahoe Utilities
    """


@tu.group()
def grid():
    """
    Manage local Grids
    """


@grid.command()
@click.argument(
    'directory',
    type=click.Path(exists=False),
)
@click.option(
    "--storage",
    help="Number of storage nodes",
    default=5,
)
@click.option(
    "--client",
    help="Add a client with this name",
    multiple=True,
    default=["alice", "bob"],
)
def create(directory, storage, client):
    """
    Create a new local grid
    """
    # tu create grid <dir>

    @inlineCallbacks
    def main(reactor):
        grid = yield tu_grid_create(
            FilePath(directory),
            ["storage{}".format(n) for n in range(storage)],
            client,
        )
        print(grid)
    react(main)
