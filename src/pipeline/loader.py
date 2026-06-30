from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

@dataclass(slots=True)
class SourceDocument:
    path: str
    source_type: str
    text: str | None
    binary: bytes | None
    checksum: str
    metadata: dict[str, str]


class InputLoader:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def load(self, input_path: str | Path) -> list[SourceDocument]:
        path = Path(input_path)
        files = sorted([item for item in path.rglob("*") if item.is_file()]) if path.is_dir() else [path]
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            return list(filter(None, executor.map(self._load_one, files)))

    def _load_one(self, path: Path) -> SourceDocument | None:
        try:
            data = path.read_bytes()
            checksum = sha256(data).hexdigest()
            text = self._decode_text(path, data)
            return SourceDocument(str(path), self.detect_source_type(path, text, data), text, data, checksum, {"extension": path.suffix.lower()})
        except OSError:
            return None

    def _decode_text(self, path: Path, data: bytes) -> str | None:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return None
        for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp1252", "latin1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="ignore")

    def detect_source_type(self, path: Path, text: str | None, data: bytes) -> str:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return "csv"
        if suffix in {".txt", ".md"}:
            return self._detect_text_type(text or "", path)
        if suffix == ".pdf":
            return "resume_pdf"
        if suffix == ".json":
            return self._detect_json_type(text or "")
        return self._detect_text_type(text or "", path)

    def _detect_json_type(self, text: str) -> str:
        lowered = text.lower()
        if any(marker in lowered for marker in ("linkedin", "headline", "positions")):
            return "linkedin_json"
        if any(marker in lowered for marker in ("github", "login", "public_repos")):
            return "github_json"
        if any(marker in lowered for marker in ("applications", "candidate", "ats")):
            return "ats_json"
        return "json"

    def _detect_text_type(self, text: str, path: Path) -> str:
        lowered = text.lower()
        stem = path.stem.lower()
        if "recruiter" in lowered or "notes" in lowered or "recruiter" in stem or "notes" in stem:
            return "notes_txt"
        if "linkedin" in lowered and "headline" in lowered:
            return "linkedin_txt"
        if "github" in lowered or "public repos" in lowered or "github" in stem:
            return "github_txt"
        if "experience |" in lowered or "education |" in lowered or "skills:" in lowered or "curriculum vitae" in lowered or "resume" in stem:
            return "resume_txt"
        if "resume" in lowered or "curriculum vitae" in lowered:
            return "resume_txt"
        return "unknown"
