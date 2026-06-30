from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QSyntaxHighlighter


class JsonHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self._string_format = self._format("#93c5fd")
        self._number_format = self._format("#fbbf24")
        self._bool_format = self._format("#86efac", bold=True)
        self._null_format = self._format("#fda4af", italic=True)
        self._key_format = self._format("#67e8f9", bold=True)

    def _format(self, color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(color))
        if bold:
            text_format.setFontWeight(QFont.Bold)
        text_format.setFontItalic(italic)
        return text_format

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        self._apply(r'"[^"\\]*(\\.[^"\\]*)*"', text, self._string_format)
        self._apply(r"\b-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?\b", text, self._number_format)
        self._apply(r"\btrue\b|\bfalse\b", text, self._bool_format)
        self._apply(r"\bnull\b", text, self._null_format)
        self._apply(r'(?<=")\s*:\s*', text, self._key_format)

    def _apply(self, pattern: str, text: str, text_format: QTextCharFormat) -> None:
        expression = QRegularExpression(pattern)
        iterator = expression.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), text_format)

