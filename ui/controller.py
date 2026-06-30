from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.pipeline.projector import ProjectionEngine
from src.pipeline.transformer import CandidateTransformer, TransformResult

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "src" / "config" / "default_projection.json"


@dataclass(slots=True)
class TransformSnapshot:
    result: TransformResult
    report_payload: dict[str, Any]
    json_text: str


class PipelineController:
    def __init__(self, config_path: str | Path = DEFAULT_CONFIG) -> None:
        self.transformer = CandidateTransformer(ProjectionEngine.from_file(config_path))

    def transform(self, input_path: str, explain: bool = True) -> TransformSnapshot:
        result = self.transformer.run(input_path, explain=explain)
        report_payload = {
            "candidates": result.candidates,
            "warnings": result.warnings,
            "stats": result.stats,
            "explanations": result.explanations,
            "validation_report": result.validation_report,
        }
        return TransformSnapshot(
            result=result,
            report_payload=report_payload,
            json_text=json.dumps(report_payload, indent=2, ensure_ascii=False),
        )

    def save_json(self, snapshot: TransformSnapshot, output_path: str | Path | None) -> str:
        return self.transformer.writer.write_json(snapshot.report_payload, output_path)

    def save_csv(self, snapshot: TransformSnapshot, output_path: str | Path | None) -> str:
        return self.transformer.writer.write_csv(snapshot.report_payload, output_path)

