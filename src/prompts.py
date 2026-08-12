"""
Defines the 13 prompt techniques under test. Each technique is a dict with:
  id, name, category      - identifiers used in results/leaderboard
  system_instruction      - text sent as the model's system role (None if unused)
  user_content(excerpt)   - function building the user-role message for a given excerpt
  response_schema         - Gemini structured-output schema (None for free-text techniques)
  extract_for_scoring(raw) - pulls the plain text to run checklist matching against
                              (for JSON techniques this means parsing the JSON first)
  format_ok(raw)          - True if the output actually followed the requested format

Everything downstream (run_study.py, score.py) only depends on this list - to add a
14th technique, just append one more entry here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

TASK_INSTRUCTION = (
    "Summarise the key risks from the following section of an annual report."
)

# Two invented, generic finance-risk examples used for the few-shot techniques.
# Deliberately NOT from the JPMorgan excerpt under test, so the model can't just
# copy an example answer - it has to actually generalise the pattern.
FEW_SHOT_EXAMPLES = [
    {
        "excerpt": (
            "The Company's revenue is concentrated among a small number of large "
            "customers. The loss of any one of these customers, or a significant "
            "reduction in their purchasing, could materially reduce revenue. "
            "Additionally, the Company's supply chain relies on a single "
            "manufacturing partner in one country, exposing it to geopolitical "
            "and logistics disruption risk."
        ),
        "summary": (
            "- Customer concentration risk: revenue depends on a small number of large customers\n"
            "- Supply chain risk: single manufacturing partner creates geopolitical/logistics exposure"
        ),
    },
    {
        "excerpt": (
            "Fluctuations in foreign currency exchange rates could adversely affect "
            "reported results, as a significant portion of revenue is generated "
            "outside the Company's home currency. The Company is also subject to "
            "pending litigation related to a former product line, the outcome of "
            "which cannot be predicted and could result in material liabilities."
        ),
        "summary": (
            "- FX risk: significant foreign-currency revenue exposes results to exchange rate swings\n"
            "- Litigation risk: pending lawsuit over a former product line could create material liabilities"
        ),
    },
    {
        "excerpt": (
            "The Company depends on a small team of senior executives whose "
            "departure could disrupt strategy execution. It also faces increasing "
            "competition from well-capitalised new entrants and must continue "
            "investing in R&D to maintain its market position."
        ),
        "summary": (
            "- Key person risk: dependence on a small senior executive team\n"
            "- Competitive risk: well-funded new entrants pressure market position and require sustained R&D investment"
        ),
    },
    {
        "excerpt": (
            "A significant portion of the Company's assets are pledged as "
            "collateral under its credit facilities. A downgrade in credit rating "
            "could increase borrowing costs or trigger early repayment "
            "obligations, straining liquidity."
        ),
        "summary": (
            "- Credit/liquidity risk: pledged assets and potential rating downgrade could raise costs or trigger early repayment"
        ),
    },
    {
        "excerpt": (
            "The Company's products are subject to evolving data privacy "
            "regulations across multiple jurisdictions. Non-compliance could "
            "result in fines, and new legislation may require costly changes to "
            "how customer data is processed and stored."
        ),
        "summary": (
            "- Regulatory/compliance risk: evolving multi-jurisdiction data privacy law creates fine and cost exposure"
        ),
    },
]

_BULLET_RE = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
_RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "key_risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["key_risks"],
}


def _plain_text(raw: str) -> str:
    return raw


def _has_bullets(raw: str) -> bool:
    return len(_BULLET_RE.findall(raw)) >= 2


def _json_risks_text(raw: str) -> str:
    data = _parse_json_loose(raw)
    if not data or "key_risks" not in data:
        return ""
    return "\n".join(str(item) for item in data["key_risks"])


def _parse_json_loose(raw: str) -> Optional[dict]:
    # Models sometimes wrap JSON in ```json fences even when asked not to -
    # strip those before parsing rather than failing the whole technique on it.
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None


def _json_format_ok(raw: str) -> bool:
    data = _parse_json_loose(raw)
    return bool(data and isinstance(data.get("key_risks"), list) and len(data["key_risks"]) > 0)


def _five_bullets_under_20_words(raw: str) -> bool:
    bullets = [b.strip() for b in raw.strip().split("\n") if b.strip()]
    bullets = [b for b in bullets if _BULLET_RE.match(b + " ")]
    if len(bullets) != 5:
        return False
    return all(len(re.sub(r"^[-*•]\s*", "", b).split()) <= 20 for b in bullets)


def _cot_final_answer(raw: str) -> str:
    marker = "Final Summary:"
    if marker in raw:
        return raw.split(marker, 1)[1]
    return raw


@dataclass
class Technique:
    id: str
    name: str
    category: str
    system_instruction: Optional[str]
    user_content: Callable[[str], str]
    response_schema: Optional[dict] = None
    extract_for_scoring: Callable[[str], str] = field(default=_plain_text)
    format_ok: Callable[[str], bool] = field(default=_has_bullets)


def _fewshot_block(n: int) -> str:
    parts = []
    for ex in FEW_SHOT_EXAMPLES[:n]:
        parts.append(f"Report excerpt:\n{ex['excerpt']}\n\nKey risks:\n{ex['summary']}")
    return "\n\n---\n\n".join(parts)


TECHNIQUES: list[Technique] = [
    Technique(
        id="zero_shot",
        name="Zero-shot",
        category="baseline",
        system_instruction=None,
        user_content=lambda excerpt: f"{TASK_INSTRUCTION}\n\n{excerpt}",
    ),
    Technique(
        id="few_shot_2",
        name="Few-shot (2 examples)",
        category="few-shot",
        system_instruction=None,
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION} Here are two examples of the task done well:\n\n"
            f"{_fewshot_block(2)}\n\n---\n\nNow do the same for this excerpt:\n{excerpt}"
        ),
    ),
    Technique(
        id="few_shot_5",
        name="Few-shot (5 examples)",
        category="few-shot",
        system_instruction=None,
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION} Here are five examples of the task done well:\n\n"
            f"{_fewshot_block(5)}\n\n---\n\nNow do the same for this excerpt:\n{excerpt}"
        ),
    ),
    Technique(
        id="chain_of_thought",
        name="Chain-of-thought",
        category="reasoning",
        system_instruction=None,
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION}\n\n{excerpt}\n\n"
            "Think step by step: first list every risk-related statement you notice verbatim, "
            "then group related statements into themes, then write the final summary as bullet "
            "points. Put ONLY the final bullet-point summary after a line that says exactly "
            "'Final Summary:'."
        ),
        extract_for_scoring=_cot_final_answer,
        format_ok=lambda raw: "Final Summary:" in raw and _has_bullets(_cot_final_answer(raw)),
    ),
    Technique(
        id="role_prompting",
        name="Role prompting",
        category="persona",
        system_instruction="You are a compliance officer at a bank, reviewing risk disclosures for a client briefing.",
        user_content=lambda excerpt: f"{TASK_INSTRUCTION}\n\n{excerpt}",
    ),
    Technique(
        id="role_plus_cot",
        name="Role + chain-of-thought",
        category="combined",
        system_instruction="You are a compliance officer at a bank, reviewing risk disclosures for a client briefing.",
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION}\n\n{excerpt}\n\n"
            "Think step by step: first list every risk-related statement you notice verbatim, "
            "then group related statements into themes, then write the final summary as bullet "
            "points. Put ONLY the final bullet-point summary after a line that says exactly "
            "'Final Summary:'."
        ),
        extract_for_scoring=_cot_final_answer,
        format_ok=lambda raw: "Final Summary:" in raw and _has_bullets(_cot_final_answer(raw)),
    ),
    Technique(
        id="structured_json_prompted",
        name="Structured JSON (prompt-only)",
        category="structured",
        system_instruction=None,
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION}\n\n{excerpt}\n\n"
            'Respond with ONLY valid JSON in this exact shape, no other text: '
            '{"key_risks": ["risk 1", "risk 2", ...]}'
        ),
        extract_for_scoring=_json_risks_text,
        format_ok=_json_format_ok,
    ),
    Technique(
        id="structured_json_schema",
        name="Structured JSON (API-enforced schema)",
        category="structured",
        system_instruction=None,
        user_content=lambda excerpt: f"{TASK_INSTRUCTION}\n\n{excerpt}",
        response_schema=_RISK_SCHEMA,
        extract_for_scoring=_json_risks_text,
        format_ok=_json_format_ok,
    ),
    Technique(
        id="negative_prompting",
        name="Negative prompting",
        category="constraint",
        system_instruction=None,
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION}\n\n{excerpt}\n\n"
            "Do NOT include generic legal boilerplate or disclaimers. Do NOT repeat the same "
            "risk twice under different wording. Do NOT include any risk that is not explicitly "
            "stated in the text above."
        ),
    ),
    Technique(
        id="format_constrained",
        name="Format constraints (5 bullets, <=20 words)",
        category="constraint",
        system_instruction=None,
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION}\n\n{excerpt}\n\n"
            "Respond with EXACTLY 5 bullet points, each 20 words or fewer. No preamble, no "
            "closing remarks - only the 5 bullets."
        ),
        format_ok=_five_bullets_under_20_words,
    ),
    Technique(
        id="self_consistency",
        name="Self-consistency (internal 3-draft reconciliation)",
        category="reasoning",
        system_instruction=None,
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION}\n\n{excerpt}\n\n"
            "First, independently draft three separate lists of key risks (label them Draft 1, "
            "Draft 2, Draft 3). Then compare the three drafts and keep only the risks that "
            "appear in at least two of them. Put ONLY that final reconciled bullet-point list "
            "after a line that says exactly 'Final Summary:'."
        ),
        extract_for_scoring=_cot_final_answer,
        format_ok=lambda raw: "Final Summary:" in raw and _has_bullets(_cot_final_answer(raw)),
    ),
    Technique(
        id="system_vs_user_placement",
        name="Instruction in system role (vs user role)",
        category="structural",
        system_instruction=TASK_INSTRUCTION,
        user_content=lambda excerpt: excerpt,
    ),
    Technique(
        id="kitchen_sink",
        name="Combined (role + few-shot + CoT + JSON schema + format limit)",
        category="combined",
        system_instruction="You are a compliance officer at a bank, reviewing risk disclosures for a client briefing.",
        user_content=lambda excerpt: (
            f"{TASK_INSTRUCTION} Here are two examples of the task done well:\n\n"
            f"{_fewshot_block(2)}\n\n---\n\n"
            f"Now do the same for this excerpt:\n{excerpt}\n\n"
            "Think step by step first, then respond with ONLY valid JSON in this exact shape: "
            '{"key_risks": ["risk 1", "risk 2", ...]}. Include at most 5 risks, each under 20 words.'
        ),
        response_schema=_RISK_SCHEMA,
        extract_for_scoring=_json_risks_text,
        format_ok=_json_format_ok,
    ),
]

assert len(TECHNIQUES) == 13, f"expected 13 techniques, got {len(TECHNIQUES)}"
assert len({t.id for t in TECHNIQUES}) == 13, "technique ids must be unique"
