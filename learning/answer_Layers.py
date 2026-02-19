# answer_Layers.py
"""
Answer Layers for Signatures
============================

This module lets you keep *questions.py* as stable base content while safely
adding short, optional "answer layers" (add-ons) based on runtime context from
combined_calculator.py (RESULTS dict).

Key ideas
---------
- Base answers live in questions.py and should not be mutated here.
- Layers are appended (never replace).
- If nothing matches, output is unchanged.

Public API
----------
1) build_answer_addons(question, calc_context, style) -> str
2) build_answer_addons_structured(question, calc_context, style) -> dict
3) build_layered_answer_structured(question, base, calc_context, style) -> dict

Structured payload format (LLM-friendly)
----------------------------------------
{
  "base": "...",
  "addons": ["...", "..."],
  "why_added": ["CAD active", "trust -1", "cvd_10yr > 7.5%"],
  "final": "base\\n\\n- addon...\\n- addon..."
}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Helpers (local + safe)
# =============================================================================

def _safe_strip(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _bullets(items: List[str]) -> str:
    lines = [f"- {_safe_strip(x)}" for x in items if _safe_strip(x)]
    return "\n".join(lines).strip()


def _normalize_persona(style: str) -> str:
    """
    Normalize style/persona to lowercase keys used by the engine:
      listener / motivator / director / expert
    """
    s = _safe_strip(style).lower()
    if s in ("listener", "motivator", "director", "expert"):
        return s
    # tolerate numbered prompts etc.
    mapping = {"1": "listener", "2": "motivator", "3": "director", "4": "expert"}
    return mapping.get(s, s or "listener")


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
        return value != 0
    s = _safe_strip(value).lower()
    if s in ("", "none", "null", "na", "n/a", "unknown"):
        return False
    if s in ("no", "n", "false", "0", "absent", "negative", "not present"):
        return False
    if s in ("yes", "y", "true", "1", "selected", "present", "positive"):
        return True
    # fallback: non-empty string -> treat as selected
    return True


def _get_block(calc_context: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
    calc_context = calc_context if isinstance(calc_context, dict) else {}
    v = calc_context.get(key)
    return v if isinstance(v, dict) else {}


def _get_question_signatures(question: Dict[str, Any]) -> Dict[str, Any]:
    sig = (question or {}).get("signatures")
    return sig if isinstance(sig, dict) else {}


def _get_question_condition_tags(question: Dict[str, Any]) -> List[str]:
    sig = _get_question_signatures(question)
    mods = sig.get("condition_modifiers")
    if isinstance(mods, list):
        return [str(x).strip().upper() for x in mods if _safe_strip(x)]
    return []


# =============================================================================
# Layer catalogs
# =============================================================================

# Condition-specific add-ons. Keep short and “safe”.
CONDITION_ADDONS: Dict[str, Dict[str, Any]] = {
    "CAD": {

        "lines": [
            "Because CAD is active, prioritize symptom awareness (chest pressure, unusual breathlessness) and follow your care plan closely.",
            "Ask your clinician what your LDL-C target is and how your plan (meds + lifestyle) supports it.",
        ],
    },
    "AF": {

        "lines": [
            "Because AF is active, stroke prevention and rhythm/rate monitoring are especially important.",
            "Know stroke warning signs (FAST). Seek urgent care for face droop, arm weakness, or speech trouble.",
        ],
    },
    "HF": {

        "lines": [
            "Because HF is active, monitor daily weight and swelling if advised, and act early on rapid changes per your plan.",
        ],
    },
    "HTN": {

        "lines": [
            "Because HTN treatment is active, home BP technique matters: rested 5 minutes, arm at heart level, take 2 readings and average.",
        ],
    },
    "DM": {

        "lines": [
            "Because diabetes is active, focus on steady routines (meals, meds, activity) and discuss your A1c target and monitoring plan.",
        ],
    },
    "CKMH": {

        "lines": [
            "Because CKM is active, think in connected systems: BP, glucose, kidney function, and cholesterol improvements work together.",
        ],
    },
    "ST": {

        "lines": [
            "Because stroke/TIA history is active, secondary prevention (BP, cholesterol, diabetes, rhythm control) is especially important—ask which apply to you.",
        ],
    },
    "CH": {

        "lines": [
            "Because cholesterol treatment is active, don’t stop statins abruptly—ask about dose adjustments or alternatives if side effects occur.",
        ],
    },
}

# Engagement driver add-ons (by -1/0/+1)
ENGAGEMENT_ADDONS: Dict[str, Dict[int, List[str]]] = {
    "trust": {
        -1: [
            "If trust feels low right now, it’s okay to ask for simpler explanations and a clear next step—your questions are valid.",
            "Ask: “What’s the benefit, what’s the downside, and what are my options?”",
        ],
        1: [
            "Since you’re engaged with your care, consider bringing tracked data (BP, steps, symptoms) to fine-tune the plan with your clinician.",
        ],
    },
    "selfefficacy": {
        -1: [
            "Let’s make this easier: choose a 5-minute starter step you can succeed with, then build from wins.",
        ],
        1: [
            "You seem confident—use that strength to build a simple routine and track streaks.",
        ],
    },
    "proactiveness": {
        -1: [
            "If this feels like a lot, start by writing 2 questions for your next visit—momentum often starts with clarity.",
        ],
        1: [
            "You’re being proactive—consider a weekly “health planning” time to review meds, activity, and symptoms.",
        ],
    },
    "readiness_for_change": {
        -1: [
            "No pressure to change everything today—choose the smallest step that feels realistic and start there.",
        ],
        1: [
            "Since you feel ready, choose one “next-step” goal and set a check-in date to review progress.",
        ],
    },
    "health_literacy": {
        -1: [
            "Here’s the short version: pick 1 change this week, track it for 7 days, and bring the results to your next visit.",
        ],
        1: [
            "If you like details, ask for your exact targets (BP, LDL, A1c) and how your numbers are trending over time.",
        ],
    },
    "goal_orientation": {
        -1: [
            "Try one SMART goal (specific, measurable, achievable, relevant, time-bound)—example: walk 10 minutes after dinner 5 days this week.",
        ],
        1: [
            "Pick a measurable target for the next 7 days and track it daily (minutes, steps, BP, or sleep).",
        ],
    },
    "access_to_healthcare": {
        -1: [
            "If appointments are hard to access, ask about telehealth follow-ups, remote monitoring, or community-based resources.",
        ],
        1: [
            "Since you can access care, consider scheduling a follow-up date now to review progress and adjust the plan.",
        ],
    },
}

# Risk-tier triggered add-ons (NEW)
# Trigger: 10-year CVD risk > 7.5%
RISK_TIER_ADDONS: Dict[str, List[str]] = {
    "default": [
        "Because your 10-year CVD risk is above 7.5%, it’s worth discussing a more intensive prevention plan (BP, LDL-C, diabetes control, smoking status, and activity).",
        "Ask: “What are my top 2 risk drivers, and what change this month would reduce my risk the most?”",
    ]
}

# If True, condition add-ons only apply if the question has matching condition tags.
REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS = False


# =============================================================================
# Internal collector (core of the system)
# =============================================================================

def _collect_addons_and_reasons(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]],
    style: str,
) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """
    Returns:
      addons: [line1, line2, ...]   (flat list of bullet lines)
      why_added: ["CAD active", "trust -1", ...]
      debug: { ... }                (safe debug info)
    """
    addons: List[str] = []
    why: List[str] = []
    debug: Dict[str, Any] = {}

    question = question if isinstance(question, dict) else {}
    calc_context = calc_context if isinstance(calc_context, dict) else {}
    persona = _normalize_persona(style)

    calc_conditions = _get_block(calc_context, "condition_modifiers")
    calc_drivers = _get_block(calc_context, "engagement_drivers")
    prevent_block = _get_block(calc_context, "prevent")  # where your 6 risks live

    q_condition_tags = set(_get_question_condition_tags(question))

    # -----------------------------
    # Active conditions -> addons
    # -----------------------------
    active_conditions: List[str] = []
    for code, raw in calc_conditions.items():
        code_u = _safe_strip(code).upper()
        if not code_u:
            continue
        if _is_selected(raw):
            active_conditions.append(code_u)


    for cond in active_conditions:
        if cond not in CONDITION_ADDONS:
            continue

        if REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS:
            if q_condition_tags and (cond not in q_condition_tags):
                continue

        lines = CONDITION_ADDONS.get(cond, {}).get("lines", [])
        if isinstance(lines, list):
            for line in lines:
                line_s = _safe_strip(line)
                if line_s:
                    addons.append(line_s)
        why.append(f"{cond} active")

    debug["active_conditions"] = active_conditions
    debug["question_condition_tags"] = sorted(list(q_condition_tags))

    # -----------------------------
    # Engagement drivers -> addons
    # -----------------------------
    matched_drivers: Dict[str, int] = {}
    for driver_key, variants in ENGAGEMENT_ADDONS.items():
        if driver_key not in calc_drivers:
            continue
        try:
            val = int(calc_drivers.get(driver_key))
        except Exception:
            continue
        if val == 0 or val not in (-1, 0, 1):
            continue

        matched_drivers[driver_key] = val

        for line in variants.get(val, []):
            line_s = _safe_strip(line)
            if line_s:
                addons.append(line_s)
        why.append(f"{driver_key} {val}")

    debug["matched_drivers"] = matched_drivers

    # -----------------------------
    # Risk-tier trigger (NEW)
    # -----------------------------
    cvd_10yr = prevent_block.get("cvd_10yr")
    if isinstance(cvd_10yr, (int, float)) and cvd_10yr > 0.075:
        # You can tailor by persona if you want; keep it safe and short
        risk_lines = list(RISK_TIER_ADDONS.get("default", []))
        if persona == "listener":
            risk_lines.insert(0, "It makes sense to feel concerned—higher risk is information, not a sentence. We can use it to focus your next steps.")
        elif persona == "motivator":
            risk_lines.insert(0, "This is a great moment to get proactive—small changes can make a meaningful difference in risk.")
        elif persona == "director":
            risk_lines.insert(0, "Next-step focus: confirm targets (BP, LDL-C, A1c), tighten your weekly activity plan, and schedule follow-up to reassess.")
        elif persona == "expert":
            risk_lines.insert(0, "A 10-year CVD risk above 7.5% is commonly used as a threshold to consider intensified preventive strategies in shared decision-making.")
        for line in risk_lines:
            line_s = _safe_strip(line)
            if line_s:
                addons.append(line_s)
        why.append("cvd_10yr > 7.5%")

        debug["cvd_10yr"] = cvd_10yr

    # De-dup (keep order)
    seen: set = set()
    deduped_addons: List[str] = []
    for a in addons:
        if a not in seen:
            seen.add(a)
            deduped_addons.append(a)

    # keep why unique but ordered
    seen_w: set = set()
    deduped_why: List[str] = []
    for w in why:
        if w not in seen_w:
            seen_w.add(w)
            deduped_why.append(w)

    return deduped_addons, deduped_why, debug


# =============================================================================
# Public APIs
# =============================================================================

def build_answer_addons(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> str:
    """
    Returns a single string with optional add-on content.

    If no add-ons match, returns "".
    """
    addons, _why, _debug = _collect_addons_and_reasons(question, calc_context, style)
    return _bullets(addons) if addons else ""


def build_answer_addons_structured(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> Dict[str, Any]:
    """
    Returns:
      {
        "text": "...",          # bullet string
        "addons": [...],
        "why_added": [...],
        "debug": {...}
      }
    """
    addons, why_added, debug = _collect_addons_and_reasons(question, calc_context, style)
    return {
        "text": _bullets(addons) if addons else "",
        "addons": addons,
        "why_added": why_added,
        "debug": debug,
    }


def build_layered_answer_structured(
    question: Dict[str, Any],
    base: str,
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> Dict[str, Any]:
    """
    Returns the LLM-friendly payload you requested:

    {
      "base": "...",
      "addons": ["...", "..."],
      "why_added": ["CAD active", "trust -1", "cvd_10yr > 7.5%"],
      "final": "base\\n\\n- addon...\\n- addon..."
    }
    """
    base_s = _safe_strip(base)
    addons, why_added, _debug = _collect_addons_and_reasons(question, calc_context, style)
    addon_text = _bullets(addons) if addons else ""
    final = (base_s + "\n\n" + addon_text).strip() if addon_text else base_s

    return {
        "base": base_s,
        "addons": addons,
        "why_added": why_added,
        "final": final,
    }
