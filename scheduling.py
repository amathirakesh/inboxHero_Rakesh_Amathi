import re
from datetime import datetime, timedelta


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class SchedulingError(Exception):
    pass


def to_24_hour(
    hour,
    minute,
    meridiem,
):
    hour = int(hour)
    minute = int(minute or 0)

    meridiem = meridiem.lower()

    if meridiem == "pm" and hour != 12:
        hour += 12

    if meridiem == "am" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}"


def resolve_meeting_request(message):
    """
    Resolve wording such as:
    "Could you do Monday at 9:00am?"
    relative to the email timestamp.
    """

    text = " ".join([
        message.get("subject", ""),
        message.get("body", ""),
    ]).lower()

    match = re.search(
        r"\b("
        r"monday|tuesday|wednesday|thursday|"
        r"friday|saturday|sunday"
        r")\b.*?"
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*(am|pm)",
        text,
        re.IGNORECASE,
    )

    if not match:
        raise SchedulingError(
            "Could not resolve meeting day/time"
        )

    weekday_name = (
        match.group(1).lower()
    )

    proposed_time = to_24_hour(
        match.group(2),
        match.group(3),
        match.group(4),
    )

    sent_at = datetime.fromisoformat(
        message["timestamp"]
    )

    target_weekday = WEEKDAYS[
        weekday_name
    ]

    days_ahead = (
        target_weekday
        - sent_at.weekday()
    ) % 7

    # "Monday" in a scheduling request is treated as
    # the next occurrence when the named day is today.
    if days_ahead == 0:
        days_ahead = 7

    target_date = (
        sent_at.date()
        + timedelta(days=days_ahead)
    )

    return {
        "date": target_date.isoformat(),
        "time": proposed_time,
        "weekday": weekday_name,
    }


def slot_conflicts(
    date,
    time,
    commitments,
):
    conflicts = []

    for commitment in commitments:
        if (
            commitment.get("date") == date
            and commitment.get("time") == time
        ):
            conflicts.append(
                commitment
            )

    return conflicts


def existing_calendar_conflicts(
    commitments
):
    return [
        item
        for item in commitments
        if item.get(
            "conflicts_with"
        )
    ]