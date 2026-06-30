from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path


class OutputWriter:
    CSV_FIELDNAMES = [
        "Candidate ID",
        "Full Name",
        "Email",
        "Phone",
        "City",
        "Country",
        "Headline",
        "Experience (Years)",
        "Skills",
        "Confidence",
    ]

    def write_json(self, payload: object, output_path: str | Path | None) -> str:
        data = json.dumps(self._serialize(payload), indent=2)
        if output_path is None:
            return data
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return str(path)

    def write_html(self, payload: object, output_path: str | Path) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._serialize(payload)
        path.write_text(self._render_html(data), encoding="utf-8")
        return str(path)

    def write_csv(self, payload: object, output_path: str | Path | None) -> str:
        data = self._serialize(payload)
        rows = self._csv_rows(data if isinstance(data, dict) else {"candidates": data})
        output = self._render_csv(rows)
        if output_path is None:
            return output
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        return str(path)

    def _serialize(self, value):
        if is_dataclass(value):
            return {key: self._serialize(item) for key, item in asdict(value).items()}
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize(item) for key, item in value.items()}
        return value

    def _render_html(self, payload: dict) -> str:
        candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
        stats = payload.get("stats", {}) if isinstance(payload, dict) else {}
        warnings = payload.get("warnings", []) if isinstance(payload, dict) else []
        explanations = payload.get("explanations", {}) if isinstance(payload, dict) else {}
        validation_report = payload.get("validation_report", {}) if isinstance(payload, dict) else {}
        candidate_blocks = "\n".join(self._render_candidate(candidate) for candidate in candidates)
        stats_rows = "\n".join(
            f"<tr><th>{self._escape(str(key))}</th><td>{self._escape(self._format_value(value))}</td></tr>"
            for key, value in stats.items()
        )
        warning_items = "".join(f"<li>{self._escape(str(item))}</li>" for item in warnings)
        explanation_items = "".join(
            f"<details><summary>{self._escape(str(key))}</summary><pre>{self._escape(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))}</pre></details>"
            for key, value in explanations.items()
        )
        validation_items = f"<pre>{self._escape(json.dumps(validation_report, indent=2, sort_keys=True, ensure_ascii=False))}</pre>"
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Candidate Report</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px}}
.shell{{max-width:1200px;margin:0 auto}}
.hero{{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:20px;padding:24px;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
.card{{background:#111827;border:1px solid #334155;border-radius:16px;padding:16px}}
.confidence{{display:inline-block;padding:4px 10px;border-radius:999px;background:#14532d;color:#bbf7d0;font-weight:700}}
.warn{{color:#fca5a5}}
.search{{width:100%;padding:12px 14px;border-radius:12px;border:1px solid #475569;background:#0b1120;color:#e2e8f0;margin:12px 0 20px}}
table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;border-bottom:1px solid #1f2937;padding:8px 10px;vertical-align:top}}
summary{{cursor:pointer;font-weight:700}}
details{{margin-top:12px}}
small{{color:#94a3b8}}
.pill{{display:inline-block;padding:2px 8px;border-radius:999px;background:#1e293b;margin-right:6px}}
</style>
<script>
function filterCandidates(){{
  const query=document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('[data-candidate]').forEach(card=>{{
    const text=card.innerText.toLowerCase();
    card.style.display=text.includes(query)?'block':'none';
  }});
}}
</script>
</head>
<body>
<div class="shell">
<div class="hero">
<h1>Multi-Source Candidate Report</h1>
<p><span class="confidence">{self._escape(self._format_value(stats.get("average_confidence", 0)))}</span> average confidence
<span class="pill">{len(candidates)} candidates</span>
<span class="pill">{len(warnings)} warnings</span></p>
<input id="search" class="search" placeholder="Search candidates, warnings, provenance..." oninput="filterCandidates()">
</div>
<div class="grid">
<section class="card">
<h2>Statistics</h2>
<table>{stats_rows}</table>
</section>
<section class="card">
<h2>Warnings</h2>
<ul class="warn">{warning_items}</ul>
</section>
</div>
<section class="card" style="margin-top:16px">
<h2>Merge Explanations</h2>
{explanation_items or '<small>No merge explanations available.</small>'}
</section>
<section class="card" style="margin-top:16px">
<h2>Validation Report</h2>
{validation_items}
</section>
<section style="margin-top:16px">
{candidate_blocks or '<div class="card"><small>No candidates found.</small></div>'}
</section>
</div>
</body>
</html>"""

    def _csv_rows(self, payload: dict) -> list[dict[str, str]]:
        candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
        rows: list[dict[str, str]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            location = candidate.get("location", {}) if isinstance(candidate.get("location", {}), dict) else {}
            emails = candidate.get("primary_email") or self._join_values(candidate.get("emails", []))
            phones = candidate.get("primary_phone") or self._join_values(candidate.get("phones", []), excel_text=True)
            skills = self._join_values(candidate.get("all_skills", candidate.get("skills", [])))
            rows.append(
                {
                    "Candidate ID": self._format_missing(candidate.get("candidate_id")),
                    "Full Name": self._format_missing(candidate.get("name") or candidate.get("full_name")),
                    "Email": self._format_missing(emails),
                    "Phone": self._format_missing(phones),
                    "City": self._format_missing(location.get("city")),
                    "Country": self._format_missing(location.get("country")),
                    "Headline": self._format_missing(candidate.get("headline")),
                    "Experience (Years)": self._format_missing(candidate.get("experience", candidate.get("years_experience"))),
                    "Skills": skills,
                    "Confidence": self._format_confidence(candidate.get("overall_confidence")),
                }
            )
        return rows

    def _render_csv(self, rows: list[dict[str, str]]) -> str:
        if not rows:
            return ""
        from io import StringIO

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self.CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()

    def _join_values(self, values, excel_text: bool = False) -> str:
        joined = ", ".join(str(value) for value in values if value not in {None, ""})
        if not joined:
            return "-"
        if excel_text:
            return f'="{joined}"'
        return joined

    def _format_missing(self, value) -> str:
        if value is None or value == "":
            return "-"
        return str(value)

    def _format_confidence(self, value) -> str:
        if value is None or value == "":
            return "-"
        try:
            return f"{round(float(value) * 100):.0f}%"
        except (TypeError, ValueError):
            return "-"

    def _render_candidate(self, candidate: dict) -> str:
        confidence = candidate.get("overall_confidence", 0)
        full_name = candidate.get("name") or candidate.get("full_name") or "Candidate"
        email = candidate.get("primary_email")
        if not email:
            email = ", ".join(candidate.get("emails", []))
        phone = candidate.get("primary_phone")
        if not phone:
            phone = ", ".join(candidate.get("phones", []))
        experience = candidate.get("experience", candidate.get("years_experience", ""))
        location = candidate.get("location", {})
        skills = ", ".join(candidate.get("all_skills", candidate.get("skills", [])))
        provenance = candidate.get("provenance", [])
        provenance_dump = self._escape(json.dumps(provenance, indent=2, sort_keys=True, ensure_ascii=False))
        return f"""
<article class="card" data-candidate>
  <h2>{self._escape(str(full_name))} <span class="confidence">{self._escape(self._format_value(confidence))}</span></h2>
  <p><strong>Email:</strong> {self._escape(str(email))}</p>
  <p><strong>Phone:</strong> {self._escape(str(phone))}</p>
  <p><strong>Experience:</strong> {self._escape(self._format_value(experience))}</p>
  <p><strong>Location:</strong> {self._escape(str(location.get('city') or ''))}, {self._escape(str(location.get('country') or ''))}</p>
  <p><strong>Skills:</strong> {self._escape(skills)}</p>
  <details>
    <summary>Provenance</summary>
    <pre>{provenance_dump}</pre>
  </details>
</article>"""

    def _format_value(self, value) -> str:
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    def _escape(self, value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
