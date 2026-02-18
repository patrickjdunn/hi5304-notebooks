# answer_layers.py
"""
Answer Layers for Signatures
============================

Purpose
-------
Keep your question bank (questions.py) as the stable "base content",
and optionally add small, safe "add-on" snippets based on:

1) Condition modifiers (from combined_calculator RESULTS["condition_modifiers"])
2) Engagement drivers (from combined_calculator RESULTS["engagement_drivers"], -1/0/+1)
3) Optionally: question tags (question["signatures"])

Design goals
------------
- Never break existing behavior: if no layers match, return "".
- Keep add-ons short and "non-disruptive" (1–3 bullets or 1 short paragraph).
- Avoid changing base answers. We only append add-ons.

Usage (in signatures_engine.py)
-------------------------------
from answer_layers import build_answer_addons

addon = build_answer_addons(q, calc_context=calc, style=style_key)
final_text = base if not addon else f"{base}\n\n{addon}"
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Helpers (local + safe)
# -----------------------------
def _safe_strip(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _is_selected(value: Any) -> bool:
    """
    Interpret condition flags robustly.
    Accepts: True, 1, "yes", "y", "true", "selected", "positive", "present"
    Rejects: False, 0, "", None, "no", "n", "false", "0"
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        # treat any nonzero as selected
        return value != 0
    s = _safe_strip(value).lower()
    if s in ("", "none", "null", "na", "n/a", "unknown"):
        return False
    if s in ("no", "n", "false", "0", "absent", "negative", "not present"):
        return False
    if s in ("yes", "y", "true", "1", "selected", "present", "positive"):
        return True
    # fallback: if it's a non-empty string, assume it's "selected"
    # (you can tighten this if needed)
    return True


def _get_calc_block(calc_context: Dict[str, Any], key: str) -> Dict[str, Any]:
    v = (calc_context or {}).get(key)
    return v if isinstance(v, dict) else {}


def _get_question_signatures(question: Dict[str, Any]) -> Dict[str, Any]:
    sig = (question or {}).get("signatures")
    return sig if isinstance(sig, dict) else {}


def _get_question_condition_tags(question: Dict[str, Any]) -> List[str]:
    sig = _get_question_signatures(question)
    mods = sig.get("condition_modifiers")
    if isinstance(mods, list):
        return [str(x).strip().upper() for x in mods if str(x).strip()]
    return []


def _get_question_engagement_tags(question: Dict[str, Any]) -> Dict[str, int]:
    """
    Question-bank engagement tags are usually stored as:
      question["signatures"]["engagement_drivers"] = {"HL": 1, "TR": 0, ...}
    """
    sig = _get_question_signatures(question)
    ed = sig.get("engagement_drivers")
    if isinstance(ed, dict):
        out: Dict[str, int] = {}
        for k, v in ed.items():
            kk = str(k).strip()
            if not kk:
                continue
            try:
                out[kk] = int(v)
            except Exception:
                # ignore non-int-ish
                continue
        return out
    return {}


def _bullets(items: List[str]) -> str:
    items2 = [f"- {_safe_strip(x)}" for x in items if _safe_strip(x)]
    return "\n".join(items2)


# -----------------------------
# Layer catalogs
# -----------------------------
# Condition add-ons: add short, safe lines when that condition is active.
# Keep these "general" so they can apply across many questions.
CONDITION_ADDONS: Dict[str, Dict[str, Any]] = {
    # Coronary artery disease
    "CAD": {
        "title": "CAD considerations",
        "lines": [
            "If exertion brings chest pressure, unusual shortness of breath, or dizziness, stop and follow your symptom action plan.",
            "Ask your clinician what your LDL-C target is and how your current plan supports it (meds + lifestyle).",
        ],
    },
    # Atrial fibrillation
    "AF": {
        "title": "AFib considerations",
        "lines": [
            "Know your stroke warning signs (FAST) and your anticoagulation plan if prescribed.",
            "If you notice sustained palpitations with fainting, chest pain, or severe breathlessness, seek urgent care.",
        ],
    },
    # Heart failure
    "HF": {
        "title": "Heart failure considerations",
        "lines": [
            "Track daily weight and swelling if advised; rapid weight gain can signal fluid retention.",
            "If shortness of breath suddenly worsens, or you can’t lie flat, contact your care team promptly.",
        ],
    },
    # Hypertension treatment / high BP
    "HTN": {
        "title": "Blood pressure considerations",
        "lines": [
            "Home BP technique matters: seated, rested 5 minutes, arm at heart level; take 2 readings and average.",
            "If readings are very high with symptoms (chest pain, severe headache, weakness, trouble speaking), seek urgent care.",
        ],
    },
    # Diabetes
    "DM": {
        "title": "Diabetes considerations",
        "lines": [
            "If you use insulin or meds that can cause lows, carry fast-acting carbs and know the 15–15 rule.",
            "Ask what your A1c target is and how often to recheck based on your regimen and risk.",
        ],
    },
    # CKM / metabolic-kidney-heart
    "CKMH": {
        "title": "Heart–kidney–metabolic considerations",
        "lines": [
            "These systems are connected—BP, glucose, kidney function, and lipids work together in risk reduction.",
            "Ask how your eGFR and UACR affect your medication choices and monitoring frequency.",
        ],
    },
    # Stroke / TIA history
    "ST": {
        "title": "Stroke/TIA considerations",
        "lines": [
            "If you have new one-sided weakness, facial droop, or speech trouble, treat it as an emergency (call 911).",
            "Secondary prevention often focuses on BP, cholesterol, diabetes, and rhythm (AFib) control—ask which apply to you.",
        ],
    },
    # Cholesterol treatment (e.g., statin)
    "CH": {
        "title": "Cholesterol treatment considerations",
        "lines": [
            "If you have muscle aches or concerns about statins, don’t stop abruptly—ask about dose adjustments or alternatives.",
            "Recheck your lipid panel on the schedule your clinician recommends to confirm you’re at goal.",
        ],
    },
}


# Engagement driver add-ons based on calculator driver values (-1/0/+1).
# These are delivery/behavioral coaching micro-snippets.
ENGAGEMENT_ADDONS: Dict[str, Dict[int, List[str]]] = {
    # Trust
    "trust": {
        -1: [
            "If you’re unsure who to trust, we can stick to one or two well-known sources and confirm the plan with your clinician.",
            "It’s okay to ask: “What’s the benefit, what’s the downside, and what are my options?”",
        ],
        1: [
            "Since you’re engaged with your care, consider bringing your tracked data (BP, steps, symptoms) to tighten the plan together.",
        ],
    },
    # Health literacy
    "health_literacy": {
        -1: [
            "Here’s the short version: pick 1 change this week, track it for 7 days, and bring the results to your next visit.",
            "If any terms feel unclear, ask for plain-language explanations—good care should be understandable.",
        ],
        1: [
            "If you like details, ask for your exact targets (BP, LDL, A1c) and how your numbers are trending over time.",
        ],
    },
    # Readiness for change
    "readiness_for_change": {
        -1: [
            "No pressure to change everything today—choose the smallest step that feels realistic and start there.",
        ],
        1: [
            "Since you feel ready, choose one “next-step” goal and set a check-in date to review progress.",
        ],
    },
    # Self-efficacy (confidence)
    "selfefficacy": {
        -1: [
            "Let’s make this easier: define a 5-minute starter step you can succeed with, then build from wins.",
        ],
        1: [
            "You seem confident—use that strength to build a simple routine and track streaks.",
        ],
    },
    # Proactiveness
    "proactiveness": {
        -1: [
            "If this feels like a lot, start by writing 2 questions for your next visit—momentum often starts with clarity.",
        ],
        1: [
            "You’re being proactive—consider a weekly ‘health planning’ time to review meds, activity, and symptoms.",
        ],
    },
    # Goal orientation
    "goal_orientation": {
        -1: [
            "Try one SMART goal: specific, measurable, achievable, relevant, time-bound (example: walk 10 minutes after dinner 5 days this week).",
        ],
        1: [
            "Pick a measurable target for the next 7 days and track it daily (minutes, steps, BP, or sleep).",
        ],
    },
    # Independence
    "independence": {
        -1: [
            "If you rely on others, choose one support person and give them a clear role (reminders, walks, meal planning).",
        ],
        1: [
            "Since you prefer autonomy, use a simple self-tracking tool and bring the summary to visits.",
        ],
    },
    # Decision style
    "decision_style": {
        -1: [
            "If decisions feel stressful, ask your clinician for 2–3 options and a recommendation, then take 24 hours to decide if needed.",
        ],
        1: [
            "Since you like exploring options, ask: “What are the alternatives and what evidence supports each?”",
        ],
    },
    # Food insecurity
    "food_insecurity": {
        -1: [
            "If cost or access is a barrier, ask about budget-friendly heart-healthy staples (beans, frozen vegetables, oats) and local support resources.",
        ],
        1: [
            "If access is good, plan one grocery swap this week that supports your goal (lower sodium, higher fiber).",
        ],
    },
    # Access to healthcare
    "access_to_healthcare": {
        -1: [
            "If appointments are hard to access, ask about telehealth follow-ups, remote monitoring, or community-based resources.",
        ],
        1: [
            "Since you can access care, consider scheduling a follow-up date now to review progress and adjust the plan.",
        ],
    },
}


# If you want to only apply certain condition add-ons when the question is relevant,
# set this to True. If False, any active condition can add its lines (still short/safe).
REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS = False


# -----------------------------
# Main builder
# -----------------------------
def build_answer_addons(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]],
    style: str,
) -> str:
    """
    Returns a single string with optional add-on content.

    - question: a question dict from the built question bank
    - calc_context: combined_calculator results merged with CALC_CONTEXT
    - style: "listener" | "motivator" | "director" | "expert" (or any string; we don't depend on it)

    If no add-ons match, returns "".
    """
    if not isinstance(question, dict):
        return ""
    calc_context = calc_context if isinstance(calc_context, dict) else {}

    # pull calculator blocks
    calc_conditions = _get_calc_block(calc_context, "condition_modifiers")
    calc_drivers = _get_calc_block(calc_context, "engagement_drivers")

    # question tags
    q_condition_tags = set(_get_question_condition_tags(question))  # e.g., {"AF", "CAD"}
    # Note: question engagement tags exist too, but we typically use calculator drivers for add-ons.

    addon_lines: List[str] = []
    addon_sections: List[Tuple[str, List[str]]] = []

    # -----------------------------
    # Condition modifiers add-ons
    # -----------------------------
    active_conditions: List[str] = []
    for code, raw in calc_conditions.items():
        code_u = str(code).strip().upper()
        if not code_u:
            continue
        if _is_selected(raw):
            active_conditions.append(code_u)

    cond_lines: List[str] = []
    for cond in active_conditions:
        if cond not in CONDITION_ADDONS:
            continue

        if REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS:
            if q_condition_tags and (cond not in q_condition_tags):
                # question has tags and this condition is not among them -> skip
                continue

        payload = CONDITION_ADDONS.get(cond, {})
        for line in payload.get("lines", []):
            if _safe_strip(line):
                cond_lines.append(_safe_strip(line))

    if cond_lines:
        addon_sections.append(("Condition-tailored notes", cond_lines))

    # -----------------------------
    # Engagement driver add-ons
    # -----------------------------
    # Expecting calculator drivers keys like:
    # "trust", "health_literacy", "readiness_for_change", etc with -1/0/+1
    drv_lines: List[str] = []
    for driver_key, variants in ENGAGEMENT_ADDONS.items():
        if not isinstance(variants, dict):
            continue
        if driver_key not in calc_drivers:
            continue
        try:
            val = int(calc_drivers.get(driver_key))
        except Exception:
            continue
        if val not in (-1, 0, 1):
            continue
        if val == 0:
            continue
        for line in variants.get(val, []):
            if _safe_strip(line):
                drv_lines.append(_safe_strip(line))

    if drv_lines:
        addon_sections.append(("Personalized support", drv_lines))

    # -----------------------------
    # Assemble output
    # -----------------------------
    if not addon_sections:
        return ""

    blocks: List[str] = []
    for title, lines in addon_sections:
        # Keep it compact: header + bullets
        blocks.append(f"{title}:\n{_bullets(lines)}")

    return "\n\n".join(blocks).strip()


# Optional: structured form (useful for future LLM prompting)
def build_answer_addons_structured(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]],
    style: str,
) -> Dict[str, Any]:
    """
    Like build_answer_addons(), but returns structure:
      {
        "text": "...",
        "sections": [{"title": "...", "bullets": [...]}, ...],
        "debug": {"active_conditions": [...], "matched_drivers": {...}}
      }
    """
    calc_context = calc_context if isinstance(calc_context, dict) else {}
    calc_conditions = _get_calc_block(calc_context, "condition_modifiers")
    calc_drivers = _get_calc_block(calc_context, "engagement_drivers")

    q_condition_tags = set(_get_question_condition_tags(question))

    active_conditions: List[str] = []
    for code, raw in calc_conditions.items():
        code_u = str(code).strip().upper()
        if not code_u:
            continue
        if _is_selected(raw):
            active_conditions.append(code_u)

    sections: List[Dict[str, Any]] = []
    matched_drivers: Dict[str, int] = {}

    # Conditions
    cond_lines: List[str] = []
    for cond in active_conditions:
        if cond not in CONDITION_ADDONS:
            continue
        if REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS:
            if q_condition_tags and (cond not in q_condition_tags):
                continue
        payload = CONDITION_ADDONS.get(cond, {})
        for line in payload.get("lines", []):
            if _safe_strip(line):
                cond_lines.append(_safe_strip(line))
    if cond_lines:
        sections.append({"title": "Condition-tailored notes", "bullets": cond_lines})

    # Drivers
    drv_lines: List[str] = []
    for driver_key, variants in ENGAGEMENT_ADDONS.items():
        if driver_key not in calc_drivers:
            continue
        try:
            val = int(calc_drivers.get(driver_key))
        except Exception:
            continue
        if val in (-1, 1):
            matched_drivers[driver_key] = val
            for line in variants.get(val, []):
                if _safe_strip(line):
                    drv_lines.append(_safe_strip(line))
    if drv_lines:
        sections.append({"title": "Personalized support", "bullets": drv_lines})

    text_blocks = []
    for s in sections:
        text_blocks.append(f"{s['title']}:\n{_bullets(s.get('bullets', []))}")
    text = "\n\n".join(text_blocks).strip()

    return {
        "text": text,
        "sections": sections,
        "debug": {
            "active_conditions": active_conditions,
            "question_condition_tags": sorted(list(q_condition_tags)),
            "matched_drivers": matched_drivers,
        },
    }
