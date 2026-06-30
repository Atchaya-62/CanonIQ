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
                console.print(f"Candidate: {value.get('candidate') or key}")
                console.print(value.get("merge_summary", ""))
                console.print("Sources Merged:")
                for source in value.get("sources_merged", []) or []:
                    console.print(f"  - {source}")
                console.print("Matching Criteria:")
                for line in value.get("matched_on", []) or []:
                    console.print(f"  - {line}")
                console.print("Field Selection:")
                for field_name, source in (value.get("field_selection") or {}).items():
                    console.print(f"  - {field_name}: {source or 'n/a'}")
                warnings = value.get("warnings") or []
                if warnings:
                    console.print("Warnings:")
                    for warning in warnings:
                        console.print(f"  - {warning}")
                console.print(f"Overall Confidence: {float(value.get('overall_confidence', 0.0)):.0%}")
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
