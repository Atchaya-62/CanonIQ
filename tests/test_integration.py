from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.pipeline.projector import ProjectionEngine
from src.pipeline.transformer import CandidateTransformer


def test_end_to_end_directory_transform():
    transformer = CandidateTransformer(ProjectionEngine.from_file("src/config/default_projection.json"))
    result = transformer.run("sample_inputs", explain=True)
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate["name"] == "Alice Doe"
    assert candidate["primary_email"] == "alice.doe@example.com"
    assert "Machine Learning" in candidate["all_skills"]
    assert candidate["provenance"]
    assert result.stats["records_processed"] >= 5


def test_cli_outputs_json():
    output = Path("cli_test_result.json")
    if output.exists():
        output.unlink()
    try:
        completed = subprocess.run(
            [sys.executable, "cli.py", "--input", "sample_inputs", "--output", str(output), "--stats"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data and data[0]["name"] == "Alice Doe"
        assert output.exists()
    finally:
        if output.exists():
            output.unlink()


def test_cli_dry_run_prints():
    completed = subprocess.run(
        [sys.executable, "cli.py", "--input", "sample_inputs", "--dry-run", "--explain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Alice Doe" in completed.stdout
