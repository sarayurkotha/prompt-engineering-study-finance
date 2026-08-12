"""
Reads results/raw_runs.jsonl, scores every run against the manually-built ground
truth checklist, aggregates per technique, and writes:
  - results/scored_runs.csv   (one row per run - full transparency)
  - results/leaderboard.csv   (one row per technique - the ranked leaderboard)
  - outputs/leaderboard.png   (ranked bar chart)
  - outputs/score_breakdown.png (coverage / consistency / format, side by side)

Leaderboard score per technique = weighted average of three 0-1 metrics:
  - coverage:   mean fraction of the 10 ground-truth risk themes mentioned,
                averaged across the 5 runs (this is the "accuracy/completeness" axis)
  - consistency: (themes present in ALL 5 runs) / (themes present in AT LEAST 1 run) -
                 a technique that finds the same risks every time scores near 1.0;
                 one that finds different risks each run scores near 0
  - format:     fraction of the 5 runs that followed the requested output format
Weights are the WEIGHTS constant below - change them and re-run to see how the
ranking shifts, that's part of the point of building this as a script, not a
one-off notebook cell.
"""

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from prompts import TECHNIQUES

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"
CHECKLIST_PATH = Path(__file__).resolve().parent.parent / "data" / "ground_truth_checklist.json"

WEIGHTS = {"coverage": 0.4, "consistency": 0.3, "format": 0.3}

TEAL = "#087c7f"
CORAL = "#ff6f61"
TEAL_DARK = "#05363d"

TECHNIQUES_BY_ID = {t.id: t for t in TECHNIQUES}


def load_checklist() -> list[dict]:
    data = json.loads(CHECKLIST_PATH.read_text(encoding="utf-8"))
    return data["themes"]


def matched_themes(text: str, themes: list[dict]) -> set[str]:
    lowered = text.lower()
    return {
        theme["id"]
        for theme in themes
        if any(keyword.lower() in lowered for keyword in theme["keywords"])
    }


def score_runs() -> pd.DataFrame:
    themes = load_checklist()
    rows = []
    with (RESULTS_DIR / "raw_runs.jsonl").open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            technique = TECHNIQUES_BY_ID[row["technique_id"]]
            if row["error"]:
                rows.append({**row, "coverage": 0.0, "format_ok": False, "matched": ""})
                continue
            scoring_text = technique.extract_for_scoring(row["raw_text"])
            matched = matched_themes(scoring_text, themes)
            rows.append(
                {
                    **row,
                    "coverage": len(matched) / len(themes),
                    "format_ok": technique.format_ok(row["raw_text"]),
                    "matched": ",".join(sorted(matched)),
                }
            )
    return pd.DataFrame(rows)


def build_leaderboard(scored: pd.DataFrame) -> pd.DataFrame:
    themes = load_checklist()
    theme_ids = {t["id"] for t in themes}
    leaderboard_rows = []

    for technique_id, group in scored.groupby("technique_id"):
        technique = TECHNIQUES_BY_ID[technique_id]
        matched_sets = [
            set(m.split(",")) if m else set() for m in group["matched"]
        ]
        present_in_all = set.intersection(*matched_sets) if matched_sets else set()
        present_in_any = set.union(*matched_sets) if matched_sets else set()
        consistency = len(present_in_all) / len(present_in_any) if present_in_any else 0.0

        coverage = group["coverage"].mean()
        format_rate = group["format_ok"].mean()
        final_score = (
            WEIGHTS["coverage"] * coverage
            + WEIGHTS["consistency"] * consistency
            + WEIGHTS["format"] * format_rate
        )

        leaderboard_rows.append(
            {
                "technique_id": technique_id,
                "name": technique.name,
                "category": technique.category,
                "coverage": round(coverage, 3),
                "consistency": round(consistency, 3),
                "format_compliance": round(format_rate, 3),
                "avg_latency_s": round(group["elapsed_s"].mean(), 2),
                "error_count": int((group["error"].notna()).sum()),
                "final_score": round(final_score, 3),
            }
        )

    leaderboard = pd.DataFrame(leaderboard_rows).sort_values("final_score", ascending=False)
    leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))
    return leaderboard


def plot_leaderboard(leaderboard: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    ordered = leaderboard.sort_values("final_score")
    colors = [TEAL if i == len(ordered) - 1 else CORAL if i == 0 else "#5a6c70" for i in range(len(ordered))]
    ax.barh(ordered["name"], ordered["final_score"], color=colors)
    ax.set_xlabel("Leaderboard score (weighted: coverage 40%, consistency 30%, format 30%)")
    ax.set_title("Prompt technique leaderboard - financial risk summarisation")
    ax.set_xlim(0, 1)
    fig.tight_layout()
    fig.savefig(OUTPUTS_DIR / "leaderboard.png", dpi=150)
    plt.close(fig)


def plot_breakdown(leaderboard: pd.DataFrame) -> None:
    ordered = leaderboard.sort_values("final_score", ascending=False)
    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(ordered))
    width = 0.25
    ax.bar([i - width for i in x], ordered["coverage"], width, label="Coverage", color=TEAL)
    ax.bar(x, ordered["consistency"], width, label="Consistency", color=CORAL)
    ax.bar([i + width for i in x], ordered["format_compliance"], width, label="Format compliance", color=TEAL_DARK)
    ax.set_xticks(list(x))
    ax.set_xticklabels(ordered["name"], rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("Score (0-1)")
    ax.set_title("Score breakdown by technique, ranked by final score")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUTS_DIR / "score_breakdown.png", dpi=150)
    plt.close(fig)


def main() -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    scored = score_runs()
    scored.to_csv(RESULTS_DIR / "scored_runs.csv", index=False, quoting=csv.QUOTE_MINIMAL)

    leaderboard = build_leaderboard(scored)
    leaderboard.to_csv(RESULTS_DIR / "leaderboard.csv", index=False)

    plot_leaderboard(leaderboard)
    plot_breakdown(leaderboard)

    print(leaderboard.to_string(index=False))
    winner = leaderboard.iloc[0]
    print(f"\nWinner: {winner['name']} (score {winner['final_score']})")


if __name__ == "__main__":
    main()
