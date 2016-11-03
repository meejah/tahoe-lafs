from zope.interfaces import implementer
from ..interfaces import IConnectionStatus

@implementer(IConnectionStatus)
class ConnectionStatus:
    def __init__(self, connected,
                 last_connection_description, last_connection_time,
                 last_received):
        self._connected = connected
        self._last_connection = last_connection_description
        self._last_connection_time = last_connection_time
        self._last_received = last_received

    def is_connected(self):
        return self._connected
    def when_established(self):
        return self._last_connection_time
    def describe_last_connection(self):
        return self._last_connection
    def last_received(self):
        return self._last_received

def _describe_statuses(hints, handlers, statuses):
    descriptions = []
    for hint in sorted(hints):
        handler = handlers.get(hint)
        handler_dsc = " via %s" % handler if handler else ""
        status = statuses[hint]
        descriptions.append("%s%s: %s" % (hint, handler_dsc, status))
    return ", ".join(descriptions)

def from_foolscap_reconnector(rc, last_received):
    state = rc.getState()
    # the Reconnector shouldn't even be exposed until it is started, so we
    # should never see "unstarted"
    assert state in ("connected", "connecting", "waiting"), state
    ci = rc.getConnectionInfo()
    when_established = ci.connectionEstablishedAt()

    if state == "connected":
        connected = True
        # build a description that shows the winning hint, and the outcomes
        # of the losing ones
        statuses = ci.connectorStatuses()
        handlers = ci.connectionHandlers()
        others = set(statuses.keys())

        winner = ci.winningHint()
        if winner:
            others.remove(winner)
            winning_handler = ci.connectionHandlers()[winner]
            winning_dsc = "to %s via %s" % (winner, winning_handler)
        else:
            winning_dsc = "via listener %s" % ci.listenerStatus()[0]
        if others:
            other_dsc = " (other hints: %s)" % \
                        _describe_statuses(others, handlers, statuses)
        else:
            other_dsc = ""
        dsc = "Connection successful " + winning_dsc + other_dsc
        last_connected = ci.connectionEstablishedAt()
    elif state == "connecting":
        connected = False
        # ci describes the current in-progress attempt
        statuses = ci.connectorStatuses()
        current = _describe_statuses(sorted(statuses.keys()),
                                     ci.connectionHandlers(), statuses)
        dsc = "Trying to connect: %s" % current
        last_connected = None
    elif state == "waiting":
        connected = False
        now = time.time()
        elapsed = now - rc.lastAttempt()
        delay = rc.nextAttempt() - now
        # ci describes the previous (failed) attempt
        statuses = ci.connectorStatuses()
        last = _describe_statuses(sorted(statuses.keys()),
                                  ci.connectionHandlers(), statuses)
        dsc = "Reconnecting in %d seconds (last connection %ds ago: %s)" % (
            delay, elapsed, last)
        last_connected = None

    cs = ConnectionStatus(connected, dsc, last_connected, last_received)
    return cs
