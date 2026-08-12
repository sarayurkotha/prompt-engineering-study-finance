"""
Loads the 13 prompt techniques from data/prompt_templates.csv - a plain CSV you
can open in Excel or a text editor and read every prompt end to end, no Python
needed. This file's only job is (a) load that CSV into a list of plain dicts,
and (b) know how to check each technique's output for format compliance.

Each technique dict has these keys:
  technique_id, name, category    - identifiers used in results/leaderboard
  system_instruction              - text sent as the model's system role ("" if unused)
  user_content_template           - prompt text with a {{EXCERPT}} placeholder
  uses_json_schema                - True if this technique should use Gemini's
                                     API-enforced JSON schema (not just a text request)
  format_type                     - one of "bullets", "cot_bullets", "json",
                                     "exact5_20w" - which format-checking rule applies
                                     (see FORMAT_CHECKS below)

To add a 14th technique: add one row to the CSV. Nothing in this file needs to
change unless the new technique needs a genuinely new kind of format check.
"""

import csv
import json
import re
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "prompt_templates.csv"

RISK_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "key_risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["key_risks"],
}

_BULLET_RE = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)


def render_prompt(template: str, excerpt: str) -> str:
    """Fills in the one placeholder every template has - this is the entire
    "templating engine": no library needed for a single find-and-replace."""
    return template.replace("{{EXCERPT}}", excerpt)


def _parse_json_loose(raw: str) -> dict | None:
    # Models sometimes wrap JSON in ```json fences even when asked not to -
    # strip those before parsing rather than failing the whole technique on it.
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


def _has_bullets(text: str) -> bool:
    return len(_BULLET_RE.findall(text)) >= 2


def _cot_final_answer(raw: str) -> str:
    marker = "Final Summary:"
    return raw.split(marker, 1)[1] if marker in raw else raw


# --- format_type dispatch ---------------------------------------------------
# Every technique's output gets checked and scored the same way EXCEPT for how
# it decides (a) whether the output followed the requested format, and (b)
# which part of the raw text actually counts as "the answer" to run checklist
# matching against. Both of those only depend on format_type, so instead of a
# bespoke function per technique (13 of them), there are only 4 rules here -
# one per distinct output shape the 13 techniques actually use.

def _format_ok_bullets(raw: str) -> bool:
    return _has_bullets(raw)


def _format_ok_cot_bullets(raw: str) -> bool:
    return "Final Summary:" in raw and _has_bullets(_cot_final_answer(raw))


def _format_ok_json(raw: str) -> bool:
    data = _parse_json_loose(raw)
    return bool(data and isinstance(data.get("key_risks"), list) and len(data["key_risks"]) > 0)


def _format_ok_exact5_20w(raw: str) -> bool:
    bullets = [b.strip() for b in raw.strip().split("\n") if b.strip()]
    bullets = [b for b in bullets if _BULLET_RE.match(b + " ")]
    if len(bullets) != 5:
        return False
    return all(len(re.sub(r"^[-*•]\s*", "", b).split()) <= 20 for b in bullets)


def _extract_plain(raw: str) -> str:
    return raw


def _extract_cot(raw: str) -> str:
    return _cot_final_answer(raw)


def _extract_json(raw: str) -> str:
    data = _parse_json_loose(raw)
    if not data or "key_risks" not in data:
        return ""
    return "\n".join(str(item) for item in data["key_risks"])


FORMAT_CHECKS = {
    "bullets": {"format_ok": _format_ok_bullets, "extract_for_scoring": _extract_plain},
    "cot_bullets": {"format_ok": _format_ok_cot_bullets, "extract_for_scoring": _extract_cot},
    "json": {"format_ok": _format_ok_json, "extract_for_scoring": _extract_json},
    "exact5_20w": {"format_ok": _format_ok_exact5_20w, "extract_for_scoring": _extract_plain},
}


def load_techniques() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        row["uses_json_schema"] = row["uses_json_schema"] == "TRUE"
        checks = FORMAT_CHECKS[row["format_type"]]
        row["format_ok"] = checks["format_ok"]
        row["extract_for_scoring"] = checks["extract_for_scoring"]
    return rows


TECHNIQUES: list[dict] = load_techniques()

assert len(TECHNIQUES) == 13, f"expected 13 techniques, got {len(TECHNIQUES)}"
assert len({t["technique_id"] for t in TECHNIQUES}) == 13, "technique_ids must be unique"
