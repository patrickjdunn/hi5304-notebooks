"""
signatures_engine.py

CLI engine for:
- selecting persona
- choosing a preloaded question (by number or ID)
- searching questions
- entering a custom question
- printing structured output

Designed to be resilient:
- missing persona responses are auto-filled in questions.py
- IDs are auto-generated if missing
"""

from __future__ import annotations
from typing import Any, Dict, Optional, List

import sys

from questions import (
    PERSONAS,
    all_categories,
    list_questions,
    list_question_summaries,
    valid_ids,
    get_question_by_id,
    search_questions,
    validate_question_bank,
)


# ---------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------

def _safe(s: Any) -> str:
    return "" if s is None else str(s).strip()


def choose_persona() -> str:
    print("\nChoose a communication style:")
    for i, p in enumerate(PERSONAS, start=1):
        print(f"{i}. {p}")
    raw = input("Enter 1-4 (default 1): ").strip()
    if not raw:
        return PERSONAS[0]
    try:
        idx = int(raw)
        if 1 <= idx <= len(PERSONAS):
            return PERSONAS[idx - 1]
    except ValueError:
        pass
    print("⚠️ Invalid choice. Defaulting to Listener.")
    return PERSONAS[0]


def print_question_list(items: List[Dict[str, str]], max_items: int = 70) -> None:
    print("\nPreloaded Questions:")
    if not items:
        print("⚠️ No questions available.")
        return

    for i, item in enumerate(items[:max_items], start=1):
        cat = item.get("category", "GENERAL")
        qid = item.get("id", "NO-ID")
        qtxt = item.get("question", "").strip() or "(missing question text)"
        print(f"{i:2d}. [{cat}] {qid} — {qtxt}")

    if len(items) > max_items:
        print(f"... ({len(items) - max_items} more not shown)")


def pick_preloaded_question() -> Optional[Dict[str, Any]]:
    # Category filter
    raw_cat = input("Optional: type a category to filter (or press Enter to show all): ").strip()
    category = raw_cat.upper() if raw_cat else None

    items = list_question_summaries()
    if category:
        filtered = [x for x in items if x.get("category", "").upper() == category]
        if not filtered:
            print("⚠️ No questions found for that filter. Showing all.")
        else:
            items = filtered

    print_question_list(items)

    if not items:
        return None

    print("\nPick by:")
    print(" - number (e.g., 1)")
    print(" - ID (e.g., CKM-01)")
    choice = input("Enter selection: ").strip()

    if not choice:
        return None

    # Number selection
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(items):
            qid = items[idx - 1]["id"]
            return get_question_by_id(qid)
        print("⚠️ Number out of range.")
        return None

    # ID selection
    q = get_question_by_id(choice)
    if q:
        return q

    # If not found, show valid IDs and suggest
    print("⚠️ Not found. Here are a few valid IDs:")
    print(", ".join(valid_ids(category=category)[:20]))
    return None


def search_mode() -> Optional[Dict[str, Any]]:
    print("\nSearch Mode")
    raw_cat = input("Optional category filter (or press Enter for all): ").strip()
    category = raw_cat.upper() if raw_cat else None

    query = input("Enter keyword(s) to search: ").strip()
    if not query:
        print("⚠️ No keywords entered.")
        return None

    matches = search_questions(query=query, category=category, limit=50)
    if not matches:
        print("⚠️ No matches found.")
        return None

    print_question_list(matches, max_items=50)
    choice = input("Select by number or ID (or press Enter to cancel): ").strip()
    if not choice:
        return None

    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(matches):
            return get_question_by_id(matches[idx - 1]["id"])
        print("⚠️ Number out of range.")
        return None

    q = get_question_by_id(choice)
    if q:
        return q

    print("⚠️ Not found.")
    return None


def render_output(persona: str, question_obj: Dict[str, Any]) -> None:
    q_text = _safe(question_obj.get("question"))
    responses = question_obj.get("responses", {}) or {}
    persona_msg = _safe(responses.get(persona))

    action_step = _safe(question_obj.get("action_step"))
    why = _safe(question_obj.get("why_it_matters"))
    source_title = _safe(question_obj.get("source_title"))
    source_url = _safe(question_obj.get("source_url"))

    print("\n" + "=" * 72)
    print("SIGNATURES OUTPUT")
    print("=" * 72)
    print(f"Persona: {persona}")
    print(f"Question: {q_text}\n")

    print("Response:")
    print(persona_msg if persona_msg else "(no response available)")

    if action_step:
        print("\nAction Step:")
        print(action_step)
    if why:
        print("\nWhy it matters:")
        print(why)

    if source_title or source_url:
        print("\nSource:")
        if source_title:
            print(f"- {source_title}")
        if source_url:
            print(f"- {source_url}")

    # Optional: signatures metadata
    sig = question_obj.get("signatures")
    if isinstance(sig, dict) and sig:
        print("\nSignatures Tags:")
        for k, v in sig.items():
            print(f"- {k}: {v}")

    print("=" * 72 + "\n")


def custom_question_flow(persona: str) -> None:
    q_text = input("\nEnter your custom question: ").strip()
    if not q_text:
        print("⚠️ No question entered.")
        return

    # Basic generic response if custom
    print("\n" + "=" * 72)
    print("SIGNATURES OUTPUT (CUSTOM QUESTION)")
    print("=" * 72)
    print(f"Persona: {persona}")
    print(f"Question: {q_text}\n")
    print("Response:")
    if persona == "Listener":
        print("I hear you. What part of this feels most urgent or confusing right now?")
    elif persona == "Motivator":
        print("You’re taking a strong step by asking. Let’s pick one small action you can start this week.")
    elif persona == "Director":
        print("Here’s a simple next step: write down 1 goal, 1 barrier, and 1 action you can do today.")
    else:
        print("In general, evidence-based steps combine healthy habits, monitoring, and clinician guidance tailored to your risk.")
    print("=" * 72 + "\n")


def main() -> None:
    # Non-fatal validation check
    issues = validate_question_bank(raise_on_error=False)
    if issues:
        print("⚠️ Question bank issues detected (non-fatal). First 5:")
        for x in issues[:5]:
            print(f"- {x}")

    print("Signatures Engine")

    persona = choose_persona()

    while True:
        print("\nMenu:")
        print("1) Choose a preloaded question")
        print("2) Search mode (keyword search)")
        print("3) Enter a custom question")
        print("4) Show categories")
        print("5) Quit")

        choice = input("Enter choice (1-5): ").strip()

        if choice == "1":
            use_preloaded = input("Use a preloaded question? (Y/n): ").strip().lower()
            if use_preloaded in ("", "y", "yes"):
                q = pick_preloaded_question()
                if q:
                    render_output(persona, q)

        elif choice == "2":
            q = search_mode()
            if q:
                render_output(persona, q)

        elif choice == "3":
            custom_question_flow(persona)

        elif choice == "4":
            print("\nCategories:")
            print(", ".join(all_categories()))

        elif choice == "5":
            print("Goodbye.")
            return

        else:
            print("⚠️ Invalid selection.")


if __name__ == "__main__":
    main()




