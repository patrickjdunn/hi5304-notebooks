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
- Never break existing behavior: if no layers match, return "" (for text) and empty lists (for structured).
- Keep add-ons short and "non-disruptive" (1–3 bullets or 1 short paragraph).
- Avoid changing base answers. We only append add-ons.

Usage (in signatures_engine.py)
-------------------------------
# Text:
addon_text = build_answer_addons_text(q, calc_context=calc, style=style_key)
final_text = base if not addon_text else f"{base}\n\n{addon_text}"

# Structured (LLM-friendly):
payload = build_layered_answer_structured(q, base=base, calc_context=calc, style=style_key)
print(payload["final"])
# payload contains: {"base","addons","why_added","final"}
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


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _normalize_persona(persona: str) -> str:
    """
    Normalizes persona keys to the form used in questions.py responses:
      listener / motivator / director / expert
    """
    p = _safe_strip(persona).lower()
    mapping = {
        "Listener": "listener",
        "Motivator": "motivator",
        "Director": "director",
        "Expert": "expert",
    }
    # if caller passes already-lowercase persona, keep it
    return mapping.get(persona, p)


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
    # fallback: non-empty string -> assume selected
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
                continue
        return out
    return {}


def _bullets(items: List[str]) -> str:
    items2 = [f"- {_safe_strip(x)}" for x in items if _safe_strip(x)]
    return "\n".join(items2)


# -----------------------------
# Layer catalogs
# -----------------------------
CONDITION_ADDONS: Dict[str, Dict[str, Any]] = {
    "CAD": {
        "title": "CAD considerations",
        "lines": [
            "If exertion brings chest pressure, unusual shortness of breath, or dizziness, stop and follow your symptom action plan.",
            "Ask your clinician what your LDL-C target is and how your current plan supports it (meds + lifestyle).",
        ],
    },
    "AF": {
        "title": "AFib considerations",
        "lines": [
            "Know your stroke warning signs (FAST) and your anticoagulation plan if prescribed.",
            "If you notice sustained palpitations with fainting, chest pain, or severe breathlessness, seek urgent care.",
        ],
    },
    "HF": {
        "title": "Heart failure considerations",
        "lines": [
            "Track daily weight and swelling if advised; rapid weight gain can signal fluid retention.",
            "If shortness of breath suddenly worsens, or you can’t lie flat, contact your care team promptly.",
        ],
    },
    "HTN": {
        "title": "Blood pressure considerations",
        "lines": [
            "Home BP technique matters: seated, rested 5 minutes, arm at heart level; take 2 readings and average.",
            "If readings are very high with symptoms (chest pain, severe headache, weakness, trouble speaking), seek urgent care.",
        ],
    },
    "DM": {
        "title": "Diabetes considerations",
        "lines": [
            "If you use insulin or meds that can cause lows, carry fast-acting carbs and know the 15–15 rule.",
            "Ask what your A1c target is and how often to recheck based on your regimen and risk.",
        ],
    },
    "CKMH": {
        "title": "Heart–kidney–metabolic considerations",
        "lines": [
            "These systems are connected—BP, glucose, kidney function, and lipids work together in risk reduction.",
            "Ask how your eGFR and UACR affect your medication choices and monitoring frequency.",
        ],
    },
    "ST": {
        "title": "Stroke/TIA considerations",
        "lines": [
            "If you have new one-sided weakness, facial droop, or speech trouble, treat it as an emergency (call 911).",
            "Secondary prevention often focuses on BP, cholesterol, diabetes, and rhythm (AFib) control—ask which apply to you.",
        ],
    },
    "CH": {
        "title": "Cholesterol treatment considerations",
        "lines": [
            "If you have muscle aches or concerns about statins, don’t stop abruptly—ask about dose adjustments or alternatives.",
            "Recheck your lipid panel on the schedule your clinician recommends to confirm you’re at goal.",
        ],
    },
}


ENGAGEMENT_ADDONS: Dict[str, Dict[int, List[str]]] = {
    "trust": {
        -1: [
            "If you’re unsure who to trust, we can stick to one or two well-known sources and confirm the plan with your clinician.",
            "It’s okay to ask: “What’s the benefit, what’s the downside, and what are my options?”",
        ],
        1: [
            "Since you’re engaged with your care, consider bringing your tracked data (BP, steps, symptoms) to tighten the plan together.",
        ],
    },
    "health_literacy": {
        -1: [
            "Here’s the short version: pick 1 change this week, track it for 7 days, and bring the results to your next visit.",
            "If any terms feel unclear, ask for plain-language explanations—good care should be understandable.",
        ],
        1: [
            "If you like details, ask for your exact targets (BP, LDL, A1c) and how your numbers are trending over time.",
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
    "selfefficacy": {
        -1: [
            "Let’s make this easier: define a 5-minute starter step you can succeed with, then build from wins.",
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
            "You’re being proactive—consider a weekly ‘health planning’ time to review meds, activity, and symptoms.",
        ],
    },
    "goal_orientation": {
        -1: [
            "Try one SMART goal: specific, measurable, achievable, relevant, time-bound (example: walk 10 minutes after dinner 5 days this week).",
        ],
        1: [
            "Pick a measurable target for the next 7 days and track it daily (minutes, steps, BP, or sleep).",
        ],
    },
    "independence": {
        -1: [
            "If you rely on others, choose one support person and give them a clear role (reminders, walks, meal planning).",
        ],
        1: [
            "Since you prefer autonomy, use a simple self-tracking tool and bring the summary to visits.",
        ],
    },
    "decision_style": {
        -1: [
            "If decisions feel stressful, ask your clinician for 2–3 options and a recommendation, then take 24 hours to decide if needed.",
        ],
        1: [
            "Since you like exploring options, ask: “What are the alternatives and what evidence supports each?”",
        ],
    },
    "food_insecurity": {
        -1: [
            "If cost or access is a barrier, ask about budget-friendly heart-healthy staples (beans, frozen vegetables, oats) and local support resources.",
        ],
        1: [
            "If access is good, plan one grocery swap this week that supports your goal (lower sodium, higher fiber).",
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


# If True, condition add-ons only apply when the question's condition_modifiers include that condition.
# If False, any active condition can add its lines (still intended to be short/safe).
REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS = False


# -----------------------------
# Internal collector (source of truth)
# -----------------------------
def _collect_addons_and_reasons(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]],
) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """
    Returns:
      addons: [line1, line2, ...]           (flat list of bullet lines)
      why_added: ["CAD active", "trust -1", ...]
      debug: { ... }                        (safe debug info)
    """
    if not isinstance(question, dict):
        return [], [], {"error": "question not dict"}

    calc_context = calc_context if isinstance(calc_context, dict) else {}

    calc_conditions = _get_calc_block(calc_context, "condition_modifiers")
    calc_drivers = _get_calc_block(calc_context, "engagement_drivers")

    q_condition_tags = set(_get_question_condition_tags(question))

    addons: List[str] = []
    why: List[str] = []

    # Active conditions
    active_conditions: List[str] = []
    for code, raw in calc_conditions.items():
        code_u = str(code).strip().upper()
        if not code_u:
            continue
        if _is_selected(raw):
            active_conditions.append(code_u)

    # Condition lines
    for cond in active_conditions:
        if cond not in CONDITION_ADDONS:
            continue

        if REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS:
            if q_condition_tags and (cond not in q_condition_tags):
                continue

        payload = CONDITION_ADDONS.get(cond, {})
        lines = payload.get("lines", [])
        if isinstance(lines, list):
            for line in lines:
                line_s = _safe_strip(line)
                if line_s:
                    addons.append(line_s)
        why.append(f"{cond} active")

    # Engagement driver lines
    matched_drivers: Dict[str, int] = {}
    for driver_key, variants in ENGAGEMENT_ADDONS.items():
        if driver_key not in calc_drivers:
            continue
        try:
            val = int(calc_drivers.get(driver_key))
        except Exception:
            continue
        if val not in (-1, 0, 1) or val == 0:
            continue

        matched_drivers[driver_key] = val

        for line in variants.get(val, []):
            line_s = _safe_strip(line)
            if line_s:
                addons.append(line_s)
        why.append(f"{driver_key} {val}")

    debug = {
        "active_conditions": active_conditions,
        "question_condition_tags": sorted(list(q_condition_tags)),
        "matched_drivers": matched_drivers,
    }
    return addons, why, debug


# -----------------------------
# Public API (LLM-friendly structured)
# -----------------------------
def build_answer_addons_structured(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> Dict[str, Any]:
    """
    Returns:
      {
        "text": "- ...\\n- ...",     # bullet text block (or "")
        "addons": [...],            # list of addon lines
        "why_added": [...],         # list of reasons
        "debug": {...}              # safe debugging info
      }
    """
    _ = _normalize_persona(style)  # currently unused, but kept for future persona-specific rules
    addons, why_added, debug = _collect_addons_and_reasons(question, calc_context)
    text = _bullets(addons).strip() if addons else ""
    return {
        "text": text,
        "addons": addons,
        "why_added": why_added,
        "debug": debug,
    }


def build_answer_addons_text(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> str:
    """
    Backward-compatible: returns ONLY the add-on text block (or "").
    """
    payload = build_answer_addons_structured(question, calc_context=calc_context, style=style)
    return _safe_strip(payload.get("text", ""))


def build_layered_answer_structured(
    question: Dict[str, Any],
    base: str,
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> Dict[str, Any]:
    """
    Returns exactly the payload you asked for:

    {
      "base": "...",
      "addons": ["...", "..."],
      "why_added": ["CAD active", "trust -1"],
      "final": "base\\n\\n- addon...\\n- addon..."
    }
    """
    base_s = _safe_strip(base)
    payload = build_answer_addons_structured(question, calc_context=calc_context, style=style)

    addons = payload.get("addons", []) if isinstance(payload, dict) else []
    why_added = payload.get("why_added", []) if isinstance(payload, dict) else []

    addon_text = _bullets(addons).strip() if addons else ""
    final = (base_s + "\n\n" + addon_text).strip() if addon_text else base_s

    return {
        "base": base_s,
        "addons": addons,
        "why_added": why_added,
        "final": final,
    }


# -----------------------------
# Engine-facing wrapper (optional, but matches your signatures_engine usage)
# -----------------------------
def _apply_answer_layers(
    base_text: str,
    question_payload: Dict[str, Any],
    persona: str,
    calc_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (final_text, layer_meta) where layer_meta is ALWAYS:
      { "base": str, "addons": [str], "why_added": [str] }
    """
    base = _safe_strip(base_text)

    try:
        payload = build_layered_answer_structured(
            question=question_payload,
            base=base,
            calc_context=calc_context,
            style=persona,
        )
    except Exception:
        payload = {"base": base, "addons": [], "why_added": [], "final": base}

    final = _safe_strip(payload.get("final", base))

    layer_meta = {
        "base": _safe_strip(payload.get("base", base)),
        "addons": payload.get("addons", []) if isinstance(payload.get("addons", []), list) else [],
        "why_added": payload.get("why_added", []) if isinstance(payload.get("why_added", []), list) else [],
    }
    return final, layer_meta
