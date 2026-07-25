"""Small local activation channel for AirPoint's single-instance launcher.

``QLockFile`` remains the authority for deciding which process owns the
camera.  This module only gives a later process a way to ask that owner to
bring its window back, including when it is hidden in the notification area.
Qt implements ``QLocalServer`` as a named pipe on Windows.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


ACTIVATION_SERVER_NAME = "AirPoint-GestureControl-Activation-v1"


class ActivationServer(QObject):
    """Emit ``activation_requested`` whenever another AirPoint connects."""

    activation_requested = Signal()

    def __init__(
        self,
        name: str = ACTIVATION_SERVER_NAME,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._owns_endpoint = False
        self._server = QLocalServer(self)
        # On Windows this restricts access to the current user.  It is also a
        # sensible least-privilege default on platforms backed by Unix sockets.
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept_connections)

    @property
    def is_listening(self) -> bool:
        return self._server.isListening()

    def listen(self) -> bool:
        """Start listening, cleaning up an endpoint left by a crashed owner."""
        if self._server.isListening():
            return True
        QLocalServer.removeServer(self._name)
        self._owns_endpoint = bool(self._server.listen(self._name))
        return self._owns_endpoint

    def close(self) -> None:
        if self._server.isListening():
            self._server.close()
        if self._owns_endpoint:
            QLocalServer.removeServer(self._name)
            self._owns_endpoint = False

    def _accept_connections(self) -> None:
        # A successful connection is the whole protocol.  No payload parsing
        # is needed, so activation cannot be lost if the client exits quickly.
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self.activation_requested.emit()
            socket.disconnectFromServer()
            socket.deleteLater()


def request_activation(
    name: str = ACTIVATION_SERVER_NAME,
    timeout_ms: int = 750,
) -> bool:
    """Ask the current instance to show itself.

    Returns ``False`` when no activation server can be reached, allowing the
    launcher to retain its existing informational-dialog fallback.
    """
    socket = QLocalSocket()
    socket.connectToServer(name)
    connected = socket.waitForConnected(max(0, int(timeout_ms)))
    if connected:
        socket.disconnectFromServer()
    else:
        socket.abort()
    return bool(connected)
