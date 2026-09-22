import argparse
import json
from pathlib import Path

from inbox_store import (
    InboxStore,
    InboxValidationError,
)

from llm_provider import (
    OllamaProvider,
    LLMProviderError,
)

from models import Decision

from rule_router import route_by_rule

from audit_trace import (
    clear_trace,
    log_event,
)


BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

DECISIONS_FILE = (
    ARTIFACTS_DIR / "decisions.json"
)


def inspect_inbox():
    try:
        store = InboxStore()

    except InboxValidationError as error:
        print(
            f"Inbox validation failed: {error}"
        )
        return

    messages = store.all_messages()
    unread = store.unread_messages()

    print("=" * 60)
    print("INBOXHERO - INBOX VALIDATION")
    print("=" * 60)

    print(
        f"Messages processed: {len(messages)}"
    )

    print(
        f"Unread messages: {len(unread)}"
    )

    print(
        f"Read messages: "
        f"{len(messages) - len(unread)}"
    )

    print(
        f"Threads: {len(store.by_thread)}"
    )

    print("\nValidation: PASSED")


def run_r1():
    print("=" * 70)
    print("R1 - ZERO THE INBOX")
    print("=" * 70)

    clear_trace()

    ARTIFACTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    store = InboxStore()
    provider = OllamaProvider()

    decisions = []

    rule_handled = 0
    model_handled = 0
    model_failures = 0

    log_event(
        "run_start",
        cap="R1",
        messages=store.count()
    )

    for index, message in enumerate(
        store.all_messages(),
        start=1
    ):
        message_id = message["id"]

        log_event(
            "message_read",
            cap="R1",
            message_id=message_id
        )

        decision = route_by_rule(
            message
        )

        if decision is not None:
            rule_handled += 1

        else:
            try:
                decision = (
                    provider.classify_message(
                        message
                    )
                )

                model_handled += 1

            except LLMProviderError as error:
                model_failures += 1

                # Safety fallback:
                # a model failure must never leave
                # the message undecided.
                decision = Decision(
                    message_id=message_id,
                    disposition="escalate",
                    reason=(
                        "Classification could not be "
                        "completed safely because the "
                        "model was unavailable or returned "
                        "an invalid response."
                    ),
                    handled_by="fallback",
                    rule_name=None,
                )

                log_event(
                    "model_error",
                    cap="R1",
                    message_id=message_id,
                    error=str(error),
                )

        decisions.append(
            decision
        )

        log_event(
            "decision",
            cap="R1",
            **decision.to_dict()
        )

        print(
            f"[{index:03}/{store.count()}] "
            f"{message_id:<5} "
            f"{decision.disposition:<9} "
            f"{decision.handled_by:<8} "
            f"{decision.reason}"
        )

    decision_dicts = [
        decision.to_dict()
        for decision in decisions
    ]

    DECISIONS_FILE.write_text(
        json.dumps(
            decision_dicts,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    decided_ids = {
        decision.message_id
        for decision in decisions
    }

    inbox_ids = {
        message["id"]
        for message in store.all_messages()
    }

    undecided_ids = (
        inbox_ids - decided_ids
    )

    duplicate_decisions = (
        len(decisions)
        - len(decided_ids)
    )

    print("\n" + "=" * 70)
    print("R1 SUMMARY")
    print("=" * 70)

    print(
        f"Messages processed: {store.count()}"
    )

    print(
        f"Rule handled:      {rule_handled}"
    )

    print(
        f"Model handled:     {model_handled}"
    )

    print(
        f"Model failures:    {model_failures}"
    )

    print(
        f"Undecided:         {len(undecided_ids)}"
    )

    print(
        f"Duplicate decisions: "
        f"{duplicate_decisions}"
    )

    log_event(
        "run_summary",
        cap="R1",
        messages_processed=store.count(),
        rule_handled=rule_handled,
        model_handled=model_handled,
        model_failures=model_failures,
        undecided=len(undecided_ids),
        duplicate_decisions=duplicate_decisions,
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--inspect",
        action="store_true",
    )

    parser.add_argument(
        "--cap",
    )

    parser.add_argument(
        "--all",
        action="store_true",
    )

    parser.add_argument(
        "--msg",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    if args.inspect:
        inspect_inbox()
        return

    if args.cap == "R1":
        run_r1()
        return

    print(
        "Capability not implemented yet."
    )


if __name__ == "__main__":
    main()