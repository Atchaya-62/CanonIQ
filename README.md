# CanonIQ Candidate Transformer

This project turns messy candidate data from multiple sources into one clean, merged candidate profile.

It handles files like:
- CSV exports
- ATS JSON
- LinkedIn JSON
- GitHub JSON
- Resume text
- Recruiter notes

The pipeline is deterministic, explainable, and tested. It normalizes values, matches duplicate people, merges records, validates the final profile, and exports a configurable output.

## What The Assignment Asked For

The assignment in this folder asks for:
- multiple candidate data sources
- source detection and parsing
- normalization of values
- matching duplicate records
- merging into one canonical profile
- confidence scoring
- provenance and explanation of merge decisions
- validation warnings
- configurable output projection
- a CLI or UI to run the transform

This repository implements all of those steps.

## How The Pipeline Works

The end-to-end flow is:

1. Load input files from a file or folder.
2. Detect the source type for each file.
3. Parse each file into candidate fragments.
4. Normalize names, emails, phones, locations, dates, skills, and links.
5. Match fragments that belong to the same person.
6. Merge the matched fragments into one profile.
7. Score confidence and preserve provenance.
8. Validate the merged profile and collect warnings.
9. Project the result into the desired output shape.
10. Write JSON, CSV, or HTML.

## Input Files

The project accepts a folder of mixed files or a single file through the CLI and web app.

Supported examples in `sample_inputs/`:
- `candidate.csv`
- `ats.json`
- `linkedin.json`
- `github.json`
- `resume.txt`
- `notes.txt`

The parsers are designed to extract the same kinds of fields from different formats so the rest of the pipeline can stay source-agnostic.

## What Gets Normalized

Normalization makes the data consistent before matching and merging.

Examples:
- names are cleaned and title-cased
- emails are lowercased and validated
- phone numbers are converted to a canonical format
- locations are standardized to city/country style
- dates are normalized to `YYYY-MM`
- skills are canonicalized through an alias map
- URLs are cleaned and normalized

This matters because two sources may say the same thing in different formats, and the pipeline needs to recognize that they are equivalent.

## Matching And Merging

The matcher compares records using weighted evidence:
- email
- phone
- GitHub
- LinkedIn
- name similarity
- experience overlap
- education overlap
- skill overlap

If the score passes the threshold, the fragments are treated as the same candidate.

Then the merger:
- selects the best value for each field
- keeps alternative values as aliases where useful
- preserves source provenance
- records merge conflicts
- attaches recruiter notes when they can be linked safely

## Confidence And Provenance

Confidence is tracked at the field and record level.

The final profile includes:
- `overall_confidence`
- `merge_score`
- `merge_threshold`
- `merge_decision`
- `field_conflicts`
- `field_provenance`

That means the output is not just a flat record. It also shows why a value was chosen and where it came from.

## Output Configuration

The default projection is defined in `src/config/default_projection.json`.

Supported projection behaviors:
- `rename`
- `remove`
- `normalize`
- `required`
- `default`
- `on_missing`
- `on_error`
- dot-notation path traversal

Example:

```json
{
  "format": "custom",
  "fields": {
    "candidate_id": { "rename": "id", "required": true },
    "name.value": { "rename": "full_name", "required": true },
    "headline": { "default": "Unknown", "on_missing": "default" },
    "skills.0.value": { "rename": "primary_skill", "on_error": "error" }
  }
}
```

## Final Output

The canonical output includes fields such as:
- candidate id
- full name
- aliases
- emails
- phones
- location
- headline
- years of experience
- skills
- notes
- overall confidence
- merge score and merge decision
- field conflicts
- field provenance

Example shape:

```json
{
  "candidate_id": "cand_123",
  "full_name": "John Smith",
  "emails": ["john@gmail.com"],
  "phones": ["+919876543210"],
  "location": { "city": "Bengaluru", "country": "IN" },
  "headline": "Machine Learning Engineer",
  "years_experience": 4,
  "skills": ["Python", "Machine Learning"],
  "overall_confidence": 0.96
}
```

## How To Run

### CLI

Process a folder:

```bash
python cli.py --input sample_inputs
```

Write JSON output:

```bash
python cli.py --input sample_inputs --output output.json
```

Write HTML output:

```bash
python cli.py --input sample_inputs --output output.html
```

Print merge explanations:

```bash
python cli.py --input sample_inputs --explain
```

Print pipeline statistics:

```bash
python cli.py --input sample_inputs --stats
```

Run without writing files:

```bash
python cli.py --input sample_inputs --dry-run
```

Use a custom projection config:

```bash
python cli.py --input sample_inputs --config src/config/default_projection.json
```

### Web App

Run the Flask UI:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

The web app lets you:
- upload a folder or ZIP
- run the same pipeline
- inspect the merged report
- download JSON or CSV
- view explainability details

## Repository Structure

- `src/models`: canonical candidate data structures
- `src/parsers`: source-specific input readers
- `src/pipeline`: load, normalize, match, merge, score, validate, project, write
- `src/utils`: normalization and helper functions
- `src/config`: configuration files used by the pipeline
- `sample_inputs`: example files for testing the transform
- `tests`: unit and integration coverage
- `static` and `templates`: Flask UI assets
- `ui`: desktop UI components

## Testing

Run the test suite:

```bash
pytest -q
```

Current coverage in this repo:
- 123 passing tests
- parser coverage
- pipeline coverage
- web app coverage
- regression coverage

## Notes

- The pipeline is deterministic for the same input set.
- Output order is stable.
- Parser failures are reported as warnings instead of crashing the run.
- Resume parsing is heuristic-based, not a full NLP system.
- PDF support depends on `pdfplumber`.

## Good Submission State

Before uploading to Git, keep:
- `src/`
- `tests/`
- `sample_inputs/`
- `static/`
- `templates/`
- `ui/`
- `app.py`
- `cli.py`
- `pyproject.toml`
- `README.md`
- `.gitignore`

