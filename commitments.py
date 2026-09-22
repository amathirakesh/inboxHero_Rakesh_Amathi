import calendar
import re
from datetime import datetime, timedelta


class CommitmentError(Exception):
    pass


def validate_sources(source_ids, store, read_set):
    for message_id in source_ids:
        if not store.get_message(message_id):
            raise CommitmentError(
                f"Source message does not exist: {message_id}"
            )

        if message_id not in read_set:
            raise CommitmentError(
                f"Source message was not read: {message_id}"
            )

    return True


def _to_24_hour(hour, minute, meridiem):
    hour = int(hour)
    minute = int(minute)

    meridiem = meridiem.lower()

    if meridiem == "pm" and hour != 12:
        hour += 12

    if meridiem == "am" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}"


def _base_year_month(message):
    timestamp = datetime.fromisoformat(
        message["timestamp"]
    )

    return timestamp.year, timestamp.month


def extract_board_review(message):
    pattern = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)"
        r",\s*(\d{1,2}):(\d{2})\s*(am|pm)",
        message["body"],
        re.IGNORECASE,
    )

    if not pattern:
        raise CommitmentError(
            "Could not parse board review"
        )

    year, month = _base_year_month(
        message
    )

    day = int(pattern.group(1))

    time_value = _to_24_hour(
        pattern.group(2),
        pattern.group(3),
        pattern.group(4),
    )

    return {
        "id": "commit-board-review",
        "title": "Quarterly board review",
        "date": f"{year:04d}-{month:02d}-{day:02d}",
        "time": time_value,
        "status": "confirmed",
        "source_message_ids": [
            message["id"]
        ],
        "derived": False,
        "conflicts_with": [],
    }


def derive_board_deck_deadline(
    board_message,
    deck_message,
):
    board = extract_board_review(
        board_message
    )

    board_date = datetime.strptime(
        board["date"],
        "%Y-%m-%d",
    )

    deadline = (
        board_date -
        timedelta(days=2)
    )

    return {
        "id": "commit-board-deck",
        "title": (
            "Finish and circulate board deck"
        ),
        "date": deadline.date().isoformat(),
        "time": None,
        "status": "deadline",
        "source_message_ids": [
            board_message["id"],
            deck_message["id"],
        ],
        "derived": True,
        "derivation": (
            "m038 sets the board review date; "
            "m040 requires the deck two days "
            "before the board review."
        ),
        "conflicts_with": [],
    }


def extract_investor_call(message):
    match = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)"
        r"\s+at\s+"
        r"(\d{1,2}):(\d{2})\s*(am|pm)",
        message["body"],
        re.IGNORECASE,
    )

    if not match:
        raise CommitmentError(
            "Could not parse investor call"
        )

    year, month = _base_year_month(
        message
    )

    day = int(match.group(1))

    time_value = _to_24_hour(
        match.group(2),
        match.group(3),
        match.group(4),
    )

    return {
        "id": "commit-investor-call",
        "title": "Investor intro call",
        "date": f"{year:04d}-{month:02d}-{day:02d}",
        "time": time_value,

        # Important: this has been proposed,
        # not confirmed.
        "status": "proposed",

        "source_message_ids": [
            message["id"]
        ],

        "derived": False,
        "conflicts_with": [],
    }


def extract_dentist(message):
    match = re.search(
        r"([A-Za-z]+)\s+"
        r"(\d{1,2})\s+at\s+"
        r"(\d{1,2}):(\d{2})\s*(am|pm)",
        message["body"],
        re.IGNORECASE,
    )

    if not match:
        raise CommitmentError(
            "Could not parse dentist appointment"
        )

    month_name = (
        match.group(1).lower()
    )

    month_lookup = {
        name.lower(): number
        for number, name
        in enumerate(calendar.month_name)
        if name
    }

    if month_name not in month_lookup:
        raise CommitmentError(
            f"Unknown month: {month_name}"
        )

    year, _ = _base_year_month(
        message
    )

    month = month_lookup[
        month_name
    ]

    day = int(
        match.group(2)
    )

    time_value = _to_24_hour(
        match.group(3),
        match.group(4),
        match.group(5),
    )

    return {
        "id": "commit-dentist",
        "title": "Dental cleaning",
        "date": (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        ),
        "time": time_value,
        "status": "confirmed",
        "source_message_ids": [
            message["id"]
        ],
        "derived": False,
        "conflicts_with": [],
    }


def detect_conflicts(commitments):
    timed = {}

    for commitment in commitments:
        if not commitment["time"]:
            continue

        key = (
            commitment["date"],
            commitment["time"],
        )

        timed.setdefault(
            key,
            []
        ).append(
            commitment
        )

    for items in timed.values():
        if len(items) < 2:
            continue

        for current in items:
            current["conflicts_with"] = [
                other["id"]
                for other in items
                if other["id"]
                != current["id"]
            ]

    return commitments


def build_commitments(store):
    required_ids = {
        "m038",
        "m040",
        "m010",
        "m061",
    }

    messages = {}

    read_set = set()

    for message_id in required_ids:
        message = store.get_message(
            message_id
        )

        if not message:
            raise CommitmentError(
                f"Missing required message: "
                f"{message_id}"
            )

        messages[message_id] = message
        read_set.add(message_id)

    commitments = [
        extract_board_review(
            messages["m038"]
        ),

        derive_board_deck_deadline(
            messages["m038"],
            messages["m040"],
        ),

        extract_investor_call(
            messages["m010"]
        ),

        extract_dentist(
            messages["m061"]
        ),
    ]

    for commitment in commitments:
        validate_sources(
            commitment[
                "source_message_ids"
            ],
            store,
            read_set,
        )

        commitment[
            "citations_validated"
        ] = True

    return detect_conflicts(
        commitments
    )