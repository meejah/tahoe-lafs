"""
Utilities relating to computing progress information.

Ties in with the "consumer" module also
"""

from allmydata.interfaces import IProgress
from zope.interface import implementer

@implementer(IProgress)
class AbsoluteProgress(object):
    """
    Merely remembers and gives back the same value as the last call to set_value
    """

    def __init__(self):
        self._value = 0.0

    def set_progress(self, value):
        self._value = value

    @property
    def progress(self):
        return self._value


@implementer(IProgress)
class PercentProgress(AbsoluteProgress):
    """
    Represents progress as a percentage, from 0.0 to 100.0
    """

    def __init__(self, total_size):
        super(PercentProgress, self).__init__()
        self._total_size = float(total_size)

    @property
    def progress(self):
        if self._total_size is None:
            return 0
        return (self._value / self._total_size) * 100.0
