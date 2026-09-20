"""
SESSION RESULT LOG

Appends one row per completed session so the confidence pre/post measurement
is actually reportable, rather than living and dying in st.session_state.

Deliberately records only structured fields — not her day narrative, not the
reflection text, not her district. Those are free-text personal descriptions,
and writing them to a CSV by default is a consent question rather than an
engineering one. If the study needs them, that should be an explicit decision
with a participant-information step in front of it.
"""
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RESULTS_FILE = RESULTS_DIR / "sessions.csv"

FIELDS = [
    "timestamp",
    "flow",
    "confidence_before",
    "confidence_after",
    "final_skill_id",
    "final_score",
    "used_llm_reading",
    "questions_answered",
    "state",
    "stage",
]


def record_session(profile) -> bool:
    """
    Append one row. Returns True on success. Never raises — a logging failure
    must not take down the results screen she just reached.
    """
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "flow": profile.get("flow", ""),
        "confidence_before": profile.get("confidence_before", ""),
        "confidence_after": profile.get("confidence_after", ""),
        "final_skill_id": profile.get("final_skill_id", ""),
        "final_score": (profile.get("final_assessment") or {}).get("score", ""),
        "used_llm_reading": bool(profile.get("skill_reading")),
        # a rough measure of how long the session was for her
        "questions_answered": sum(
            1 for key, value in profile.items()
            if value not in (None, "", []) and not key.startswith("_") and not key.endswith("_hi")
        ),
        "state": profile.get("state", ""),
        "stage": profile.get("stage", ""),
    }

    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        write_header = not RESULTS_FILE.exists()
        with RESULTS_FILE.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        return True
    except Exception as exc:
        log.warning("Could not record session (%s): %s", type(exc).__name__, exc)
        return False
