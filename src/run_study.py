"""
Calls the Gemini API once per (technique, run) pair - 13 techniques x 5 runs = 65
calls - and saves every raw response to results/raw_runs.jsonl. Scoring happens
separately in score_and_rank.py, so this script's only job is "collect the data."

Needs a free Gemini API key in a local .env file (GEMINI_API_KEY=...) - see README.

The free tier for full gemini-3.5-flash allows only 5 requests per MINUTE -
found this out the hard way on the first attempt, which hit 429
RESOURCE_EXHAUSTED after ~19 calls and never fully recovered within a
reasonable wait. Switched to gemini-3.5-flash-lite, which has its own,
separate and much roomier free-tier quota. SECONDS_BETWEEN_CALLS and the
retry-with-backoff logic are kept conservative regardless, since free-tier
limits can change.

Safe to re-run: any (technique, run) pair already present in raw_runs.jsonl
without an error is skipped, so a partial/failed run just picks up where it
left off instead of re-spending quota on calls that already succeeded.
"""

import json
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from prompts import TECHNIQUES

load_dotenv()

MODEL = "gemini-3.5-flash-lite"
N_RUNS = 5
SECONDS_BETWEEN_CALLS = 13  # free tier = 5 requests/minute -> 12s minimum, +1s buffer
MAX_RETRIES = 4
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "results" / "raw_runs.jsonl"
EXCERPT_PATH = Path(__file__).resolve().parent.parent / "data" / "source_excerpt.txt"


def load_excerpt() -> str:
    text = EXCERPT_PATH.read_text(encoding="utf-8")
    # The file starts with a citation block separated from the actual excerpt by "---".
    return text.split("---", 1)[1].strip()


def load_existing_successes() -> dict[tuple[str, int], dict]:
    if not OUTPUT_PATH.exists():
        return {}
    existing = {}
    with OUTPUT_PATH.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if not row["error"]:
                existing[(row["technique_id"], row["run_index"])] = row
    return existing


def call_gemini(client: genai.Client, technique, excerpt: str) -> tuple[str, float]:
    config_kwargs = {}
    if technique.system_instruction:
        config_kwargs["system_instruction"] = technique.system_instruction
    if technique.response_schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = technique.response_schema

    for attempt in range(MAX_RETRIES):
        started = time.monotonic()
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=technique.user_content(excerpt),
                config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
            )
            return response.text or "", time.monotonic() - started
        except ClientError as exc:
            if "RESOURCE_EXHAUSTED" in str(exc) and attempt < MAX_RETRIES - 1:
                backoff = 20 * (attempt + 1)
                print(f"    rate limited, retrying in {backoff}s...")
                time.sleep(backoff)
                continue
            raise
    raise RuntimeError("unreachable")


def main() -> None:
    client = genai.Client()
    excerpt = load_excerpt()
    OUTPUT_PATH.parent.mkdir(exist_ok=True)

    existing = load_existing_successes()
    all_pairs = [(t, r) for t in TECHNIQUES for r in range(N_RUNS)]
    to_run = [(t, r) for t, r in all_pairs if (t.id, r) not in existing]

    print(f"{len(existing)} already succeeded, {len(to_run)} left to run.")

    results_by_pair = dict(existing)
    for i, (technique, run_index) in enumerate(to_run, start=1):
        try:
            raw_text, elapsed_s = call_gemini(client, technique, excerpt)
            error = None
        except Exception as exc:  # API errors shouldn't kill the whole run
            raw_text, elapsed_s, error = "", 0.0, str(exc)

        results_by_pair[(technique.id, run_index)] = {
            "technique_id": technique.id,
            "run_index": run_index,
            "raw_text": raw_text,
            "elapsed_s": round(elapsed_s, 2),
            "error": error,
        }

        # Rewrite the whole file after each call - keeps it always in a valid,
        # resumable state even if this process gets interrupted mid-run.
        with OUTPUT_PATH.open("w", encoding="utf-8") as out:
            for t, r in all_pairs:
                if (t.id, r) in results_by_pair:
                    out.write(json.dumps(results_by_pair[(t.id, r)]) + "\n")

        print(f"[{i}/{len(to_run)}] {technique.id} run {run_index + 1}/{N_RUNS} "
              f"({'error: ' + error[:80] if error else f'{elapsed_s:.1f}s'})")

        if i < len(to_run):
            time.sleep(SECONDS_BETWEEN_CALLS)

    print(f"\nWrote {len(results_by_pair)} results to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
