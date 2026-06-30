from __future__ import annotations

import io
import json
from pathlib import Path

from app import app


def test_index_page_loads():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Eightfold Candidate Transformer" in response.data


def test_transform_endpoint_returns_report():
    client = app.test_client()
    with Path("sample_inputs/candidate.csv").open("rb") as csv_file, Path("sample_inputs/linkedin.json").open("rb") as json_file:
        response = client.post(
            "/api/transform",
            data={
                "upload_kind": "folder",
                "folder_files": [
                    (csv_file, "candidate.csv"),
                    (json_file, "linkedin.json"),
                ],
            },
            content_type="multipart/form-data",
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["report"]["candidates"]
    assert payload["report"]["explanations"]
    report_text = json.dumps(payload["report"]["explanations"], ensure_ascii=False)
    assert "_web_uploads" not in report_text
    assert "E:\\" not in report_text

    download_json = client.post("/api/download/json", data=json.dumps(payload["report"]), content_type="application/json")
    assert download_json.status_code == 200
    assert download_json.mimetype == "application/json"

    download_csv = client.post("/api/download/csv", data=json.dumps(payload["report"]), content_type="application/json")
    assert download_csv.status_code == 200
    assert download_csv.mimetype == "text/csv"
    assert b"Candidate ID,Full Name,Email,Phone,City,Country,Headline,Experience (Years),Skills,Confidence" in download_csv.data
