"""
questions.py

Holds the preloaded question bank and helper functions for:
- listing categories/questions
- searching
- retrieving by ID
- validating and normalizing the bank (auto-fill missing fields)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import re

# ---------------------------------------------------------------------
#Signatures
# ---------------------------------------------------------------------

PERSONAS: List[str] = ["Listener", "Motivator", "Director", "Expert"]

# Safe defaults used if a question is missing persona responses
DEFAULT_RESPONSES: Dict[str, str] = {
    "Listener": "I hear you. Tell me a bit more about what feels hardest or most confusing right now.",
    "Motivator": "You’ve got this. One small step this week can make a real difference.",
    "Director": "Here’s a simple next step: pick one action you can do today and repeat it daily for a week.",
    "Expert": "In general, evidence supports combining healthy habits with guideline-based care; your clinician can tailor this to you.",
}

# ---------------------------------------------------------------------
# Question schema (flexible)
# Each question dict may include:
#   id: str (auto-generated if missing)
#   category: str (default GENERAL)
#   question: str
#   responses: {Listener/Motivator/Director/Expert: str}
#   action_step: str (optional)
#   why_it_matters: str (optional)
#   signatures: dict (optional, for Signatures codes)
#   source_title: str (optional)
#   source_url: str (optional)
# ---------------------------------------------------------------------

QUESTION_BANK: List[Dict[str, Any]] = [
    # --- Minimal examples (you can paste your full sets here) ---
    {
        "category": "CKM",
        "question": "What does my diagnosis mean for my future?",
        "responses": {
            "Listener": "That sounds overwhelming. What are you most worried about?",
            "Motivator": "You can live a full life with support.",
            "Director": "Let’s monitor labs and scores every 3 months.",
            "Expert": "Early action guided by PREVENT and Life’s Essential 8 makes a difference.",
        },
        "action_step": "Write down your top 3 concerns and bring them to your next visit.",
        "why_it_matters": "Sharing helps your care team focus on what matters most to you.",
        "source_title": "Cardiovascular-Kidney-Metabolic Health",
        "source_url": "https://www.heart.org/en/professional/quality-improvement/cardio-kidney-metabolic-health",
    },
    {
        "category": "HTN",
        "question": "What should my blood pressure goal be?",
        "responses": {
            "Listener": "It’s normal to feel unsure—many people don’t know their number.",
            "Motivator": "Knowing your goal puts you in control!",
            "Director": "For many people, a common target is below 130/80—your clinician may individualize this.",
            "Expert": "Lower blood pressure is associated with lower risk of heart attack, stroke, and kidney disease.",
        },
        "action_step": "Ask your doctor: “What’s my target blood pressure?” and write it down.",
        "why_it_matters": "Clear targets make it easier to track progress and adjust your plan.",
        "source_title": "Understanding Blood Pressure Readings",
        "source_url": "https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings",
    },
]

# ---------------------------------------------------------------------
# Normalization + ID generation
# ---------------------------------------------------------------------

def rebuild_ids() -> None:
    """
    Ensures every question has a stable id like CAT-01, CAT-02...
    Only fills missing/blank ids; it does not overwrite existing ids.
    """
    counters: Dict[str, int] = {}
    for q in QUESTION_BANK:
        cat = (q.get("category") or "GENERAL").strip().upper()
        counters.setdefault(cat, 0)
        counters[cat] += 1

        if not str(q.get("id", "")).strip():
            q["id"] = f"{cat}-{counters[cat]:02d}"


def normalize_question_bank() -> int:
    """
    Ensures all questions have required keys and persona responses.
    Auto-fills blanks with safe defaults.
    Returns count of persona fields auto-filled.
    """
    rebuild_ids()

    fixed = 0
    for q in QUESTION_BANK:
        q.setdefault("category", "GENERAL")
        q.setdefault("question", "")
        q.setdefault("responses", {})

        if not isinstance(q["responses"], dict):
            q["responses"] = {}

        for persona in PERSONAS:
            val = q["responses"].get(persona, "")
            if not str(val).strip():
                q["responses"][persona] = DEFAULT_RESPONSES[persona]
                fixed += 1

        # Optional fields default
        if "action_step" not in q:
            q["action_step"] = ""
        if "why_it_matters" not in q:
            q["why_it_matters"] = ""
        if "source_title" not in q:
            q["source_title"] = ""
        if "source_url" not in q:
            q["source_url"] = ""

    return fixed


def validate_question_bank(raise_on_error: bool = False) -> List[str]:
    """
    Validate integrity. Non-fatal by default.
    Returns list of issues found.
    """
    normalize_question_bank()

    issues: List[str] = []
    for q in QUESTION_BANK:
        qid = q.get("id", "UNKNOWN")

        if not str(q.get("question", "")).strip():
            issues.append(f"{qid}: missing question text")

        if not str(q.get("category", "")).strip():
            issues.append(f"{qid}: missing category")

        responses = q.get("responses")
        if not isinstance(responses, dict) or not responses:
            issues.append(f"{qid}: missing responses")
            continue

        for persona in PERSONAS:
            if persona not in responses or not str(responses[persona]).strip():
                issues.append(f"{qid}: missing/blank persona response for {persona}")

    if raise_on_error and issues:
        raise ValueError("Question bank validation failed:\n" + "\n".join(issues))

    return issues


# ---------------------------------------------------------------------
# Listing + lookup helpers
# ---------------------------------------------------------------------

def all_categories() -> List[str]:
    normalize_question_bank()
    cats = sorted({(q.get("category") or "GENERAL").upper() for q in QUESTION_BANK})
    return cats


def list_questions(category: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Returns list of lightweight summaries for display:
      [{"id": "...", "category": "...", "question": "..."}]
    """
    normalize_question_bank()
    out: List[Dict[str, str]] = []
    for q in QUESTION_BANK:
        cat = (q.get("category") or "GENERAL").upper()
        if category and cat != category.strip().upper():
            continue
        out.append({
            "id": str(q.get("id", "")).strip(),
            "category": cat,
            "question": str(q.get("question", "")).strip(),
        })
    return out


def list_question_summaries(limit: Optional[int] = None) -> List[Dict[str, str]]:
    items = list_questions()
    return items[:limit] if limit else items


def valid_ids(category: Optional[str] = None) -> List[str]:
    return [x["id"] for x in list_questions(category=category)]


def get_question_by_id(qid: str) -> Optional[Dict[str, Any]]:
    normalize_question_bank()
    qid = qid.strip().upper()
    for q in QUESTION_BANK:
        if str(q.get("id", "")).strip().upper() == qid:
            return q
    return None


def search_questions(query: str, category: Optional[str] = None, limit: int = 25) -> List[Dict[str, str]]:
    """
    Keyword search across question text and persona responses.
    Returns summaries (id/category/question).
    """
    normalize_question_bank()
    q = (query or "").strip().lower()
    if not q:
        return []

    pat = re.compile(re.escape(q), re.IGNORECASE)
    results: List[Dict[str, str]] = []

    for item in QUESTION_BANK:
        cat = (item.get("category") or "GENERAL").upper()
        if category and cat != category.strip().upper():
            continue

        text_blobs = [str(item.get("question", ""))]
        responses = item.get("responses", {})
        if isinstance(responses, dict):
            text_blobs.extend([str(v) for v in responses.values()])

        hay = " ".join(text_blobs)
        if pat.search(hay):
            results.append({
                "id": str(item.get("id", "")).strip(),
                "category": cat,
                "question": str(item.get("question", "")).strip(),
            })

    return results[:limit]


