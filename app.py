from __future__ import annotations

import json
import io
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from src.pipeline.projector import ProjectionEngine
from src.pipeline.transformer import CandidateTransformer
from src.pipeline.writer import OutputWriter


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "src" / "config" / "default_projection.json"

app = Flask(__name__)
transformer = CandidateTransformer(ProjectionEngine.from_file(DEFAULT_CONFIG))
writer = OutputWriter()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/transform")
def api_transform():
    upload_kind = request.form.get("upload_kind", "folder")
    temp_root = BASE_DIR / "_web_uploads"
    temp_root.mkdir(exist_ok=True)
    temp_dir = temp_root / f"upload_{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        input_dir = temp_dir
        if upload_kind == "zip":
            upload = request.files.get("zip_file")
            if upload is None or not upload.filename:
                return jsonify({"success": False, "error": "Upload a ZIP file."}), 400
            zip_path = input_dir / "upload.zip"
            upload.save(zip_path)
            with zipfile.ZipFile(zip_path) as archive:
                _safe_extract_zip(archive, input_dir)
        else:
            files = request.files.getlist("folder_files")
            if not files:
                return jsonify({"success": False, "error": "Choose a folder or ZIP file."}), 400
            _save_uploaded_files(files, input_dir)

        result = transformer.run(str(input_dir), explain=True)
        report = {
            "candidates": result.candidates,
            "warnings": result.warnings,
            "stats": result.stats,
            "explanations": result.explanations,
            "validation_report": result.validation_report,
        }
        return jsonify({"success": True, "report": report})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/download/json")
def api_download_json():
    payload = request.get_json(silent=True) or {}
    data = json.dumps(payload, indent=2, ensure_ascii=False)
    return send_file(
        io.BytesIO(data.encode("utf-8")),
        as_attachment=True,
        download_name="candidate_report.json",
        mimetype="application/json",
    )


@app.post("/api/download/csv")
def api_download_csv():
    payload = request.get_json(silent=True) or {}
    csv_data = writer.write_csv(payload, None)
    return send_file(
        io.BytesIO(csv_data.encode("utf-8")),
        as_attachment=True,
        download_name="candidate_report.csv",
        mimetype="text/csv",
    )


def _save_uploaded_files(files, target_dir: Path) -> None:
    for upload in files:
        relative_name = upload.filename or ""
        if not relative_name:
            continue
        safe_path = _safe_relative_path(relative_name)
        destination = target_dir / safe_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        upload.save(destination)


def _safe_relative_path(filename: str) -> Path:
    parts = [secure_filename(part) for part in Path(filename).parts if part not in {"", ".", ".."}]
    parts = [part for part in parts if part]
    if not parts:
        return Path("upload.bin")
    return Path(*parts)


def _safe_extract_zip(archive: zipfile.ZipFile, target_dir: Path) -> None:
    for member in archive.infolist():
        if member.is_dir():
            continue
        safe_name = _safe_relative_path(member.filename)
        destination = target_dir / safe_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)


def main() -> int:
    app.run(host="127.0.0.1", port=5000, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
