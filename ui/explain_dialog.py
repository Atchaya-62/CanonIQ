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
        lines.extend(self._section("Merge Summary", [
            f"Cluster size: {explanation.get('cluster_size', 'n/a')}",
            explanation.get("merge_summary"),
            f"Decision: {self._label(explanation.get('merge_decision'))}" if explanation.get("merge_decision") else None,
            f"Merge score: {self._percent(explanation.get('merge_score'))}",
            f"Threshold: {self._percent(explanation.get('merge_threshold'))}",
        ]))
        lines.extend(self._list_section("Sources", explanation.get("sources_merged")))
        lines.extend(self._list_section("Merge Details", explanation.get("merge_details")))
        lines.extend(self._match_section("Matching Criteria", explanation.get("matching_details") or explanation.get("matched_on")))
        lines.extend(self._field_section("Field Resolution", explanation.get("field_details") or explanation.get("field_selection")))
        lines.extend(self._json_section("Conflict Resolution", explanation.get("field_conflicts")))
        lines.extend(self._json_section("Field Resolvers", explanation.get("field_resolvers")))
        lines.extend(self._json_section("Confidence Breakdown", explanation.get("confidence_evidence")))
        lines.append("")
        lines.append(f"Overall Confidence: {self._percent(candidate.get('overall_confidence'))}")
        warnings = explanation.get("warnings") or []
        if warnings:
            lines.append("")
            lines.extend(self._list_section("Warnings", warnings))
        return "\n".join(line for line in lines if line is not None)

    def _section(self, title: str, lines: list[str | None]) -> list[str]:
        content = [line for line in lines if line not in (None, "")]
        if not content:
            return []
        rendered = [title]
        rendered.extend(content)
        rendered.append("")
        return rendered

    def _list_section(self, title: str, values) -> list[str]:
        items = [item for item in values or [] if item not in (None, "")]
        if not items:
            return []
        lines = [title]
        for item in items:
            lines.append(f"- {self._summary(item)}")
        lines.append("")
        return lines

    def _match_section(self, title: str, values) -> list[str]:
        items = [item for item in values or [] if item]
        if not items:
            return []
        lines = [title]
        for item in items:
            lines.append(f"- {self._match_summary(item)}")
        lines.append("")
        return lines

    def _field_section(self, title: str, fields) -> list[str]:
        if not isinstance(fields, dict) or not fields:
            return []
        lines = [title]
        for field_name, detail in fields.items():
            lines.append(field_name.replace("_", " ").title())
            lines.extend(self._detail(detail))
        lines.append("")
        return lines

    def _json_section(self, title: str, value) -> list[str]:
        if not value or (isinstance(value, dict) and not value):
            return []
        dump = json.dumps(value, indent=2, ensure_ascii=False).splitlines()
        return [title, *[f"  {line}" for line in dump], ""]

    def _detail(self, detail) -> list[str]:
        if detail in (None, ""):
            return ["  n/a"]
        if isinstance(detail, list):
            return [f"  - {self._summary(item)}" for item in detail] or ["  n/a"]
        if not isinstance(detail, dict):
            return [f"  {detail}"]
        lines: list[str] = []
        if "selected_value" in detail:
            lines.append(f"  Value: {self._summary(detail.get('selected_value'))}")
        elif "value" in detail:
            lines.append(f"  Value: {self._summary(detail.get('value'))}")
        source = detail.get("selected_source") or detail.get("source")
        if source:
            lines.append(f"  Source: {source}")
        confidence = detail.get("selected_confidence")
        if confidence is None:
            confidence = detail.get("confidence")
        if isinstance(confidence, (int, float)):
            lines.append(f"  Confidence: {self._percent(confidence)}")
        reason = detail.get("selected_reason") or detail.get("reason")
        if reason:
            lines.append(f"  Reason: {reason}")
        sources = detail.get("sources") or []
        if sources:
            lines.append(f"  Sources: {', '.join(str(item) for item in sources if item)}")
        items = detail.get("items") or []
        if items:
            lines.append("  Evidence:")
            for item in items[:5]:
                lines.append(f"    - {self._summary(item)}")
            if len(items) > 5:
                lines.append(f"    - + {len(items) - 5} more")
        values = detail.get("values") or []
        if values:
            lines.append("  Values:")
            for item in values[:5]:
                lines.append(f"    - {self._summary(item)}")
            if len(values) > 5:
                lines.append(f"    - + {len(values) - 5} more")
        if not lines:
            lines.append(f"  {detail}")
        return lines

    def _summary(self, value) -> str:
        if value in (None, ""):
            return "n/a"
        if isinstance(value, list):
            return " + ".join(self._summary(item) for item in value if item not in (None, "")) or "n/a"
        if not isinstance(value, dict):
            return str(value)
        parts = []
        if value.get("value") not in (None, ""):
            parts.append(str(value.get("value")))
        else:
            for key in ("company", "title", "institution", "degree", "field_of_study", "location"):
                if value.get(key):
                    parts.append(str(value.get(key)))
        source = value.get("source") or value.get("selected_source")
        if source:
            parts.append(f"from {source}")
        confidence = value.get("confidence")
        if confidence is None:
            confidence = value.get("selected_confidence")
        if isinstance(confidence, (int, float)):
            parts.append(f"confidence {self._percent(confidence)}")
        return " | ".join(parts) if parts else json.dumps(value, ensure_ascii=False)

    def _match_summary(self, value) -> str:
        if value in (None, ""):
            return "n/a"
        if not isinstance(value, dict):
            return str(value)
        parts = []
        if value.get("field"):
            parts.append(str(value.get("field")).replace("_", " ").title())
        if value.get("selected_value") not in (None, "") or value.get("value") not in (None, ""):
            parts.append(str(value.get("selected_value") or value.get("value")))
        source = value.get("selected_source") or value.get("source")
        if source:
            parts.append(f"from {source}")
        confidence = value.get("selected_confidence")
        if confidence is None:
            confidence = value.get("confidence")
        if isinstance(confidence, (int, float)):
            parts.append(f"confidence {self._percent(confidence)}")
        reason = value.get("selected_reason") or value.get("reason")
        if reason:
            parts.append(str(reason))
        return " | ".join(parts) if parts else json.dumps(value, ensure_ascii=False)

    def _percent(self, value) -> str:
        if isinstance(value, (int, float)):
            return f"{float(value):.0%}"
        return "n/a"
