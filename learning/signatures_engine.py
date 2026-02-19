#!/usr/bin/env python3


from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from answer_Layers import build_answer_addons_structured

# -----------------------------
# Demo presets (CLI)
# -----------------------------
DEMO_PRESETS = {
    # Risk-tier trigger demo: 10-yr CVD risk > 7.5%
    "risk": {
        "prevent": {
            "cvd_10yr": 0.102,
            "ascvd_10yr": 0.081,
            "hf_10yr": 0.030,
            "cvd_30yr": 0.280,
            "ascvd_30yr": 0.210,
            "hf_30yr": 0.120,
        },
        "condition_modifiers": {"CAD": "Yes"},
        "engagement_drivers": {"selfefficacy": 1, "proactiveness": 1, "trust": 0},
    },

    # Conflict demo: HF + CKMH + HTN
    "hf_ckmh_htn": {
        "condition_modifiers": {"HF": "Yes", "CKMH": "Yes", "HTN": "Yes"},
        "prevent": {"cvd_10yr": 0.052},
        "engagement_drivers": {"trust": 0},
    },

    # Conflict demo: DM + CKMH
    "dm_ckmh": {
        "condition_modifiers": {"DM": "Yes", "CKMH": "Yes"},
        "prevent": {"cvd_10yr": 0.061},
        "engagement_drivers": {"trust": 0},
        "inputs": {"A1c": 8.4, "egfr": 42, "uacr": 220},  # optional: makes the story obvious
    },

    # Conflict demo: AF + ST
    "af_st": {
        "condition_modifiers": {"AF": "Yes", "ST": "Yes"},
        "prevent": {"cvd_10yr": 0.061},
        "engagement_drivers": {"trust": -1},
    },
}



CALC_CONTEXT: Dict[str, Any] = {}

# -----------------------------
# Imports from questions.py
# -----------------------------
try:
    from questions import QUESTION_BANK, PERSONAS, validate_question_bank  # required
except Exception as e:
    print("ERROR: Unable to import QUESTION_BANK / PERSONAS / validate_question_bank from questions.py.")
    print("Details:", e)
    sys.exit(1)

# Optional helpers (we provide fallbacks if missing)
try:
    from questions import all_categories  # type: ignore
except Exception:
    all_categories = None  # type: ignore

try:
    from questions import list_categories  # type: ignore
except Exception:
    list_categories = None  # type: ignore

try:
    from questions import list_question_summaries  # type: ignore
except Exception:
    list_question_summaries = None  # type: ignore

try:
    from questions import get_question_by_id  # type: ignore
except Exception:
    get_question_by_id = None  # type: ignore

try:
    from questions import search_questions  # type: ignore
except Exception:
    search_questions = None  # type: ignore

# --- Optional: answer layering (condition modifiers + engagement drivers) ---
try:
    # Expected in answer_layers.py (user module)
    # build_answer_addons(question_dict, calc_context, style) -> str | dict | tuple
    from answer_layers import build_answer_addons  # type: ignore
    ANSWER_LAYERS_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    build_answer_addons = None  # type: ignore
    ANSWER_LAYERS_AVAILABLE = False
    ANSWER_LAYERS_IMPORT_ERROR = str(_e)


# -----------------------------
# Optional combined_calculator import
# -----------------------------
CALCULATOR_AVAILABLE = False
calculator = None
CALCULATOR_IMPORT_ERROR = None

try:
    import combined_calculator  # type: ignore

    calculator = combined_calculator  # type: ignore
    CALCULATOR_AVAILABLE = True
except Exception as e:
    CALCULATOR_IMPORT_ERROR = e
    CALCULATOR_AVAILABLE = False


# -----------------------------
# Data structures
# -----------------------------
PersonaKey = str
QuestionId = str


@dataclass
class PickedQuestion:
    qid: QuestionId
    category: str
    question: str
    payload: Dict[str, Any]


# -----------------------------
# Small utilities
# -----------------------------
def _safe_strip(s: Any) -> str:
    return str(s).strip() if s is not None else ""


def _normalize_persona_choice(choice: str) -> PersonaKey:
    """
    Map numeric input or text to a persona key used in the bank.
    Expected keys in PERSONAS: e.g., ["listener","motivator","director","expert"]
    """
    choice = _safe_strip(choice).lower()

    # Numeric mapping (1-4)
    if choice in {"1", "2", "3", "4"}:
        idx = int(choice) - 1
        if 0 <= idx < len(PERSONAS):
            return PERSONAS[idx]

    # Text mapping
    for p in PERSONAS:
        if choice == p.lower():
            return p

    # Default
    return PERSONAS[0] if PERSONAS else "listener"


def _clamp_engagement_value(v: Any) -> int:
    """
    Engagement drivers use -1 / 0 / +1.
    """
    try:
        iv = int(v)
    except Exception:
        return 0
    if iv < -1:
        return -1
    if iv > 1:
        return 1
    return iv


def _print_hr():
    print("-" * 72)


def _title(s: str):
    print(f"\n{s}\n" + ("=" * len(s)))


def _bullet_list(items: List[str], empty_text: str = "(none)"):
    if not items:
        print(empty_text)
        return
    for it in items:
        it = _safe_strip(it)
        if it:
            print(f"- {it}")


def _format_link(url: str) -> str:
    url = _safe_strip(url)
    return url if url else ""


def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i) for i in x if _safe_strip(i)]
    if isinstance(x, str):
        s = x.strip()
        return [s] if s else []
    return [str(x)]


# -----------------------------
# Fallback helpers if questions.py lacks them
# -----------------------------
def _fallback_all_categories() -> List[str]:
    cats = set()
    for _, q in QUESTION_BANK.items():
        c = _safe_strip(q.get("category", "")).upper()
        if c:
            cats.add(c)
    return sorted(cats)


def _fallback_list_categories() -> List[str]:
    return _fallback_all_categories()


def _fallback_get_question_by_id(qid: str) -> Optional[Dict[str, Any]]:
    return QUESTION_BANK.get(qid)


def _fallback_list_question_summaries(category_filter: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Returns list of dicts: {id, category, question}
    """
    out: List[Dict[str, str]] = []
    cf = _safe_strip(category_filter).upper()
    for qid, q in QUESTION_BANK.items():
        cat = _safe_strip(q.get("category", "")).upper()
        if cf and cat != cf:
            continue
        out.append(
            {
                "id": qid,
                "category": cat,
                "question": _safe_strip(q.get("question", "")),
            }
        )
    # stable sort by category then id
    out.sort(key=lambda d: (d.get("category", ""), d.get("id", "")))
    return out


def _fallback_search_questions(query: str, category_filter: Optional[str] = None, limit: int = 25) -> List[Dict[str, str]]:
    """
    Simple keyword search in question text + persona responses.
    Returns list of summaries: {id, category, question}
    """
    q = _safe_strip(query).lower()
    cf = _safe_strip(category_filter).upper()
    if not q:
        return []

    hits: List[Tuple[int, Dict[str, str]]] = []
    for qid, item in QUESTION_BANK.items():
        cat = _safe_strip(item.get("category", "")).upper()
        if cf and cat != cf:
            continue

        text_parts = [_safe_strip(item.get("question", ""))]
        responses = item.get("responses", {})
        if isinstance(responses, dict):
            for p in PERSONAS:
                text_parts.append(_safe_strip(responses.get(p, "")))

        hay = " ".join(text_parts).lower()

        if q in hay:
            score = hay.count(q)
            hits.append(
                (
                    score,
                    {"id": qid, "category": cat, "question": _safe_strip(item.get("question", ""))},
                )
            )

    hits.sort(key=lambda t: (-t[0], t[1]["category"], t[1]["id"]))
    return [h[1] for h in hits[:limit]]


def all_categories_safe() -> List[str]:
    if callable(all_categories):
        try:
            return list(all_categories())  # type: ignore
        except Exception:
            return _fallback_all_categories()
    return _fallback_all_categories()


def list_categories_safe() -> List[str]:
    if callable(list_categories):
        try:
            return list(list_categories())  # type: ignore
        except Exception:
            return _fallback_list_categories()
    return _fallback_list_categories()


def list_question_summaries_safe(category_filter: Optional[str] = None) -> List[Dict[str, str]]:
    if callable(list_question_summaries):
        try:
            return list(list_question_summaries(category_filter=category_filter))  # type: ignore
        except Exception:
            return _fallback_list_question_summaries(category_filter=category_filter)
    return _fallback_list_question_summaries(category_filter=category_filter)


def get_question_by_id_safe(qid: str) -> Optional[Dict[str, Any]]:
    if callable(get_question_by_id):
        try:
            return get_question_by_id(qid)  # type: ignore
        except Exception:
            return _fallback_get_question_by_id(qid)
    return _fallback_get_question_by_id(qid)


def search_questions_safe(query: str, category_filter: Optional[str] = None, limit: int = 25) -> List[Dict[str, str]]:
    if callable(search_questions):
        try:
            return list(search_questions(query=query, category_filter=category_filter, limit=limit))  # type: ignore
        except Exception:
            return _fallback_search_questions(query=query, category_filter=category_filter, limit=limit)
    return _fallback_search_questions(query=query, category_filter=category_filter, limit=limit)


# -----------------------------
# Calculator integration (MyLifeCheck + PREVENT)
# -----------------------------
def try_get_calculator_results() -> Dict[str, Any]:
    """
    Pulls results from combined_calculator.py in a flexible way.
    We do NOT re-prompt here; we try to reuse what combined_calculator exposes.

    Supported patterns:
    - combined_calculator.get_results() -> dict
    - combined_calculator.run_all() -> dict
    - combined_calculator.calculate_all(inputs_dict) -> dict  (not used here)
    - combined_calculator.RESULTS global dict
    - combined_calculator.last_results global dict
    """
    if not CALCULATOR_AVAILABLE or calculator is None:
        return {}

    # Prefer a function call if present
    for fn_name in ("get_results", "run_all", "results", "compute_all"):
        fn = getattr(calculator, fn_name, None)
        if callable(fn):
            try:
                out = fn()
                if isinstance(out, dict):
                    return out
            except Exception:
                pass

    # Try globals
    for attr in ("RESULTS", "results", "last_results", "LAST_RESULTS"):
        val = getattr(calculator, attr, None)
        if isinstance(val, dict):
            return val

    return {}

from typing import Any, Dict, Optional, Tuple



def get_merged_calc_context() -> Dict[str, Any]:
    """Return calculator results merged with any local overrides (CALC_CONTEXT)."""
    base: Dict[str, Any] = {}
    if CALCULATOR_AVAILABLE:
        try:
            base = try_get_calculator_results() or {}
        except Exception:
            base = {}
    if not isinstance(base, dict):
        base = {}

    if isinstance(CALC_CONTEXT, dict) and CALC_CONTEXT:
        try:
            base = {**base, **CALC_CONTEXT}
        except Exception:
            pass
    return base

def extract_mylifecheck_prevent(calc: Dict[str, Any]) -> Tuple[Optional[Any], Optional[Any]]:
    """
    Best-effort extraction from calculator output dict.

    Expected current structure (based on your debug):
      calc = {
        "condition_modifiers": {...},
        "inputs": {...},
        "engagement_drivers": {...},
        "scores": {...},     # <-- MyLifeCheck / LE8 likely here
        "prevent": {...},    # <-- PREVENT likely here
      }
    """
    if not isinstance(calc, dict) or not calc:
        return None, None

    scores = calc.get("scores") if isinstance(calc.get("scores"), dict) else {}
    prevent_block = calc.get("prevent") if isinstance(calc.get("prevent"), dict) else {}

    # -----------------------------
    # MyLifeCheck / Life's Essential 8
    # -----------------------------
    mylife = None

    # 1) Nested blocks inside scores (preferred)
    for k in ("mylifecheck", "my_life_check", "life_essential_8", "le8", "lifes_essential_8"):
        if k in scores and scores.get(k) is not None:
            mylife = scores.get(k)
            break

    # 2) Flat-ish fields inside scores (what your project likely uses)
    if mylife is None:
        mlc = None
        for k in ("MLC_score", "mlc_score", "mylifecheck_score", "my_life_check_score"):
            if k in scores and scores.get(k) is not None:
                mlc = scores.get(k)
                break

        cvh = None
        for k in ("cardiovascular_health_status", "cvh_status", "CVH_status"):
            if k in scores and scores.get(k) is not None:
                cvh = scores.get(k)
                break

        assessments: Dict[str, Any] = {}
        for k, v in scores.items():
            if v is None:
                continue
            ks = str(k)
            if ks.lower().endswith("_assessment"):
                assessments[ks] = v

        if mlc is not None or cvh is not None or assessments:
            mylife = {}
            if mlc is not None:
                mylife["MLC_score"] = mlc
            if cvh is not None:
                mylife["CVH_status"] = cvh
            mylife.update(assessments)

    # 3) Legacy fallback (top-level keys)
    if mylife is None:
        mlc = None
        for k in ("MLC_score", "mlc_score"):
            if k in calc and calc.get(k) is not None:
                mlc = calc.get(k)
                break
        if mlc is not None:
            mylife = {"MLC_score": mlc}

    # -----------------------------
    # PREVENT
    # -----------------------------
    prevent = None

    # 1) Use nested prevent dict if present
    if prevent_block:
        prevent = prevent_block
    else:
        # 2) Legacy fallback: flat keys
        for k in ("last_risk_score", "risk_score", "PREVENT"):
            if k in calc and calc.get(k) is not None:
                prevent = {"last_risk_score": calc.get(k)}
                break

    return mylife, prevent


def _format_percent(value: Any, decimals: int = 2) -> str:
    """Format a 0–1 probability (or 0–100 percent) into a percent string."""
    try:
        x = float(value)
    except Exception:
        return _safe_strip(value)

    pct = x if x > 1.0 else x * 100.0
    return f"{pct:.{decimals}f}%"


def _mlc_tier(mlc_score: Any) -> str:
    """Lightweight CVH tier label for readability."""
    try:
        s = float(mlc_score)
    except Exception:
        return ""
    if s >= 80:
        return "High CVH"
    if s >= 50:
        return "Moderate CVH"
    return "Low CVH"


def _prevent_tier(risk: float, horizon: str = "10yr") -> str:
    """
    risk: probability 0–1
    horizon: "10yr" or "30yr"
    """
    try:
        r_pct = float(risk) * 100.0
    except Exception:
        return ""

    h = str(horizon).lower()

    # -------------------------
    # 10-year tiering (YOUR RULE)
    # -------------------------
    # High risk if >7.5%
    if "10" in h:
        if r_pct < 5.0:
            return "Low"
        if r_pct <= 7.5:
            return "Borderline"
        return "High"

    # -------------------------
    # 30-year tiering (leave as-is unless you want different)
    # -------------------------
    if r_pct < 20.0:
        return "Low"
    if r_pct < 40.0:
        return "Moderate"
    return "High"


    
def _is_selected(v: Any) -> bool:
    """
    Returns True only when the value clearly represents an active/selected state.
    Handles Yes/No strings, booleans, and numeric flags safely.
    """
    if v is None:
        return False

    if isinstance(v, bool):
        return v

    if isinstance(v, (int, float)):
        return v != 0

    s = str(v).strip().lower()

    if s in ("yes", "y", "true", "t", "1", "on", "checked", "selected"):
        return True

    if s in ("no", "n", "false", "f", "0", "off", "unchecked", "", "none"):
        return False

    # Conservative default: treat unknown strings as NOT selected
    return False


def _pretty_calc_block(obj: Any) -> List[str]:
    """
    Render calculator result (dict/str/number) as bullet strings.
    """
    if obj is None:
        return []
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            ks = _safe_strip(k)
            vs = _safe_strip(v)
            if ks and vs:
                lines.append(f"{ks}: {vs}")
        return lines
    if isinstance(obj, (list, tuple)):
        return [f"{_safe_strip(x)}" for x in obj if _safe_strip(x)]
    s = _safe_strip(obj)
    return [s] if s else []


# -----------------------------
# Question picking (preloaded + search)
# -----------------------------
def prompt_category_filter() -> str:
    cats = list_categories_safe()
    if cats:
        print("\nAvailable categories:", ", ".join(cats))
    return _safe_strip(input("Optional: type a category to filter (or press Enter to show all): ")).upper()


def pick_preloaded_question() -> PickedQuestion:
    """
    Allows the user to select by ID OR by number. If they enter an invalid ID,
    we list valid IDs and let them retry without crashing.
    """
    category_filter = prompt_category_filter()

    items = list_question_summaries_safe(category_filter=category_filter)
    if not items and category_filter:
        print("⚠️ No questions found for that filter. Showing all.")
        items = list_question_summaries_safe(category_filter=None)

    if not items:
        raise RuntimeError("No questions available in QUESTION_BANK.")

    _title("Preloaded Questions")
    for i, it in enumerate(items, start=1):
        print(f"{i:>3}. [{it['category']}] {it['id']} — {it['question']}")

    while True:
        raw = _safe_strip(input("\nEnter question ID (e.g., CKM-01) OR number (e.g., 1): "))
        if not raw:
            print("Using first question.")
            chosen = items[0]
            break

        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(items):
                chosen = items[idx - 1]
                break
            print("⚠️ Number out of range. Try again.")
            continue

        # Treat as ID
        qid = raw.upper()
        match = next((it for it in items if it["id"].upper() == qid), None)
        if match:
            chosen = match
            break

        # Not found -> show top valid IDs in current list
        print("⚠️ Not found. Please enter a valid ID shown above (or a number).")
        sample_ids = ", ".join([it["id"] for it in items[:10]])
        print(f"Hint: valid IDs include: {sample_ids} ...")

    qid = chosen["id"]
    payload = get_question_by_id_safe(qid)
    if payload is None:
        raise RuntimeError(f"Selected question id {qid} not found in QUESTION_BANK (unexpected).")

    return PickedQuestion(
        qid=qid,
        category=_safe_strip(payload.get("category", chosen.get("category", ""))).upper(),
        question=_safe_strip(payload.get("question", chosen.get("question", ""))),
        payload=payload,
    )


def search_mode_pick_question() -> PickedQuestion:
    """
    Search by keyword, then pick by number or ID.
    """
    category_filter = prompt_category_filter()
    query = _safe_strip(input("Search keywords (e.g., 'salt', 'exercise', 'blood thinner'): "))
    results = search_questions_safe(query=query, category_filter=category_filter or None, limit=40)

    if not results and category_filter:
        print("⚠️ No matches in that category. Searching all categories.")
        results = search_questions_safe(query=query, category_filter=None, limit=40)

    if not results:
        print("⚠️ No matches found. Returning to preloaded list.")
        return pick_preloaded_question()

    _title("Search Results")
    for i, it in enumerate(results, start=1):
        print(f"{i:>3}. [{it['category']}] {it['id']} — {it['question']}")

    while True:
        raw = _safe_strip(input("\nPick by ID or number (Enter = 1): "))
        if not raw:
            chosen = results[0]
            break

        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(results):
                chosen = results[idx - 1]
                break
            print("⚠️ Number out of range.")
            continue

        qid = raw.upper()
        match = next((it for it in results if it["id"].upper() == qid), None)
        if match:
            chosen = match
            break

        print("⚠️ Not found. Try again.")

    qid = chosen["id"]
    payload = get_question_by_id_safe(qid)
    if payload is None:
        raise RuntimeError(f"Selected question id {qid} not found in QUESTION_BANK (unexpected).")

    return PickedQuestion(
        qid=qid,
        category=_safe_strip(payload.get("category", chosen.get("category", ""))).upper(),
        question=_safe_strip(payload.get("question", chosen.get("question", ""))),
        payload=payload,
    )


def choose_question() -> PickedQuestion:
    """
    Choose between custom question, preloaded pick, or search mode.
    """
    print("\nQuestion mode:")
    print("1. Preloaded question (pick from bank)")
    print("2. Search (keyword search in bank)")
    print("3. Custom question (type your own)")

    choice = _safe_strip(input("Enter 1-3 (default 1): "))
    if choice == "2":
        return search_mode_pick_question()
    if choice == "3":
        qtext = _safe_strip(input("Enter your question: "))
        # Represent custom question with a synthetic ID
        payload = {
            "id": "CUSTOM-01",
            "category": "CUSTOM",
            "question": qtext,
            "responses": {},
            "signatures": {},
            "security_rules": [],
            "action_plans": [],
            "sources": [],
        }
        return PickedQuestion(qid="CUSTOM-01", category="CUSTOM", question=qtext, payload=payload)

    return pick_preloaded_question()

def _get_calc_context_merged() -> Dict[str, Any]:
    """
    Safe calculator context fetch:
    - returns {} if calculator isn't available or has no results
    - merges CALC_CONTEXT on top (CALC_CONTEXT wins)
    """
    if not CALCULATOR_AVAILABLE:
        return {}

    calc = try_get_calculator_results()
    if not isinstance(calc, dict):
        calc = {}

    # Merge in local context (wins if keys overlap)
    if isinstance(CALC_CONTEXT, dict) and CALC_CONTEXT:
        calc = {**calc, **CALC_CONTEXT}

    return calc

# -----------------------------
# Signatures rendering
# -----------------------------

def render_signatures_sections(
    q: Dict[str, Any],
    calc_override: Optional[Dict[str, Any]] = None,
) -> None:
    _title("Signatures Structure")

    sig = q.get("signatures", {}) if isinstance(q, dict) else {}
    if not isinstance(sig, dict):
        sig = {}

    calc = calc_override if isinstance(calc_override, dict) else get_merged_calc_context()
    cm_calc = calc.get("condition_modifiers") if isinstance(calc, dict) else None
    ed_calc = calc.get("engagement_drivers") if isinstance(calc, dict) else None

    core = sig.get("behavioral_core", [])
    if not core:
        core = sig.get("behavioral_core_codes", [])
    core_list = [str(x).strip() for x in core] if isinstance(core, list) else []

    print("\nBehavioral Core:")
    if core_list:
        for c in core_list:
            if c:
                print(f"- {c}")
    else:
        print("(none)")

    q_mods = sig.get("condition_modifiers", [])
    q_mods_list = [str(x).strip().upper() for x in q_mods] if isinstance(q_mods, list) else []
    print("\nCondition Modifiers (from question bank):")
    if q_mods_list:
        for c in q_mods_list:
            if c:
                print(f"- {c}")
    else:
        print("(none)")

    print("\nCondition Modifiers (from calculator):")
    selected_cm: List[str] = []
    if isinstance(cm_calc, dict):
        for k, v in cm_calc.items():
            if _is_selected(v):
                kk = str(k).strip().upper()
                if kk:
                    selected_cm.append(kk)
    if selected_cm:
        for c in sorted(set(selected_cm)):
            print(f"- {c}")
    else:
        print("(none)")

    if isinstance(ed_calc, dict):
        plus = sorted([k for k, v in ed_calc.items() if isinstance(v, (int, float)) and v > 0])
        zero = sorted([k for k, v in ed_calc.items() if isinstance(v, (int, float)) and v == 0])
        neg = sorted([k for k, v in ed_calc.items() if isinstance(v, (int, float)) and v < 0])

        print("\nEngagement Drivers (+1 present) (from calculator):")
        if plus:
            for k in plus:
                print(f"- {k}")
        else:
            print("(none)")

        print("\nEngagement Drivers (0 unknown) (from calculator):")
        if zero:
            for k in zero:
                print(f"- {k}")
        else:
            print("(none)")

        print("\nEngagement Drivers (-1 not present) (from calculator):")
        if neg:
            for k in neg:
                print(f"- {k}")
        else:
            print("(none)")

    q_ed = sig.get("engagement_drivers", {})
    q_plus: List[str] = []
    q_zero: List[str] = []
    if isinstance(q_ed, dict):
        for k, v in q_ed.items():
            try:
                iv = int(v)
            except Exception:
                continue
            kk = str(k).strip()
            if not kk:
                continue
            if iv > 0:
                q_plus.append(kk)
            elif iv == 0:
                q_zero.append(kk)

    print("\nEngagement Drivers (+1 present) (from question bank):")
    if q_plus:
        for k in sorted(q_plus):
            print(f"- {k}")
    else:
        print("(none)")

    print("\nEngagement Drivers (0 unknown) (from question bank):")
    if q_zero:
        for k in sorted(q_zero):
            print(f"- {k}")
    else:
        print("(none)")

    rules = sig.get("security_rules", [])
    if isinstance(rules, list) and rules:
        print("\nSecurity Rules:")
        for r in rules:
            rr = _safe_strip(r)
            if rr:
                print(f"- {rr}")

    plans = sig.get("action_plans", [])
    if isinstance(plans, list) and plans:
        print("\nAction Plans:")
        for p in plans:
            pp = _safe_strip(p)
            if pp:
                print(f"- {pp}")

def render_sources(q: PickedQuestion):
    payload = q.payload
    sources = payload.get("sources", [])

    _title("Source")
    if not sources:
        print("(no source listed)")
        return

    # Allow sources to be a list of dicts or strings
    if isinstance(sources, list):
        for s in sources:
            if isinstance(s, dict):
                name = _safe_strip(s.get("name", "Source"))
                url = _format_link(s.get("url", ""))
                print(f"- {name}")
                if url:
                    print(f"  {url}")
            else:
                st = _safe_strip(s)
                if st:
                    print(f"- {st}")
    elif isinstance(sources, dict):
        name = _safe_strip(sources.get("name", "Source"))
        url = _format_link(sources.get("url", ""))
        print(f"- {name}")
        if url:
            print(f"  {url}")
    else:
        st = _safe_strip(sources)
        if st:
            print(f"- {st}")



def _apply_answer_layers(
    *,
    base_text: str,
    question_payload: Dict[str, Any],
    persona: PersonaKey,
    calc_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Combine a base response with optional answer-layer addons from answer_layers.py.

    Returns (final_text, meta_dict). meta_dict is shaped like:
      {"base": str, "addons": [str...], "why_added": [str...] }
    """
    if not ANSWER_LAYERS_AVAILABLE or build_answer_addons is None:
        return base_text, None

    try:
        res = build_answer_addons(question_payload, calc_context=calc_context or {}, style=persona)
    except Exception:
        # Never let addons break the core engine output.
        return base_text, None

    addon_text = ""
    meta: Optional[Dict[str, Any]] = None

    if isinstance(res, str):
        addon_text = res.strip()
    elif isinstance(res, dict):
        # Expected keys: base/addons/why_added (+ optional text/addon)
        meta = {
            "base": _safe_strip(res.get("base", base_text)),
            "addons": list(res.get("addons", []) or []),
            "why_added": list(res.get("why_added", []) or []),
        }
        # Prefer explicit combined text if provided
        if isinstance(res.get("text"), str):
            addon_text = res.get("text", "").strip()
        elif isinstance(res.get("addon"), str):
            addon_text = res.get("addon", "").strip()
        else:
            addon_text = "\n\n".join([_safe_strip(a) for a in meta["addons"] if _safe_strip(a)]).strip()
    elif isinstance(res, tuple) and len(res) >= 1:
        # Allow (addon_text,) or (addon_text, meta_dict)
        addon_text = _safe_strip(res[0])
        if len(res) > 1 and isinstance(res[1], dict):
            meta = res[1]
    else:
        addon_text = ""

    final = (base_text + "\n\n" + addon_text).strip() if addon_text else base_text

    # If meta wasn't provided, build a minimal one when we have addon text
    if meta is None and addon_text:
        meta = {"base": base_text, "addons": [addon_text], "why_added": []}

    return final, meta
def render_question_header(q: Any) -> None:
    """Print the selected question header once (before Inputs / Scoring / Answer).

    The selected question is often represented as a PickedQuestion wrapper
    (with a `.payload` dict). Accept either a PickedQuestion or a dict.
    """
    _title("Question")

    payload: Dict[str, Any]
    if isinstance(q, PickedQuestion):
        payload = q.payload
    elif isinstance(q, dict):
        payload = q
    else:
        payload = {}

    qid = payload.get("id", "UNKNOWN")
    category = payload.get("category", "GENERAL")
    question = payload.get("question", "(missing question)")
    print(f"[{category}] {qid}: {question}")


def render_persona_response(
    q: Dict[str, Any],
    style_key: str,
    persona: str,
    calc_override: Optional[Dict[str, Any]] = None,
    *,
    show_title: bool = True,
    show_question: bool = True,
) -> None:
    if show_title:
        _title("Answer")

    if show_question:
        qid = q.get("id", "UNKNOWN")
        category = q.get("category", "GENERAL")
        question = q.get("question", "(missing question)")
        print(f"Question [{category}] {qid}: {question}\n")

    responses = q.get("responses", {}) if isinstance(q, dict) else {}
    if not isinstance(responses, dict):
        responses = {}

    text = responses.get(style_key) or responses.get(persona) or ""

    if text:
        base = text
        calc = calc_override if isinstance(calc_override, dict) else get_merged_calc_context()

        final, layer_meta = _apply_answer_layers(
            base_text=base,
            question_payload=q,
            persona=persona,
            calc_context=calc if isinstance(calc, dict) else {},
        )
        print(final)

        if layer_meta:
            print("\nAnswer Layers")
            print("============")
            import json as _json
            print(_json.dumps(layer_meta, indent=2, ensure_ascii=False))
    else:
        print("(no persona response available yet for this question)")

    payload = q.get("signatures", {}) if isinstance(q, dict) else {}
    action_step = _safe_strip(payload.get("action_step", ""))
    why = _safe_strip(payload.get("why_it_matters", ""))

    if action_step or why:
        _print_hr()
        if action_step:
            print(f"Action Step: {action_step}")
        if why:
            print(f"Why it matters: {why}")

def render_input_values(calc_override: Optional[Dict[str, Any]] = None) -> None:
    """Print calculator input values (if available) above the Answer."""
    _title("Input Values")

    if not CALCULATOR_AVAILABLE and not isinstance(calc_override, dict):
        print("(calculator not available)")
        return

    calc = calc_override if isinstance(calc_override, dict) else get_merged_calc_context()

    inputs = calc.get("inputs") if isinstance(calc, dict) else None
    if not isinstance(inputs, dict) or not inputs:
        print("(none)")
        return

    preferred = [
        "total_cholesterol",
        "HDL_cholesterol",
        "LDL_cholesterol",
        "systolic_blood_pressure",
        "diastolic_blood_pressure",
        "fasting_blood_sugar",
        "A1c",
        "BMI",
        "uacr",
        "egfr",
        "tobacco_use",
        "sleep_hours",
        "moderate_intensity",
        "vigorous_intensity",
    ]

    for k in preferred:
        if k in inputs:
            v = inputs.get(k)
            if isinstance(v, float):
                if k in ("A1c", "BMI"):
                    print(f"- {k}: {v:.2f}")
                else:
                    print(f"- {k}: {v}")
            else:
                print(f"- {k}: {_safe_strip(v)}")

    extras = [k for k in inputs.keys() if k not in preferred]
    for k in sorted(extras):
        print(f"- {k}: {_safe_strip(inputs.get(k))}")

def render_scoring_hooks(calc_override: Optional[Dict[str, Any]] = None) -> None:
    _title("Scoring Hooks (MyLifeCheck + PREVENT)")

    if not CALCULATOR_AVAILABLE and not isinstance(calc_override, dict):
        print("combined_calculator.py not available.")
        if CALCULATOR_IMPORT_ERROR:
            print("Import error:", CALCULATOR_IMPORT_ERROR)
        print("(You can still use Signatures without scoring.)")
        return

    calc = calc_override if isinstance(calc_override, dict) else get_merged_calc_context()

    mylife, prevent = extract_mylifecheck_prevent(calc)

    print("\nMyLifeCheck / Life's Essential 8:")
    if isinstance(mylife, dict) and isinstance(mylife.get("MLC_score"), (int, float)):
        mlc = float(mylife["MLC_score"])
        tier = _mlc_tier(mlc)
        tier_suffix = f" ({tier})" if tier else ""
        print(f"- MLC_score: {mlc:.2f}{tier_suffix}")
        rest = {k: v for k, v in mylife.items() if k != "MLC_score"}
        if rest:
            _bullet_list(_pretty_calc_block(rest))
    else:
        _bullet_list(_pretty_calc_block(mylife))

    print("\nPREVENT Risk:")
    if isinstance(prevent, dict) and prevent:
        items = list(prevent.items())

        def _sort_key(item: Tuple[str, Any]) -> Tuple[int, str]:
            k = str(item[0]).lower()
            if "10" in k and "yr" in k:
                return (0, k)
            if "30" in k and "yr" in k:
                return (1, k)
            if "risk_score" in k:
                return (2, k)
            return (3, k)

        for k, v in sorted(items, key=_sort_key):
            k_l = str(k).lower()
            horizon = "30yr" if ("30" in k_l and "yr" in k_l) else "10yr"
            if isinstance(v, (int, float)):
                tier = _prevent_tier(v, horizon=horizon)
                tier_suffix = f" ({tier})" if tier else ""
                print(f"- {k}: {_format_percent(v, 2)}{tier_suffix}")
            else:
                print(f"- {k}: {_safe_strip(v)}")
    else:
        _bullet_list(_pretty_calc_block(prevent))

    scores = calc.get("scores") if isinstance(calc, dict) else None
    if isinstance(scores, dict) and scores:
        print("\nOther Scores:")
        omit = {"MLC_score", "PREVENT"}
        preferred = ["signatures_score", "sdi", "metabolic_syndrome_score", "ckm_stage", "chads2vasc_score"]
        for k in preferred:
            if k in scores and k not in omit:
                print(f"- {k}: {scores.get(k)}")
        for k, v in scores.items():
            if k in omit or k in preferred:
                continue
            print(f"- {k}: {v}")

def pick_persona() -> PersonaKey:
    _title("Signatures Engine")

    print("\nChoose a communication style:")
    for i, p in enumerate(PERSONAS, start=1):
        print(f"{i}. {p.capitalize()}")

    raw = _safe_strip(input(f"Enter 1-{len(PERSONAS)} (default 1): "))
    persona = _normalize_persona_choice(raw)
    return persona

def _parse_cli_args(argv=None):
    """
    Add safe CLI options without breaking interactive mode.
    """
    import argparse

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--demo",
        choices=sorted(DEMO_PRESETS.keys()),
        help="Apply a demo override preset (for presentations).",
    )
    parser.add_argument(
        "--show-demos",
        action="store_true",
        help="Print available demo names and exit.",
    )
    return parser.parse_args(argv)


def _apply_demo_to_calc_context(demo_name: str) -> None:
    """
    Mutates global CALC_CONTEXT by merging the demo preset.
    Demo values override calculator values (because CALC_CONTEXT wins in your merge).
    """
    global CALC_CONTEXT
    preset = DEMO_PRESETS.get(demo_name) or {}

    # Ensure CALC_CONTEXT exists and is a dict
    if not isinstance(CALC_CONTEXT, dict):
        CALC_CONTEXT = {}

    # Shallow merge is usually fine because preset keys are top-level blocks:
    # condition_modifiers, inputs, engagement_drivers, prevent, scores
    CALC_CONTEXT = {**CALC_CONTEXT, **preset}




def main():
    args = _parse_cli_args()

    if getattr(args, "show_demos", False):
        print("Available demos:")
        for k in sorted(DEMO_PRESETS.keys()):
            print(f"- {k}")
        return

    if getattr(args, "demo", None):
        _apply_demo_to_calc_context(args.demo)
        print(f"[DEMO] Applied preset: {args.demo}")


    # Validate bank (FIXED: pass QUESTION_BANK)
    issues = validate_question_bank(QUESTION_BANK, raise_on_error=False)

    if issues:
        print("⚠️ Question bank issues detected (non-fatal). First 5:")
        for it in issues[:5]:
            # supports either dataclass BankIssue or plain dict
            qid = getattr(it, "qid", None) or (it.get("qid") if isinstance(it, dict) else "?")  # type: ignore
            msg = getattr(it, "message", None) or (it.get("message") if isinstance(it, dict) else str(it))  # type: ignore
            print(f"- {qid}: {msg}")

    persona = pick_persona()
    q = choose_question()

    # Pull calculator context once so every section stays in sync.
    calc = get_merged_calc_context()

    # Desired order (after the question is selected):
    # Question -> Inputs -> Scoring Hooks -> Answer -> Signatures Structure -> Source
    render_question_header(q)
    render_input_values(calc)
    render_scoring_hooks(calc)

    # render_persona_response expects (q, style_key, persona_display).
    # Do not repeat the question line because we printed it above.
    render_persona_response(q.payload, persona, persona, calc_override=calc, show_question=False)

    # Always show Signatures Structure (fundamental)
    render_signatures_sections(q.payload, calc_override=calc)

    # Always show source section
    render_sources(q)

    print("\nDone.\n")


if __name__ == "__main__":
    main()




