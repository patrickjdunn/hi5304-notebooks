#!/usr/bin/env python3
"""
signatures_engine.py

Signatures Engine (LLM-friendly CLI):

- Keeps the clean, minimal input flow (persona -> question mode -> optional signatures tags)
- Uses QUESTION_BANK from questions.py
- Supports:
  - Preloaded question picker (list + ID select)
  - Search mode (keyword search across question text + responses)
  - Signatures output sections:
      behavioral core, condition modifiers, engagement drivers (-1/0/+1),
      security rules, action plans, source + link
  - MyLifeCheck + PREVENT hooks:
      pulls results from combined_calculator.py if available (no re-entry required here)
      (If combined_calculator prompts for inputs, it does so inside that module.)

Important:
- This version fixes your error by calling:
    validate_question_bank(QUESTION_BANK, raise_on_error=False)
  while remaining backwards-compatible even if questions.py is missing helpers.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

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


def _prevent_tier(risk_value: Any, horizon: str = "10yr") -> str:
    """Heuristic risk tier labels (for interpretation; not a diagnosis).

    10-year tiers align with commonly used ASCVD-style groupings:
      <5% Low, 5–<7.5% Borderline, 7.5–<20% Intermediate, >=20% High

    30-year tiers are broader pragmatic buckets for readability.
    """
    try:
        x = float(risk_value)
    except Exception:
        return ""

    pct = x if x > 1.0 else x * 100.0

    if horizon.lower().startswith("30"):
        if pct < 20:
            return "Low"
        if pct < 30:
            return "Moderate"
        if pct < 40:
            return "High"
        return "Very High"

    if pct < 5:
        return "Low"
    if pct < 7.5:
        return "Borderline"
    if pct < 20:
        return "Intermediate"
    return "High"


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


# -----------------------------
# Signatures rendering
# -----------------------------
def render_signatures_sections(q: PickedQuestion):
    payload = q.payload

    sig = payload.get("signatures", {})
    if not isinstance(sig, dict):
        sig = {}

    behavioral_core = _as_list(sig.get("behavioral_core"))
    condition_modifiers = _as_list(sig.get("condition_modifiers"))

    # engagement_drivers supports -1/0/+1 scheme
    ed_raw = sig.get("engagement_drivers", {})
    engagement_present: List[str] = []
    engagement_unknown: List[str] = []
    engagement_not_present: List[str] = []

    if isinstance(ed_raw, dict):
        for k, v in ed_raw.items():
            code = _safe_strip(k)
            val = _clamp_engagement_value(v)
            if not code:
                continue
            if val == 1:
                engagement_present.append(code)
            elif val == 0:
                engagement_unknown.append(code)
            else:
                engagement_not_present.append(code)

    security_rules = _as_list(payload.get("security_rules"))
    action_plans = _as_list(payload.get("action_plans"))

    _title("Signatures Structure")

    print("\nBehavioral Core:")
    _bullet_list(behavioral_core)

    print("\nCondition Modifiers:")
    _bullet_list(condition_modifiers)

    print("\nEngagement Drivers (+1 present):")
    _bullet_list(sorted(engagement_present))

    # Keeping unknown/not-present visible but not noisy
    if engagement_unknown:
        print("\nEngagement Drivers (0 unknown):")
        _bullet_list(sorted(engagement_unknown))

    if engagement_not_present:
        print("\nEngagement Drivers (-1 not present):")
        _bullet_list(sorted(engagement_not_present))

    print("\nSecurity Rules:")
    _bullet_list(security_rules)

    print("\nAction Plans:")
    _bullet_list(action_plans)


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


def render_persona_response(q: PickedQuestion, persona: PersonaKey):
    payload = q.payload
    responses = payload.get("responses", {})

    _title("Answer")
    print(f"Question [{q.category}] {q.qid}: {q.question}\n")

    # If question has a direct persona response, use it; otherwise fall back.
    text = ""
    if isinstance(responses, dict):
        text = _safe_strip(responses.get(persona, ""))

    if not text:
        # fallback: try any available persona
        if isinstance(responses, dict):
            for p in PERSONAS:
                t = _safe_strip(responses.get(p, ""))
                if t:
                    text = t
                    break

    if text:
        print(text)
    else:
        print("(no persona response available yet for this question)")

    # Action Step / Why (optional, but common pattern)
    action_step = _safe_strip(payload.get("action_step", ""))
    why = _safe_strip(payload.get("why_it_matters", ""))

    if action_step or why:
        _print_hr()
        if action_step:
            print(f"Action Step: {action_step}")
        if why:
            print(f"Why it matters: {why}")


# -----------------------------
# Calculator rendering
# -----------------------------
def render_scoring_hooks():
    _title("Scoring Hooks (MyLifeCheck + PREVENT)")

    if not CALCULATOR_AVAILABLE:
        print("combined_calculator.py not available.")
        if CALCULATOR_IMPORT_ERROR:
            print("Import error:", CALCULATOR_IMPORT_ERROR)
        print("(You can still use Signatures without scoring.)")
        return

    calc = try_get_calculator_results()

    # Merge in local context (wins if keys overlap)
    if isinstance(CALC_CONTEXT, dict) and CALC_CONTEXT:
        calc = {**calc, **CALC_CONTEXT}

    # ✅ PLACE DEBUG RIGHT HERE
       
    print(
        "\n[DEBUG] calc keys include:",
        [k for k in calc.keys()
         if "MLC" in str(k)
         or "assessment" in str(k)
         or "cardio" in str(k)
         or "CVH" in str(k)]
    )
    print("[DEBUG] calc has", len(calc), "keys. First 30:", list(calc.keys())[:30])

    calc = try_get_calculator_results()

# Merge in local context (wins if keys overlap)
    if isinstance(CALC_CONTEXT, dict) and CALC_CONTEXT:
        calc = {**calc, **CALC_CONTEXT}

    print("\n[DEBUG] calc has", len(calc), "keys. First 30:", list(calc.keys())[:30])
    if isinstance(calc.get("scores"), dict):
        print("[DEBUG] scores keys:", list(calc["scores"].keys())[:50])
    if isinstance(calc.get("prevent"), dict):
        print("[DEBUG] prevent keys:", list(calc["prevent"].keys())[:50])

    mylife, prevent = extract_mylifecheck_prevent(calc)



    # ---------------------
    # MyLifeCheck
    # ---------------------
    print("\nMyLifeCheck / Life's Essential 8:")
    if isinstance(mylife, dict) and isinstance(mylife.get("MLC_score"), (int, float)):
        mlc = float(mylife["MLC_score"])
        tier = _mlc_tier(mlc)
        tier_suffix = f" ({tier})" if tier else ""
        #print(f"- MLC_score: {mlc:.2f}{tier_suffix}")
        
        # print remaining keys (if any)
        #rest = {k: v for k, v in mylife.items() if k != "MLC_score"}
        #_bullet_list(_pretty_calc_block(rest))
        rest = {k: v for k, v in mylife.items() if k != "MLC_score"}
    if rest:
        _bullet_list(_pretty_calc_block(rest))

    else:
        _bullet_list(_pretty_calc_block(mylife))

    # ---------------------
    # PREVENT
    # ---------------------
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


# -----------------------------
# Main
# -----------------------------
def pick_persona() -> PersonaKey:
    _title("Signatures Engine")

    print("\nChoose a communication style:")
    for i, p in enumerate(PERSONAS, start=1):
        print(f"{i}. {p.capitalize()}")

    raw = _safe_strip(input(f"Enter 1-{len(PERSONAS)} (default 1): "))
    persona = _normalize_persona_choice(raw)
    return persona


def main():
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

    render_persona_response(q, persona)

    # Always show Signatures Structure (fundamental)
    render_signatures_sections(q)

    # Always show scoring hooks (if calculator has results)
    render_scoring_hooks()

    # Always show source section
    render_sources(q)

    print("\nDone.\n")


if __name__ == "__main__":
    main()



