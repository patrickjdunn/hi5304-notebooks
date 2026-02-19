# answer_Layers.py
"""
Answer Layers for Signatures
============================

Goal
----
Keep `questions.py` as the stable base content, and optionally append short,
low-risk "add-on" snippets based on the calculator context (combined_calculator RESULTS).

Inputs this module expects (best-effort; all optional):
- calc_context["condition_modifiers"] : dict of flags (e.g., {"CAD": "Yes", "HF": False, ...})
- calc_context["engagement_drivers"]  : dict of -1/0/+1 (e.g., {"trust": -1, "selfefficacy": 1, ...})
- calc_context["prevent"]             : dict of PREVENT risks (e.g., {"cvd_10yr": 0.08, ...})
- calc_context["scores"]              : dict of other scores (optional)

Public API (engine-safe)
------------------------
- build_answer_addons(question, calc_context, style) -> str
- build_answer_addons_structured(question, calc_context, style) -> dict
- build_layered_answer_structured(question, base, calc_context, style) -> dict
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Safe helpers
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
    # fallback: any non-empty string counts as selected
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
        return [str(x).strip().upper() for x in mods if _safe_strip(x)]
    return []


def _bullets(items: List[str]) -> str:
    items2 = [f"- {_safe_strip(x)}" for x in items if _safe_strip(x)]
    return "\n".join(items2)


def _get_prevent_block(calc_context: Dict[str, Any]) -> Dict[str, Any]:
    # Prefer calc_context["prevent"]; fall back to calc_context["scores"]["prevent_results"] etc if you later add.
    prevent = (calc_context or {}).get("prevent")
    return prevent if isinstance(prevent, dict) else {}


def _coerce_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = _safe_strip(x)
        if not s:
            return None
        # handle percent strings like "7.5%"
        if s.endswith("%"):
            return float(s[:-1].strip()) / 100.0
        return float(s)
    except Exception:
        return None


# -----------------------------
# Add-on catalogs (single-condition, single-driver)
# -----------------------------
CONDITION_ADDONS: Dict[str, Dict[str, Any]] = {
    "CAD": {

        "lines": [
            "If exertion brings chest pressure, unusual shortness of breath, or dizziness, stop and follow your symptom action plan.",
            "Ask your clinician what your LDL-C target is and how your current plan supports it (meds + lifestyle).",
        ],
    },
    "AF": {

        "lines": [
            "Know your stroke warning signs (FAST) and your anticoagulation plan if prescribed.",
            "If you notice sustained palpitations with fainting, chest pain, or severe breathlessness, seek urgent care.",
        ],
    },
    "HF": {

        "lines": [
            "Track daily weight and swelling if advised; rapid weight gain can signal fluid retention.",
            "If shortness of breath suddenly worsens, or you can’t lie flat, contact your care team promptly.",
            "Ask your clinician what sodium and fluid targets apply to you—heart failure plans are individualized.",
        ],
    },
    "HTN": {

        "lines": [
            "Home BP technique matters: seated, rested 5 minutes, arm at heart level; take 2 readings and average.",
            "If readings are very high with symptoms (chest pain, severe headache, weakness, trouble speaking), seek urgent care.",
        ],
    },
    "DM": {

        "lines": [
            "If you use insulin or meds that can cause lows, carry fast-acting carbs and know the 15–15 rule.",
            "Ask what your A1c target is and how often to recheck based on your regimen and risk.",
        ],
    },
    "CKMH": {

        "lines": [
            "These systems are connected—BP, glucose, kidney function, and lipids work together in risk reduction.",
            "Ask how your eGFR and UACR affect your medication choices and monitoring frequency.",
        ],
    },
    "ST": {

        "lines": [
            "Treat new one-sided weakness, facial droop, or speech trouble as an emergency (call 911).",
            "Secondary prevention often focuses on BP, cholesterol, diabetes, and rhythm (AFib) control—ask which apply to you.",
        ],
    },
    "CH": {

        "lines": [
            "If you have muscle aches or concerns about statins, don’t stop abruptly—ask about dose adjustments or alternatives.",
            "Recheck your lipid panel on the schedule your clinician recommends to confirm you’re at goal.",
        ],
    },
}


ENGAGEMENT_ADDONS: Dict[str, Dict[int, List[str]]] = {
    "trust": {
        -1: [
            "If trust feels low right now, it’s okay to ask for simpler explanations and a clear next step—your questions are valid.",
            "Try: “What’s the benefit, what’s the downside, and what are my options?”",
        ],
        1: [
            "Since you’re engaged with your care, consider bringing tracked data (BP, steps, symptoms) to refine the plan together.",
        ],
    },
    "health_literacy": {
        -1: [
            "Here’s the short version: pick 1 change this week, track it for 7 days, and bring the results to your next visit.",
        ],
        1: [
            "If you like details, ask for exact targets (BP, LDL, A1c) and how your numbers are trending over time.",
        ],
    },
    "readiness_for_change": {
        -1: [
            "No pressure to change everything today—choose the smallest step that feels realistic and start there.",
        ],
        1: [
            "Since you feel ready, pick one “next-step” goal and set a check-in date to review progress.",
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
}

# If True, condition add-ons only apply when the question tags include that condition.
REQUIRE_QUESTION_RELEVANCE_FOR_CONDITION_ADDONS = False


# -----------------------------
# Conflict resolution (cross-condition)
# -----------------------------
def _apply_conflict_resolution(
    addons: List[str],
    why_added: List[str],
    active_conditions: List[str],
    prevent: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    """
    Resolves cross-condition conflicts by:
      1) removing/avoiding duplicates
      2) replacing generic guidance with combined guidance

    Implemented combos:
      - HF + CKMH + HTN: BP targets + diuretics + sodium
      - DM + CKMH: A1c targets + hypoglycemia risk + kidney meds
      - AF + ST: anticoagulation emphasis + FAST
    """
    active = set([c.strip().upper() for c in (active_conditions or []) if _safe_strip(c)])

    # Deduplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for line in addons:
        line_s = _safe_strip(line)
        if not line_s:
            continue
        key = line_s.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line_s)
    addons = deduped

    def _remove_if_contains(substrs: List[str]) -> None:
        nonlocal addons
        subs = [s.lower() for s in substrs if _safe_strip(s)]
        if not subs:
            return
        addons = [a for a in addons if all(s not in a.lower() for s in subs)]

    # -----------------------------
    # HF + CKMH + HTN
    # -----------------------------
    if {"HF", "CKMH", "HTN"}.issubset(active):
        # remove any prior sodium/BP-target fragments to avoid contradictions
        _remove_if_contains(["sodium", "fluid", "bp", "blood pressure goal", "target bp", "diuretic"])

        addons.insert(
            0,
            "Because HF + CKM + HTN overlap, your BP goal, diuretic plan, and sodium/fluid targets should be set together by your clinician. A common BP target is <130/80 if tolerated, but kidney function, symptoms (dizziness), and meds can change the best target for you.",
        )
        addons.insert(
            1,
            "If you’re on diuretics, ask what weight change or symptoms should trigger a call (and when NOT to change doses on your own).",
        )
        addons.insert(
            2,
            "For sodium: ask for a specific daily target (often in the 1,500–2,000 mg/day range for HF), and confirm what applies to you given CKM stage and BP control.",
        )
        why_added.append("HF+CKMH+HTN conflict-resolved")

    # -----------------------------
    # DM + CKMH
    # -----------------------------
    if {"DM", "CKMH"}.issubset(active):
        _remove_if_contains(["a1c", "hypogly", "kidney", "egfr", "uacr", "sglt", "glp"])

        addons.insert(
            0,
            "Because diabetes + CKM overlap, A1c targets should be individualized (age, kidney function, meds, hypoglycemia risk). Ask your clinician what target is safest for you.",
        )
        addons.insert(
            1,
            "If you’ve had low blood sugar or you’re on insulin/sulfonylureas, confirm a ‘low glucose plan’ and what to do during illness or reduced eating.",
        )
        addons.insert(
            2,
            "Ask whether kidney-protective diabetes meds (when appropriate) are part of your plan, and what monitoring (eGFR/UACR) you need.",
        )
        why_added.append("DM+CKMH conflict-resolved")

    # -----------------------------
    # AF + ST
    # -----------------------------
    if {"AF", "ST"}.issubset(active):
        _remove_if_contains(["fast", "anticoag", "blood thinner", "stroke warning"])

        addons.insert(
            0,
            "Because AFib + prior stroke/TIA overlap, stroke prevention is a top priority—ask how your stroke-risk score guides anticoagulation (blood thinners) and what bleeding precautions apply.",
        )
        addons.insert(
            1,
            "Review FAST (Face droop, Arm weakness, Speech difficulty, Time to call 911) and keep an emergency plan visible at home.",
        )
        why_added.append("AF+ST conflict-resolved")

    # -----------------------------
    # Risk-tier triggered layer: 10yr CVD > 7.5%
    # -----------------------------
    cvd10 = _coerce_float(prevent.get("cvd_10yr")) if isinstance(prevent, dict) else None
    if isinstance(cvd10, float) and cvd10 > 0.075:
        # keep it short and non-prescriptive
        addons.append(
            "Your 10-year CVD risk is above 7.5%. Ask about intensifying prevention: BP/lipids/smoking (if relevant), and whether medication changes (e.g., statin intensity) are appropriate for your situation."
        )
        why_added.append("10yr CVD risk >7.5%")

    # Final dedupe again (conflict inserts may reintroduce overlaps)
    seen = set()
    out: List[str] = []
    for line in addons:
        key = _safe_strip(line).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(_safe_strip(line))
    addons = out

    # Deduplicate why_added
    why_seen = set()
    why_out: List[str] = []
    for w in why_added:
        ws = _safe_strip(w)
        if not ws:
            continue
        if ws in why_seen:
            continue
        why_seen.add(ws)
        why_out.append(ws)
    why_added = why_out

    return addons, why_added


# -----------------------------
# Collector
# -----------------------------
def _collect_addons_and_reasons(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]],
    style: str,
) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """
    Returns:
      addons: [line1, line2, ...]
      why_added: ["CAD active", "trust -1", ...]
      debug: { ... }  (safe debug info)
    """

    question = question if isinstance(question, dict) else {}
    calc_context = calc_context if isinstance(calc_context, dict) else {}


    calc_conditions = _get_calc_block(calc_context, "condition_modifiers")
    calc_drivers = _get_calc_block(calc_context, "engagement_drivers")
    prevent = _get_prevent_block(calc_context)

    q_condition_tags = set(_get_question_condition_tags(question))

    addons: List[str] = []
    why: List[str] = []

    # Active conditions (from calculator)
    active_conditions: List[str] = []
    if isinstance(calc_conditions, dict):
        for code, raw in calc_conditions.items():
            code_u = _safe_strip(code).upper()
            if not code_u:
                continue
            if _is_selected(raw):
                active_conditions.append(code_u)

    # Condition add-ons
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
                s = _safe_strip(line)
                if s:
                    addons.append(s)
            why.append(f"{cond} active")

    # Engagement driver add-ons
    matched_drivers: Dict[str, int] = {}
    if isinstance(calc_drivers, dict):
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
                s = _safe_strip(line)
                if s:
                    addons.append(s)
            why.append(f"{driver_key} {val}")

    # Cross-condition conflict resolution + risk trigger
    addons, why = _apply_conflict_resolution(
        addons=addons,
        why_added=why,
        active_conditions=active_conditions,
        prevent=prevent,
    )

    debug = {
        "active_conditions": active_conditions,
        "question_condition_tags": sorted(list(q_condition_tags)),
        "matched_drivers": matched_drivers,
        "prevent_keys": sorted(list(prevent.keys())) if isinstance(prevent, dict) else [],
    }
    return addons, why, debug


# -----------------------------
# Public API
# -----------------------------
def build_answer_addons(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> str:
    """Return a single string with optional add-on content; or "" if none."""
    addons, _why, _debug = _collect_addons_and_reasons(question, calc_context, style)
    return _bullets(addons).strip() if addons else ""


def build_answer_addons_structured(
    question: Dict[str, Any],
    calc_context: Optional[Dict[str, Any]] = None,
    style: str = "listener",
) -> Dict[str, Any]:
    """
    Returns:
      {
        "text": "- ...\n- ...",
        "addons": [...],
        "why_added": [...],
        "debug": {...}
      }
    """
    addons, why_added, debug = _collect_addons_and_reasons(question, calc_context, style)
    return {
        "text": _bullets(addons).strip() if addons else "",
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
    Returns an LLM-friendly payload:

    {
      "base": "...",
      "addons": ["...", "..."],
      "why_added": ["CAD active", "trust -1"],
      "final": "base\n\n- addon...\n- addon..."
    }
    """
    base_s = _safe_strip(base)
    pkg = build_answer_addons_structured(question, calc_context, style)
    addon_text = _safe_strip(pkg.get("text", ""))
    final = (base_s + "\n\n" + addon_text).strip() if addon_text else base_s

    return {
        "base": base_s,
        "addons": pkg.get("addons", []),
        "why_added": pkg.get("why_added", []),
        "final": final,
    }
