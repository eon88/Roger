"""Canonical untrusted-but-structured tenant repair interview evidence.

No model calls, no file writes. All statements are from the signed-in tenant's
submitted form and are NOT proof of a diagnosis or a professional inspection.
The server recomputes hazard flags and a suggested trade independently.
"""
from datetime import datetime, timezone
from repair_diagnosis import danger_flags, trade_for


def _text(value, maximum):
    if not isinstance(value, str):
        raise ValueError("Interview text must be a string")
    clean = " ".join(value.split()).strip()
    if not clean or len(clean) > maximum:
        raise ValueError("Invalid interview field length")
    return clean


def normalise_dossier(value):
    """Validate, bound and turn browser-provided evidence into a server record.

    Returns None for the optional standard repair submission.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Repair interview must be an object")
    if set(value) - {"description", "history"}:
        raise ValueError("Repair interview contains unsupported fields")
    description = _text(value.get("description"), 1500)
    history = value.get("history")
    if not isinstance(history, list) or len(history) > 3:
        raise ValueError("Interview must contain at most three answers")
    answers = []
    for entry in history:
        if not isinstance(entry, dict) or set(entry) != {"question", "answer"}:
            raise ValueError("Invalid interview question or answer")
        answers.append({
            "question": _text(entry.get("question"), 160),
            "answer": _text(entry.get("answer"), 500),
        })
    statement = description + "\n" + "\n".join(a["answer"] for a in answers)
    return {
        "schema": "roger-repair-interview-v1",
        "source": "tenant_submitted_unverified",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "answers": answers,
        "safety_flags": danger_flags(statement),
        "suggested_trade": trade_for(statement),
        "needs_agent_review": True,
    }
