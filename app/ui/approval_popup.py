import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit
)


class ApprovalPopup(QDialog):
    def __init__(self, request, key, decide_callback):
        super().__init__()
        self.key = key
        self.decide_callback = decide_callback
        params = request.get("params") or {}
        tool_name = params.get("name", "Unknown tool")
        arguments = params.get("arguments", {})

        self.setWindowTitle("MCP Firewall — Approval required")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.Window, True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        heading = QLabel("MCP tool execution requested")
        heading.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(heading)

        layout.addWidget(QLabel(f"<b>Tool:</b> {tool_name}"))
        layout.addWidget(QLabel(f"<b>Request ID:</b> {request.get('id', 'notification')}"))
        layout.addWidget(QLabel("<b>Arguments:</b>"))

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(json.dumps(arguments, indent=2, ensure_ascii=False))
        details.setMaximumHeight(180)
        layout.addWidget(details)

        warning = QLabel("The request will remain pending until you choose an action.")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        buttons = QHBoxLayout()
        block = QPushButton("Block")
        allow = QPushButton("Allow")
        block.setStyleSheet("padding: 9px;")
        allow.setStyleSheet("padding: 9px; background: #16834a; color: white;")
        block.clicked.connect(self.block)
        allow.clicked.connect(self.allow)
        buttons.addWidget(block)
        buttons.addWidget(allow)
        layout.addLayout(buttons)

    def allow(self):
        self.decide_callback(self.key, True)
        self.close()

    def block(self):
        self.decide_callback(self.key, False)
        self.close()

    def closeEvent(self, event):
        # Closing the dialog is equivalent to Block (fail closed).
        self.decide_callback(self.key, False)
        event.accept()
