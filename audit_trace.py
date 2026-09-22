import json
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TRACE_FILE = BASE_DIR / "trace.jsonl"


def clear_trace():
    TRACE_FILE.write_text(
        "",
        encoding="utf-8"
    )


def log_event(
    event_type,
    cap=None,
    **data
):
    event = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event": event_type,
    }

    if cap:
        event["cap"] = cap

    event.update(data)

    with TRACE_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(
                event,
                ensure_ascii=False
            )
            + "\n"
        )