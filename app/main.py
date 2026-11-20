
import argparse
import json
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

from app.ui.approval_popup import ApprovalPopup


class ApprovalBroker(QObject):
    request_approval = Signal(object)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._pending = {}

    def ask(self, request):
        event = threading.Event()
        result = {"allow": False}

        request_id = request.get("id")
        key = str(request_id) if request_id is not None else (
            f"notification-{id(event)}"
        )

        with self._lock:
            self._pending[key] = (event, result)

        self.request_approval.emit({
            "key": key,
            "request": request
        })

        # Fail closed after 5 minutes.
        if not event.wait(300):
            with self._lock:
                self._pending.pop(key, None)
            return False

        return result["allow"]

    def decide(self, key, allow):
        with self._lock:
            item = self._pending.pop(key, None)

        if item:
            event, result = item
            result["allow"] = allow
            event.set()


def jsonrpc_error(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message
        }
    }


class Proxy:

    def __init__(self, command, args, broker):
        self.command = [command, *args]
        self.broker = broker

        self.write_lock = threading.Lock()
        self.stdout_lock = threading.Lock()

        self.child = None

    def start(self):
        self.child = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        threading.Thread(
            target=self._relay_stderr,
            daemon=True
        ).start()

        threading.Thread(
            target=self._relay_server_stdout,
            daemon=True
        ).start()

    def _write_stdout(self, message):
        with self.stdout_lock:
            sys.stdout.write(
                json.dumps(message, separators=(",", ":")) + "\n"
            )
            sys.stdout.flush()

    def _relay_stderr(self):
        if not self.child or not self.child.stderr:
            return

        for line in self.child.stderr:
            sys.stderr.write("[MCP Server] " + line)
            sys.stderr.flush()

    def _relay_server_stdout(self):
        if not self.child or not self.child.stdout:
            return

        for line in self.child.stdout:
            with self.stdout_lock:
                sys.stdout.write(line)
                sys.stdout.flush()

    def _send_to_server(self, message):
        if not self.child or self.child.poll() is not None:
            raise RuntimeError("MCP server is not running")

        payload = json.dumps(
            message,
            separators=(",", ":")
        )

        with self.write_lock:
            self.child.stdin.write(payload + "\n")
            self.child.stdin.flush()

    def handle_line(self, line):
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write("Invalid JSON-RPC message\n")
            return

        if not isinstance(message, dict):
            return

        method = message.get("method")

        # Intercept tool execution.
        if method == "tools/call":

            allowed = self.broker.ask(message)

            if not allowed:
                if "id" in message:
                    self._write_stdout(
                        jsonrpc_error(
                            message["id"],
                            -32001,
                            "Request blocked by user via MCP Firewall"
                        )
                    )

                sys.stderr.write(
                    f"Blocked MCP request: {message.get('params', {}).get('name')}\n"
                )
                return

            sys.stderr.write("User approved MCP request\n")

        # Forward approved requests.
        try:
            self._send_to_server(message)

        except Exception as exc:
            sys.stderr.write(f"Proxy error: {exc}\n")

            if "id" in message:
                self._write_stdout(
                    jsonrpc_error(
                        message["id"],
                        -32603,
                        "MCP proxy forwarding failed"
                    )
                )

    def run(self):
        self.start()

        try:
            for line in sys.stdin:

                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self.handle_line(line)
                    continue

                # Tool calls can wait concurrently for approval.
                if (
                    isinstance(message, dict)
                    and message.get("method") == "tools/call"
                ):
                    threading.Thread(
                        target=self.handle_line,
                        args=(line,),
                        daemon=True
                    ).start()

                else:
                    self.handle_line(line)

        finally:
            if self.child and self.child.poll() is None:
                self.child.terminate()

                try:
                    self.child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.child.kill()


class FirewallApp(QObject):

    def __init__(self, argv):
        super().__init__()

        parser = argparse.ArgumentParser()

        parser.add_argument(
            "--command",
            required=True,
            help="Downstream MCP server executable"
        )

        parser.add_argument(
            "--args",
            nargs=argparse.REMAINDER,
            default=[],
            help="Arguments for downstream MCP server"
        )

        options = parser.parse_args(argv)

        self.qt = QApplication(sys.argv[:1])
        self.qt.setQuitOnLastWindowClosed(False)

        self.broker = ApprovalBroker()

        self.broker.request_approval.connect(
            self.show_popup,
            Qt.QueuedConnection
        )

        # Keep references to open dialogs.
        self.popups = {}

        # System tray.
        self.tray = None

        if QSystemTrayIcon.isSystemTrayAvailable():

            self.tray = QSystemTrayIcon(self)

            icon = self.qt.style().standardIcon(
                self.qt.style().StandardPixmap.SP_ComputerIcon
            )

            self.tray.setIcon(icon)
            self.tray.setToolTip("MCP Firewall is running")

            menu = QMenu()

            quit_action = menu.addAction("Quit Firewall")
            quit_action.triggered.connect(self.qt.quit)

            self.tray.setContextMenu(menu)
            self.tray.show()

        # Start MCP proxy in background.
        self.proxy = Proxy(
            options.command,
            options.args,
            self.broker
        )

        self.worker = threading.Thread(
            target=self.proxy.run,
            daemon=True
        )

        self.worker.start()

    def show_popup(self, payload):

        popup = ApprovalPopup(
            payload["request"],
            payload["key"],
            self.broker.decide
        )

        # Prevent garbage collection.
        self.popups[payload["key"]] = popup

        popup.finished.connect(
            lambda result, key=payload["key"]:
            self.popups.pop(key, None)
        )

        popup.show()
        popup.raise_()
        popup.activateWindow()

    def run(self):
        return self.qt.exec()


def main():
    app = FirewallApp(sys.argv[1:])
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
