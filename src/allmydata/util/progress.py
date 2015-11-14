"""
Utilities relating to computing progress information.

Ties in with the "consumer" module also
"""

from zope.interface import Interface, Attribute, implementer

class IProgress(Interface):
    progress = Attribute(
        "Current amount of progress; interpretation up to implementation"
    )

    def set_value(value):
        """
        Set the current amount of progress; how this is interpreted is up
        to the implementation.
        """


@implementer(IProgress)
class AbsoluteProgress(object):
    """
    Merely remembers and gives back the same value as the last call to set_value
    """

    def __init__(self):
        self.value = 0.0

    def set_value(self, value):
        self.value = value

    @property
    def progress(self):
        return self.value


@implementer(IProgress)
class PercentProgress(AbsoluteProgress):
    """
    Represents progress as a percentage, from 0.0 to 100.0
    """

    def __init__(self, total_size):
        super(PercentProgress, self).__init__()
        self.total_size = float(total_size)

    @property
    def progress(self):
        if self.total_size is None:
            return 0
        return (self.value / self.total_size) * 100.0
