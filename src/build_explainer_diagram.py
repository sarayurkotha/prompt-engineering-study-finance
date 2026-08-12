"""
Generates outputs/prompt_anatomy_diagram.png - a plain-English explainer of what
a well-structured prompt is made of. Doesn't depend on API results, so it can be
regenerated any time independently of run_study.py / score_and_rank.py.
"""

from pathlib import Path

import matplotlib.pyplot as plt

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"

TEAL = "#087c7f"
CORAL = "#ff6f61"
TEAL_DARK = "#05363d"
LEMON = "#f4c95d"

PARTS = [
    ("Role", "\"You are a compliance\nofficer reviewing\nrisk disclosures.\"", TEAL_DARK,
     "Optional. Sets the lens the\nmodel reads the task through -\nchanges tone and priorities,\nnot facts it doesn't have."),
    ("Task", "\"Summarise the key\nrisks from the\nfollowing text.\"", CORAL,
     "The one thing you actually\nwant done. Specific verbs\n(summarise, extract, rank)\nbeat vague ones (analyse)."),
    ("Context", "[the annual report\nexcerpt itself]", TEAL,
     "The material the model\nshould reason from - not\nits general training\nknowledge."),
    ("Examples", "2-5 input -> output\npairs showing the\nshape you want", LEMON,
     "Optional. Shows the model\nthe pattern instead of just\ndescribing it - usually helps\nmore than a longer instruction."),
    ("Format", "\"Respond with exactly\n5 bullet points,\n<=20 words each.\"", TEAL_DARK,
     "Without this, output length\nand shape vary run to run -\nmakes downstream parsing\nunreliable."),
]


def main() -> None:
    fig, ax = plt.subplots(figsize=(14, 4.6))
    ax.set_xlim(0, 14.5)
    ax.set_ylim(0, 4.6)
    ax.axis("off")

    box_w, box_h = 2.4, 1.3
    y_box = 2.65
    xs = [0.3 + i * 2.75 for i in range(len(PARTS))]

    for x, (label, example, color, note) in zip(xs, PARTS):
        ax.add_patch(plt.Rectangle((x, y_box), box_w, box_h, facecolor=color, edgecolor="white", linewidth=1.5, zorder=2))
        ax.text(x + box_w / 2, y_box + box_h - 0.28, label, ha="center", va="center", fontsize=12, fontweight="bold", color="white", zorder=3)
        ax.text(x + box_w / 2, y_box + 0.45, example, ha="center", va="center", fontsize=7.5, color="white", zorder=3)
        ax.text(x + box_w / 2, y_box - 0.15, note, ha="center", va="top", fontsize=7.5, color="#5a6c70", zorder=3)

    for x1 in xs[:-1]:
        ax.annotate(
            "", xy=(x1 + box_w + 0.35, y_box + box_h / 2), xytext=(x1 + box_w, y_box + box_h / 2),
            arrowprops=dict(arrowstyle="-|>", color=TEAL_DARK, linewidth=1.6), zorder=1,
        )

    ax.text(
        7.25, 4.35,
        "Anatomy of a well-structured prompt",
        ha="center", va="center", fontsize=15, fontweight="bold", color=TEAL_DARK,
    )
    ax.text(
        7.25, 0.35,
        "Not every prompt needs every part - the 13-technique study tests exactly which combinations\n"
        "of these actually improve results on this task, versus which just add length for no gain.",
        ha="center", va="center", fontsize=9.5, color="#5a6c70", style="italic",
    )

    fig.tight_layout()
    fig.savefig(OUTPUTS_DIR / "prompt_anatomy_diagram.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {OUTPUTS_DIR / 'prompt_anatomy_diagram.png'}")


if __name__ == "__main__":
    main()
