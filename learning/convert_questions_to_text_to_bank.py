#!/usr/bin/env python3
"""
convert_questions_text_to_bank.py  (with Signatures tags)

Usage:
  cd learning
  python convert_questions_text_to_bank.py input.txt --out questions_generated.py
  python convert_questions_text_to_bank.py input.txt --json --out questions_generated.json

What it produces:
- A QUESTION_BANK list of dicts, each with:
  id, category, question, responses, action_step, why_it_matters,
  signatures{behavioral_core, condition_modifiers, engagement_drivers, security_rules, action_plans, scoring_hooks},
  source_title, source_url
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


PERSONAS = ["Listener", "Motivator", "Director", "Expert"]

# -----------------------------
# Category detection
# -----------------------------
CATEGORY_HINTS: List[Tuple[str, str]] = [
    (r"\bheart,\s*kidney,\s*and\s*metabolic\b", "CKM"),
    (r"\bcardio.*kidney.*metabolic\b", "CKM"),
    (r"\bhigh blood pressure\b|\bhypertension\b", "HTN"),
    (r"\bheart failure\b", "HF"),
    (r"\bcoronary artery disease\b|\bCAD\b", "CAD"),
    (r"\batrial fibrillation\b|\bAFib\b", "AFIB"),
    (r"\bstroke\b", "STROKE"),
    (r"\bdiabetes\b", "DM"),
]

QUESTION_RE = re.compile(
    r"""^\s*Question\s*(\d+)\s*:\s*(?:[“"](?P<q1>.+?)[”"]|(?P<q2>.+))\s*$""",
    re.IGNORECASE,
)
PERSONA_RE = re.compile(
    r"""^\s*(?:[•\-\*_]\s*)?(Listener|Motivator|Director|Expert)\b\s*(?P<rest>.*)$""",
    re.IGNORECASE,
)
ACTION_RE = re.compile(r"^\s*Action\s*Step\s*:\s*(.+)\s*$", re.IGNORECASE)
WHY_RE = re.compile(r"^\s*Why\s*:\s*(.+)\s*$", re.IGNORECASE)

# -----------------------------
# Signatures configuration
# -----------------------------
# 1) Behavioral core mapping (category-level defaults)
BEHAVIORAL_CORE_BY_CATEGORY: Dict[str, str] = {
    "CKM": "PC",     # Preventive care & self-management
    "HTN": "BP",     # Blood pressure self-management
    "HF": "SY",      # Symptom tracking + self-management
    "CAD": "PC",     # Secondary prevention / risk reduction
    "AFIB": "MA",    # Med adherence + rhythm/stroke prevention behaviors
    "STROKE": "PC",  # Secondary prevention + rehab
    "DM": "GL",      # Glucose self-management
    "GENERAL": "PC",
}

# 2) Condition modifiers (category-level)
# Use your own taxonomy codes here (examples below).
CONDITION_MODIFIERS_BY_CATEGORY: Dict[str, List[str]] = {
    "CKM": ["CKM"],
    "HTN": ["HT"],
    "HF": ["HF"],
    "CAD": ["CAD"],
    "AFIB": ["AF"],
    "STROKE": ["STK"],
    "DM": ["DM"],
    "GENERAL": [],
}

# 3) Engagement driver inference (lightweight heuristics)
# These are examples aligned with your earlier traits (TR, SE, HL, GO, PR, etc.).
ENGAGEMENT_KEYWORDS: Dict[str, List[str]] = {
    "HL": ["explain", "what is", "what does", "mean", "confusing", "understand", "numbers", "chart"],
    "TR": ["trust", "side effects", "why am i on", "medications", "scared", "fear", "nervous"],
    "SE": ["can i", "still", "safely", "start", "begin", "exercise", "walk", "manage this"],
    "GO": ["goal", "target", "track", "monitor", "plan", "routine", "progress"],
    "PR": ["prevent", "avoid", "stay out of the hospital", "reduce risk", "early", "proactive"],
    "ID": ["still live my life", "independence", "routine", "travel", "vacation"],
    "FI": ["afford", "access", "food", "recipe", "groceries", "budget"],
}

# 4) Default safety rules by category (use your own codes if you have them)
DEFAULT_SECURITY_RULES_BY_CATEGORY: Dict[str, List[Dict[str, str]]] = {
    "HTN": [{"code": "SR-HTN-CRISIS", "text": "If your blood pressure is 180/120 or higher (especially with symptoms like chest pain, shortness of breath, weakness, vision changes, or trouble speaking), seek emergency care."}],
    "HF": [{"code": "SR-HF-FLARE", "text": "Call your healthcare team if you gain 2+ lb overnight or 5+ lb in a week, or if swelling or shortness of breath worsens."}],
    "CAD": [{"code": "SR-CAD-CP", "text": "Chest pain that lasts more than 5 minutes, comes with shortness of breath, sweating, nausea, or doesn’t improve with rest needs urgent evaluation (call emergency services)."}],
    "AFIB": [{"code": "SR-AFIB-STROKE", "text": "If you have signs of stroke (face drooping, arm weakness, speech trouble), call emergency services immediately."}],
    "STROKE": [{"code": "SR-STROKE-FAST", "text": "Use FAST: Face drooping, Arm weakness, Speech trouble—Time to call emergency services immediately if any are present."}],
    "DM": [{"code": "SR-DM-LOW", "text": "If you suspect low blood sugar (shaky, sweaty, confused), check glucose if possible and treat promptly with fast-acting carbs; seek help if severe or not improving."}],
    "CKM": [{"code": "SR-CKM-SX", "text": "Seek urgent care for new or worsening chest pain, severe shortness of breath, fainting, or rapidly worsening swelling."}],
    "GENERAL": [],
}

# Keyword-triggered safety rules (additive)
SECURITY_TRIGGERS: List[Tuple[re.Pattern, Dict[str, str]]] = [
    (re.compile(r"\bchest pain\b", re.IGNORECASE),
     {"code": "SR-CP-STOP", "text": "If you experience chest pain, stop what you’re doing and contact a healthcare professional or emergency services depending on severity."}),
    (re.compile(r"\bshortness of breath\b|\bbreathless\b", re.IGNORECASE),
     {"code": "SR-DYSPNEA", "text": "If you develop severe shortness of breath or it worsens quickly, stop activity and seek medical evaluation."}),
    (re.compile(r"\bexercise\b|\bwalk\b|\bactivity\b", re.IGNORECASE),
     {"code": "SR-EX-STOP", "text": "Stop exercise immediately if you have chest pain, dizziness, or severe shortness of breath, and contact your healthcare professional."}),
]

# 5) Default action plans by category
DEFAULT_ACTION_PLANS_BY_CATEGORY: Dict[str, List[Dict[str, str]]] = {
    "HTN": [{"code": "AP-HTN-HOME", "text": "Start home blood pressure monitoring with proper technique and share readings with your care team."}],
    "HF": [{"code": "AP-HF-TRACK", "text": "Use daily weights and a symptom log; review trends with your clinician."}],
    "CAD": [{"code": "AP-CAD-SEC", "text": "Focus on secondary prevention: meds as prescribed, nutrition, physical activity plan, and risk factor control."}],
    "AFIB": [{"code": "AP-AFIB-PLAN", "text": "Review rhythm/rate control and stroke prevention plan; discuss anticoagulation and symptom tracking."}],
    "STROKE": [{"code": "AP-STK-REHAB", "text": "Engage in stroke rehabilitation (PT/OT/speech therapy as indicated) and follow secondary prevention plan."}],
    "DM": [{"code": "AP-DM-PLAN", "text": "Create a glucose monitoring and medication plan; align meals, activity, and meds with your care team."}],
    "CKM": [{"code": "AP-CKM-COORD", "text": "Coordinate care across heart–kidney–metabolic goals; track key labs and vitals on a schedule."}],
    "GENERAL": [{"code": "AP-GEN-STEP", "text": "Pick one small change you can do this week and track it consistently."}],
}

# Trigger cardiac rehab when exercise / CAD / HF / AFIB shows up
REHAB_TRIGGER = re.compile(r"\bcardiac rehab\b|\brehab\b|\bexercise\b|\bwalking\b|\bactivity\b", re.IGNORECASE)

# 6) Scoring hooks (always include these hooks; they can be “not computed”)
DEFAULT_SCORING_HOOKS = {
    "mylifecheck": {
        "enabled": True,
        "notes": "Life’s Essential 8 domains: physical activity, diet, weight, sleep, tobacco, cholesterol, blood pressure, glucose.",
    },
    "prevent": {
        "enabled": True,
        "notes": "PREVENT risk can be calculated when inputs are available (age/sex/lipids/BP/diabetes/smoking/BMI/eGFR/etc.).",
    },
    "chads_vasc": {
        "enabled": False,
        "notes": "CHA₂DS₂-VASc is primarily used for AFib stroke risk decisions.",
    },
}

# 7) (Optional) default source links by category — you can refine these later
# Keep empty if you prefer to fill manually in questions.py.
DEFAULT_SOURCES_BY_CATEGORY: Dict[str, Dict[str, str]] = {
    "HTN": {"source_title": "American Heart Association — High Blood Pressure", "source_url": "https://www.heart.org/en/health-topics/high-blood-pressure"},
    "HF": {"source_title": "American Heart Association — Heart Failure", "source_url": "https://www.heart.org/en/health-topics/heart-failure"},
    "CAD": {"source_title": "American Heart Association — Coronary Artery Disease", "source_url": "https://www.heart.org/en/health-topics/heart-attack/about-heart-attacks"},
    "AFIB": {"source_title": "American Heart Association — Atrial Fibrillation (AFib)", "source_url": "https://www.heart.org/en/health-topics/atrial-fibrillation"},
    "STROKE": {"source_title": "American Stroke Association — Stroke", "source_url": "https://www.stroke.org/en/about-stroke"},
    "DM": {"source_title": "American Heart Association — Diabetes", "source_url": "https://www.heart.org/en/health-topics/diabetes"},
    "CKM": {"source_title": "American Heart Association — Cardio-Kidney-Metabolic Health", "source_url": "https://www.heart.org/en/professional/quality-improvement/cardio-kidney-metabolic-health"},
    "GENERAL": {"source_title": "American Heart Association — Healthy Living", "source_url": "https://www.heart.org/en/healthy-living"},
}


@dataclass
class QuestionItem:
    id: str
    category: str
    question: str
    responses: Dict[str, str]
    action_step: str = ""
    why_it_matters: str = ""
    signatures: Dict[str, Any] = None
    source_title: str = ""
    source_url: str = ""


def detect_category_from_line(line: str, current: str) -> str:
    low = line.lower()
    for pat, cat in CATEGORY_HINTS:
        if re.search(pat, low, flags=re.IGNORECASE):
            return cat
    return current


def clean_quotes(s: str) -> str:
    s = s.strip()
    return s.strip('“”"').strip()


def infer_engagement_drivers(question_text: str, responses: Dict[str, str]) -> Dict[str, int]:
    """
    Return engagement drivers dict with values:
      +1 present, 0 unknown, -1 not present
    We'll use a simple heuristic: if keywords appear in question or any persona response -> +1.
    Otherwise -> 0 (unknown).
    """
    blob = (question_text + " " + " ".join(responses.values())).lower()

    drivers: Dict[str, int] = {}
    for code, kws in ENGAGEMENT_KEYWORDS.items():
        hit = any(kw in blob for kw in kws)
        drivers[code] = 1 if hit else 0

    # Small persona-based nudges:
    # - Listener often implies trust/affect; Motivator implies self-efficacy.
    if responses.get("Listener", "").strip():
        drivers["TR"] = max(drivers.get("TR", 0), 1) if "scared" in blob or "overwhelming" in blob else drivers.get("TR", 0)
    if responses.get("Motivator", "").strip():
        drivers["SE"] = max(drivers.get("SE", 0), 1)

    return drivers


def build_security_rules(category: str, question_text: str) -> List[Dict[str, str]]:
    rules = list(DEFAULT_SECURITY_RULES_BY_CATEGORY.get(category, []))

    for pat, rule in SECURITY_TRIGGERS:
        if pat.search(question_text):
            # Avoid duplicates by code
            if not any(r.get("code") == rule["code"] for r in rules):
                rules.append(rule)

    return rules


def build_action_plans(category: str, question_text: str) -> List[Dict[str, str]]:
    plans = list(DEFAULT_ACTION_PLANS_BY_CATEGORY.get(category, []))

    # Cardiac rehab add-on
    if category in ("CAD", "HF", "AFIB", "CKM") and REHAB_TRIGGER.search(question_text):
        rehab_plan = {"code": "AP-REHAB", "text": "Ask your clinician if you qualify for a cardiac rehabilitation program (clinic-based or home-based)."}
        if not any(p.get("code") == rehab_plan["code"] for p in plans):
            plans.append(rehab_plan)

    return plans


def build_scoring_hooks(category: str, question_text: str) -> Dict[str, Any]:
    hooks = json.loads(json.dumps(DEFAULT_SCORING_HOOKS))  # deep-ish copy via json

    # Enable CHA2DS2-VASc for AFIB category or stroke-prevention questions
    if category == "AFIB" or re.search(r"\bblood thinner\b|\bstroke\b", question_text, flags=re.IGNORECASE):
        hooks["chads_vasc"]["enabled"] = True

    return hooks


def signatures_for_item(category: str, question_text: str, responses: Dict[str, str]) -> Dict[str, Any]:
    behavioral_core = BEHAVIORAL_CORE_BY_CATEGORY.get(category, "PC")
    condition_modifiers = CONDITION_MODIFIERS_BY_CATEGORY.get(category, [])
    engagement_drivers = infer_engagement_drivers(question_text, responses)
    security_rules = build_security_rules(category, question_text)
    action_plans = build_action_plans(category, question_text)
    scoring_hooks = build_scoring_hooks(category, question_text)

    return {
        "behavioral_core": behavioral_core,
        "condition_modifiers": condition_modifiers,
        "engagement_drivers": engagement_drivers,
        "security_rules": security_rules,
        "action_plans": action_plans,
        "scoring_hooks": scoring_hooks,
    }


def parse_blocks(lines: List[str]) -> List[QuestionItem]:
    items: List[QuestionItem] = []
    category = "GENERAL"

    current: Optional[QuestionItem] = None
    current_persona: Optional[str] = None
    counters: Dict[str, int] = {}

    def make_id(cat: str) -> str:
        counters[cat] = counters.get(cat, 0) + 1
        return f"{cat}-{counters[cat]:02d}"

    def flush():
        nonlocal current, current_persona
        if not current:
            return

        # Ensure all personas exist (empty if missing)
        for p in PERSONAS:
            current.responses.setdefault(p, "")

        # Add signatures tags
        current.signatures = signatures_for_item(current.category, current.question, current.responses)

        # Add default source (can be overridden later)
        if not current.source_title and not current.source_url:
            src = DEFAULT_SOURCES_BY_CATEGORY.get(current.category, DEFAULT_SOURCES_BY_CATEGORY["GENERAL"])
            current.source_title = src.get("source_title", "")
            current.source_url = src.get("source_url", "")

        items.append(current)
        current = None
        current_persona = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        category = detect_category_from_line(line, category)

        qm = QUESTION_RE.match(line)
        if qm:
            flush()
            q_text = clean_quotes(qm.group("q1") or qm.group("q2") or "")
            qid = make_id(category)
            current = QuestionItem(
                id=qid,
                category=category,
                question=q_text,
                responses={},
                signatures=None,
            )
            current_persona = None
            continue

        pm = PERSONA_RE.match(line)
        if pm and current:
            persona = pm.group(1).capitalize()
            rest = clean_quotes(pm.group("rest") or "")
            current.responses[persona] = rest
            current_persona = persona
            continue

        am = ACTION_RE.match(line)
        if am and current:
            current.action_step = clean_quotes(am.group(1))
            current_persona = None
            continue

        wm = WHY_RE.match(line)
        if wm and current:
            current.why_it_matters = clean_quotes(wm.group(1))
            current_persona = None
            continue

        # Continuation lines for persona message
        if current and current_persona:
            prev = current.responses.get(current_persona, "")
            extra = clean_quotes(line)
            current.responses[current_persona] = (prev + " " + extra).strip()
            continue

    flush()
    return items


def to_python(questions: List[QuestionItem]) -> str:
    data = [asdict(q) for q in questions]
    return "QUESTION_BANK = " + json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Input text file containing pasted question blocks.")
    ap.add_argument("--out", default="questions_generated.py", help="Output file path.")
    ap.add_argument("--json", action="store_true", help="Output JSON instead of Python.")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        lines = f.readlines()

    questions = parse_blocks(lines)

    print(f"Parsed {len(questions)} questions.")

    # Report missing persona responses
    missing = []
    for q in questions:
        missing_personas = [p for p in PERSONAS if not q.responses.get(p, "").strip()]
        if missing_personas:
            missing.append((q.id, missing_personas))

    if missing:
        print(f"Note: {len(missing)} questions have missing persona responses (left blank). First 10:")
        for qid, miss in missing[:10]:
            print(f" - {qid}: missing {', '.join(miss)}")

    if args.json:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([asdict(q) for q in questions], f, indent=2, ensure_ascii=False)
        print(f"Wrote JSON to {args.out}")
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("# Auto-generated by convert_questions_text_to_bank.py (with Signatures tags)\n\n")
            f.write(to_python(questions))
        print(f"Wrote Python to {args.out}")


if __name__ == "__main__":
    main()
