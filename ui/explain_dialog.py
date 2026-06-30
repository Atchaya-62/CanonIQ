from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout


class ExplainDialog(QDialog):
    def __init__(self, report_payload: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Merge Explanation")
        self.resize(900, 560)
        self._report_payload = report_payload
        self._candidates = report_payload.get("candidates", []) if isinstance(report_payload, dict) else []
        self._explanations = report_payload.get("explanations", {}) if isinstance(report_payload, dict) else {}

        self._candidate_list = QListWidget()
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._details.setMinimumWidth(500)
        self._header = QLabel("Select a candidate to inspect merge reasoning.")
        self._header.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._header)
        body = QHBoxLayout()
        body.addWidget(self._candidate_list, 1)
        body.addWidget(self._details, 2)
        layout.addLayout(body)

        self._candidate_list.currentRowChanged.connect(self._render_current)
        self._populate()

    def _populate(self) -> None:
        self._candidate_list.clear()
        if not self._candidates:
            self._candidate_list.addItem(QListWidgetItem("No candidates"))
            self._details.setPlainText("No merge explanation was produced for this run.")
            return
        for index, candidate in enumerate(self._candidates):
            label = candidate.get("full_name") or candidate.get("candidate_id") or f"Candidate {index + 1}"
            item = QListWidgetItem(f"{label}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._candidate_list.addItem(item)
        self._candidate_list.setCurrentRow(0)

    def _render_current(self, row: int) -> None:
        if row < 0 or row >= len(self._candidates):
            return
        candidate = self._candidates[row]
        key = candidate.get("candidate_id") or f"candidate_{row}"
        explanation = self._explanations.get(key, {})
        if not isinstance(explanation, dict):
            explanation = {"details": explanation}
        self._header.setText(candidate.get("full_name") or key)
        self._details.setPlainText(self._format_explanation(candidate, explanation))

    def _format_explanation(self, candidate: dict, explanation: dict) -> str:
        lines: list[str] = []
        lines.append(f"Candidate: {candidate.get('full_name') or candidate.get('candidate_id') or 'Unknown'}")
        lines.append("")
        lines.append("Identity Resolution")
        lines.append("-------------------")
        for item in explanation.get("identity_resolution", []) or []:
            lines.append(f"✓ {item}")
        lines.append("")
        lines.append("Merge")
        lines.append("-----")
        lines.append(f"Score: {self._fmt(explanation.get('merge_score'))}")
        lines.append(f"Threshold: {self._fmt(explanation.get('merge_threshold'))}")
        lines.append(f"Decision: {explanation.get('merge_decision', 'merged')}")
        lines.append("")
        lines.append("Field Selection")
        lines.append("---------------")
        for field_name, value in (explanation.get("field_selection") or {}).items():
            lines.append(f"{field_name.title()}: {self._render_value(value)}")
        conflicts = explanation.get("field_conflicts") or {}
        if conflicts:
            lines.append("")
            lines.append("Conflict Resolution")
            lines.append("-------------------")
            lines.append(json.dumps(conflicts, indent=2, ensure_ascii=False, sort_keys=True))
        lines.append("")
        lines.append(f"Confidence: {self._fmt(candidate.get('overall_confidence'))}")
        return "\n".join(lines)

    def _render_value(self, value) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if item) or "n/a"
        if value is None:
            return "n/a"
        return str(value)

    def _fmt(self, value) -> str:
        if isinstance(value, (int, float)):
            return f"{float(value):.2f}"
        return "n/a"

