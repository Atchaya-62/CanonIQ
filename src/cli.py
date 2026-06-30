from __future__ import annotations

import argparse
import json
import logging
from time import perf_counter
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from .pipeline.projector import ProjectionEngine
from .pipeline.transformer import CandidateTransformer

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "default_projection.json"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload = {"level": record.levelname, "message": record.getMessage(), "logger": record.name}
        return json.dumps(payload, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-source candidate data transformer")
    parser.add_argument("--input", required=True, help="Input file or directory")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Projection config JSON")
    parser.add_argument("--output", help="Output JSON or HTML file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose structured logging")
    parser.add_argument("--explain", action="store_true", help="Print merge reasoning")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing output")
    parser.add_argument("--stats", action="store_true", help="Print pipeline statistics")
    args = parser.parse_args()

    if args.verbose:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        logging.basicConfig(level=logging.DEBUG, handlers=[handler])
    else:
        logging.basicConfig(level=logging.INFO, handlers=[RichHandler(rich_tracebacks=True, show_path=False)])
    console = Console()
    transformer = CandidateTransformer(ProjectionEngine.from_file(args.config))
    result = transformer.run(args.input, dry_run=args.dry_run, explain=args.explain)

    if args.explain and result.explanations:
        console.print("[bold]Candidate Merge Report[/bold]")
        for key, value in result.explanations.items():
            if isinstance(value, dict) and "merge_summary" in value:
                console.print(f"\n[bold cyan]{key}[/bold cyan]")
                for line in format_explanation(value, key):
                    console.print(line)
            else:
                console.print(f"[cyan]{key}[/cyan]: {', '.join(value) if value else 'no decision details'}")

    report_payload = {
        "candidates": result.candidates,
        "warnings": result.warnings,
        "stats": result.stats,
        "explanations": result.explanations,
        "validation_report": result.validation_report,
    }
    if args.output and not args.dry_run:
        path = Path(args.output)
        output_started = perf_counter()
        if path.suffix.lower() == ".html":
            transformer.writer.write_html(report_payload, path)
        else:
            transformer.writer.write_json(result.candidates, path)
        result.stats["output_seconds"] = round(perf_counter() - output_started, 4)
        validation_path = path.with_name("validation_report.json")
        transformer.writer.write_json(result.validation_report, validation_path)
    else:
        console.print_json(data=result.candidates)

    if args.stats:
        console.print("[bold]Stats[/bold]")
        console.print_json(data=result.stats)
    if result.warnings:
        console.print("[bold yellow]Warnings[/bold yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")
    return 0


def format_explanation(explanation: dict[str, object], key: str) -> list[str]:
    lines: list[str] = []
    lines.append(safe_text(f"Candidate: {explanation.get('candidate') or key}"))
    if explanation.get("cluster_size"):
        lines.append(safe_text(f"Cluster size: {explanation.get('cluster_size')}"))
    merge_summary = explanation.get("merge_summary")
    if merge_summary:
        lines.append(safe_text(merge_summary))
    if explanation.get("merge_decision"):
        lines.append(safe_text(f"Decision: {str(explanation.get('merge_decision')).replace('_', ' ').title()}"))
    if isinstance(explanation.get("merge_score"), (int, float)):
        lines.append(safe_text(f"Merge score: {float(explanation.get('merge_score', 0.0)):.0%}"))
    if isinstance(explanation.get("merge_threshold"), (int, float)):
        lines.append(safe_text(f"Threshold: {float(explanation.get('merge_threshold', 0.0)):.0%}"))

    lines.extend(format_list_section("Sources", explanation.get("sources_merged")))
    lines.extend(format_list_section("Merge Details", explanation.get("merge_details")))
    lines.extend(format_match_section("Matching Criteria", explanation.get("matching_details") or explanation.get("matched_on")))
    lines.extend(format_field_section("Field Resolution", explanation.get("field_details") or explanation.get("field_selection")))
    lines.extend(format_json_section("Conflict Resolution", explanation.get("field_conflicts")))
    lines.extend(format_json_section("Field Resolvers", explanation.get("field_resolvers")))
    lines.extend(format_json_section("Confidence Breakdown", explanation.get("confidence_evidence")))
    lines.append(safe_text(f"Overall Confidence: {float(explanation.get('overall_confidence', 0.0)):.0%}"))

    warnings = explanation.get("warnings") or []
    if warnings:
        lines.extend(format_list_section("Warnings", warnings))
    return lines


def format_list_section(title: str, values) -> list[str]:
    items = [item for item in values or [] if item not in (None, "")]
    if not items:
        return []
    lines = [safe_text(title)]
    for item in items:
        lines.append(f"  - {safe_text(format_summary(item))}")
    lines.append("")
    return lines


def format_match_section(title: str, values) -> list[str]:
    items = [item for item in values or [] if item]
    if not items:
        return []
    lines = [safe_text(title)]
    for item in items:
        lines.append(f"  - {safe_text(format_match_item(item))}")
    lines.append("")
    return lines


def format_field_section(title: str, fields) -> list[str]:
    if not isinstance(fields, dict) or not fields:
        return []
    lines = [safe_text(title)]
    for field_name, detail in fields.items():
        lines.append(safe_text(f"{field_name.replace('_', ' ').title()}"))
        lines.extend(format_detail(detail))
    lines.append("")
    return lines


def format_json_section(title: str, value) -> list[str]:
    if not value or (isinstance(value, dict) and not value):
        return []
    dump = json.dumps(value, indent=2, ensure_ascii=True).splitlines()
    return [safe_text(title), *[safe_text(f"  {line}") for line in dump], ""]


def format_detail(detail) -> list[str]:
    if detail in (None, ""):
        return ["  n/a"]
    if isinstance(detail, list):
        return [f"  - {format_summary(item)}" for item in detail] or ["  n/a"]
    if not isinstance(detail, dict):
        return [safe_text(f"  {detail}")]
    lines: list[str] = []
    if "selected_value" in detail:
        lines.append(safe_text(f"  Value: {format_summary(detail.get('selected_value'))}"))
    elif "value" in detail:
        lines.append(safe_text(f"  Value: {format_summary(detail.get('value'))}"))
    source = detail.get("selected_source") or detail.get("source")
    if source:
        lines.append(safe_text(f"  Source: {source}"))
    confidence = detail.get("selected_confidence")
    if confidence is None:
        confidence = detail.get("confidence")
    if isinstance(confidence, (int, float)):
        lines.append(safe_text(f"  Confidence: {float(confidence):.0%}"))
    reason = detail.get("selected_reason") or detail.get("reason")
    if reason:
        lines.append(safe_text(f"  Reason: {reason}"))
    sources = detail.get("sources") or []
    if sources:
        lines.append(safe_text(f"  Sources: {', '.join(str(item) for item in sources if item)}"))
    items = detail.get("items") or []
    if items:
        lines.append("  Evidence:")
        for item in items[:5]:
            lines.append(safe_text(f"    - {format_summary(item)}"))
        if len(items) > 5:
            lines.append(safe_text(f"    - + {len(items) - 5} more"))
    values = detail.get("values") or []
    if values:
        lines.append("  Values:")
        for item in values[:5]:
            lines.append(safe_text(f"    - {format_summary(item)}"))
        if len(values) > 5:
            lines.append(safe_text(f"    - + {len(values) - 5} more"))
    if not lines:
        lines.append(safe_text(f"  {detail}"))
    return lines


def format_summary(value) -> str:
    if value in (None, ""):
        return "n/a"
    if isinstance(value, list):
        return " + ".join(format_summary(item) for item in value if item not in (None, "")) or "n/a"
    if not isinstance(value, dict):
        return safe_text(str(value))
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
        parts.append(f"confidence {float(confidence):.0%}")
    return safe_text(" | ".join(parts) if parts else json.dumps(value, ensure_ascii=True))


def format_match_item(value) -> str:
    if value in (None, ""):
        return "n/a"
    if not isinstance(value, dict):
        return safe_text(str(value))
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
        parts.append(f"confidence {float(confidence):.0%}")
    reason = value.get("selected_reason") or value.get("reason")
    if reason:
        parts.append(str(reason))
    return safe_text(" | ".join(parts) if parts else json.dumps(value, ensure_ascii=True))


def safe_text(value) -> str:
    return (
        str(value)
        .replace("←", "<-")
        .replace("→", "->")
        .replace("✓", "*")
        .encode("ascii", "replace")
        .decode("ascii")
    )
