import argparse
import json

from inbox_store import InboxStore

from preferences import (
    PreferenceStore,
    extract_meeting_preference,
    evaluate_meeting_request,
)

from audit_trace import log_event


def store_phase():
    store = InboxStore()

    message = store.get_message(
        "m041"
    )

    if not message:
        raise RuntimeError(
            "m041 was not found"
        )

    extracted = (
        extract_meeting_preference(
            message
        )
    )

    if not extracted:
        raise RuntimeError(
            "Could not extract preference "
            "from m041"
        )

    preference_store = (
        PreferenceStore()
    )

    saved = (
        preference_store.save_preference(
            key=extracted["key"],
            value=extracted["value"],
            source_message_id="m041",
        )
    )

    log_event(
        "preference_write",
        cap="R4",
        key=extracted["key"],
        value=extracted["value"],
        source_message_id="m041",
    )

    print(
        json.dumps({
            "phase": "store",
            "process": "first",
            "stored": saved,
        })
    )


def apply_phase():
    store = InboxStore()

    message = store.get_message(
        "m043"
    )

    if not message:
        raise RuntimeError(
            "m043 was not found"
        )

    preference_store = (
        PreferenceStore()
    )

    result = (
        evaluate_meeting_request(
            message,
            preference_store,
        )
    )

    log_event(
        "preference_applied",
        cap="R4",
        message_id="m043",
        source_preference_message_id="m041",
        **result,
    )

    print(
        json.dumps({
            "phase": "apply",
            "process": "second",
            "target_message_id": "m043",
            **result,
        })
    )


def main():
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--phase",
        required=True,
        choices=[
            "store",
            "apply",
        ],
    )

    args = parser.parse_args()

    if args.phase == "store":
        store_phase()
        return

    if args.phase == "apply":
        apply_phase()


if __name__ == "__main__":
    main()