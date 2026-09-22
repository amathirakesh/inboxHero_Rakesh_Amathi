import json
import re
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent

PREFERENCES_FILE = (
    BASE_DIR
    / "artifacts"
    / "preferences.json"
)


class PreferenceError(Exception):
    pass


class PreferenceStore:
    def __init__(
        self,
        path=PREFERENCES_FILE,
    ):
        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    def load(self):
        if not self.path.exists():
            return {}

        try:
            return json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )

        except json.JSONDecodeError as exc:
            raise PreferenceError(
                "Preference file contains "
                "invalid JSON"
            ) from exc

    def save_preference(
        self,
        key,
        value,
        source_message_id,
    ):
        preferences = self.load()

        preferences[key] = {
            "value": value,
            "source_message_id":
                source_message_id,
            "updated_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),
        }

        self.path.write_text(
            json.dumps(
                preferences,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return preferences[key]

    def get(self, key):
        preferences = self.load()
        return preferences.get(key)

def extract_meeting_preference(message):
    """
    Extract a safe meeting-time preference.

    Example supported text:
    "I do not take meetings before 11:00am, ever."
    """

    body = message.get(
        "body",
        ""
    ).lower()

    patterns = [
        r"i\s+do\s+not\s+take\s+meetings?\s+before\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)",

        r"i\s+don't\s+take\s+meetings?\s+before\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)",

        r"no\s+meetings?\s+before\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)",

        r"never\s+schedule\s+meetings?\s+before\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            body
        )

        if not match:
            continue

        hour = int(
            match.group(1)
        )

        minute = int(
            match.group(2) or 0
        )

        meridiem = (
            match.group(3)
            .lower()
        )

        if meridiem == "pm" and hour != 12:
            hour += 12

        if meridiem == "am" and hour == 12:
            hour = 0

        return {
            "key": "meeting_not_before",
            "value": f"{hour:02d}:{minute:02d}",
        }

    return None

def parse_hour_from_message(
    message
):
    text = " ".join([
        message.get(
            "subject",
            ""
        ),
        message.get(
            "body",
            ""
        ),
    ]).lower()

    match = re.search(
        r"\b(\d{1,2})"
        r"(?::(\d{2}))?\s*"
        r"(am|pm)\b",
        text,
    )

    if not match:
        return None

    hour = int(
        match.group(1)
    )

    minute = int(
        match.group(2) or 0
    )

    meridiem = (
        match.group(3)
        .lower()
    )

    if meridiem == "pm" and hour != 12:
        hour += 12

    if meridiem == "am" and hour == 12:
        hour = 0

    return (
        f"{hour:02d}:"
        f"{minute:02d}"
    )


def time_to_minutes(
    value
):
    hour, minute = map(
        int,
        value.split(":")
    )

    return (
        hour * 60
        + minute
    )


def evaluate_meeting_request(
    message,
    preference_store,
):
    preference = (
        preference_store.get(
            "meeting_not_before"
        )
    )

    if not preference:
        return {
            "preference_applied":
                False,

            "decision":
                "no_preference",

            "reason":
                "No meeting-time preference "
                "is stored.",
        }

    proposed_time = (
        parse_hour_from_message(
            message
        )
    )

    if not proposed_time:
        return {
            "preference_applied":
                False,

            "decision":
                "time_not_found",

            "reason":
                "No proposed meeting time "
                "could be extracted.",
        }

    earliest = (
        preference["value"]
    )

    conflict = (
        time_to_minutes(
            proposed_time
        )
        <
        time_to_minutes(
            earliest
        )
    )

    if conflict:
        return {
            "preference_applied":
                True,

            "decision":
                "conflict",

            "proposed_time":
                proposed_time,

            "earliest_allowed":
                earliest,

            "reason": (
                f"Proposed meeting time "
                f"{proposed_time} conflicts "
                f"with standing preference "
                f"not to schedule meetings "
                f"before {earliest}."
            ),

            "suggestion": (
                f"Offer {earliest} "
                f"or later."
            ),
        }

    return {
        "preference_applied":
            True,

        "decision":
            "allowed",

        "proposed_time":
            proposed_time,

        "earliest_allowed":
            earliest,

        "reason":
            "The proposed meeting time "
            "satisfies the stored preference.",
    }