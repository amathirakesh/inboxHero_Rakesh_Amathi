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

from retrieval import InboxRetriever

from drafting import (
    GroundedDrafter,
    DraftingError,
    validate_citations,
)

from actions import (
    ActionProposal,
    ActionExecutor,
)

from action_gate import ActionGate

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
DRAFTS_FILE = (
    ARTIFACTS_DIR / "drafts.json"
)
PENDING_ACTIONS_FILE = (
    ARTIFACTS_DIR /
    "pending_actions.json"
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

def run_r2(message_id="m008"):
    print("=" * 70)
    print("R2 - GROUNDED REPLY")
    print("=" * 70)

    ARTIFACTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    store = InboxStore()

    target = store.get_message(
        message_id
    )

    if not target:
        print(
            f"Message not found: {message_id}"
        )
        return

    retriever = InboxRetriever(
        store
    )

    retrieval = (
        retriever.retrieve_thread_history(
            message_id
        )
    )

    print(
        f"Target message: {message_id}"
    )

    print(
        "Retrieval strategy: "
        "chronological thread-walk"
    )

    print(
        "Retrieved message ids:",
        sorted(retrieval.read_set)
    )

    log_event(
        "retrieval",
        cap="R2",
        target_message_id=message_id,
        strategy="thread-walk",
        retrieved_message_ids=sorted(
            retrieval.read_set
        ),
    )

    if not retrieval.messages:
        print(
            "\nNo earlier evidence found."
        )

        print(
            "Draft created: NO"
        )

        log_event(
            "draft_skipped",
            cap="R2",
            target_message_id=message_id,
            reason=(
                "No supporting evidence "
                "was retrieved."
            ),
        )

        return

    drafter = GroundedDrafter()

    try:
        result = drafter.draft(
            target,
            retrieval.messages,
        )

    except DraftingError as error:
        print(
            f"Drafting failed: {error}"
        )

        log_event(
            "draft_error",
            cap="R2",
            target_message_id=message_id,
            error=str(error),
        )

        return

    if not result:
        print(
            "Draft created: NO"
        )
        return

    if not result["can_draft"]:
        print(
            "\nEvidence was insufficient "
            "for a grounded reply."
        )

        print(
            "Draft created: NO"
        )

        log_event(
            "draft_skipped",
            cap="R2",
            target_message_id=message_id,
            reason=(
                "Model determined retrieved "
                "evidence was insufficient."
            ),
        )

        return

    try:
        validate_citations(
            result["cited_message_ids"],
            store,
            retrieval.read_set,
        )

    except DraftingError as error:
        print(
            f"Citation validation failed: "
            f"{error}"
        )

        log_event(
            "citation_validation_failed",
            cap="R2",
            target_message_id=message_id,
            error=str(error),
        )

        return

    artifact = {
        "target_message_id":
            message_id,

        "retrieval_strategy":
            "thread-walk",

        "read_set":
            sorted(
                retrieval.read_set
            ),

        "can_draft":
            True,

        "draft":
            result["draft"],

        "cited_message_ids":
            result[
                "cited_message_ids"
            ],
    }

    DRAFTS_FILE.write_text(
        json.dumps(
            [artifact],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    log_event(
        "citation_validation",
        cap="R2",
        target_message_id=message_id,
        cited_message_ids=result[
            "cited_message_ids"
        ],
        valid=True,
    )

    log_event(
        "draft",
        cap="R2",
        target_message_id=message_id,
        cited_message_ids=result[
            "cited_message_ids"
        ],
    )

    print("\nDraft created: YES")

    print(
        "\nCited message ids:",
        result["cited_message_ids"]
    )

    print("\nDRAFT")
    print("-" * 70)
    print(
        result["draft"]
    )
    print("-" * 70)

    print(
        "\nCitation validation: PASSED"
    )

def run_r3(dry_run=False):
    print("=" * 70)
    print("R3 - GATE IRREVERSIBLE ACTIONS")
    print("=" * 70)

    ARTIFACTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    store = InboxStore()

    target = store.get_message(
        "m008"
    )

    if not target:
        print(
            "Demo message m008 "
            "was not found."
        )
        return

    # IMPORTANT:
    # The proposed recipient comes from the actual
    # message sender, not from an arbitrary address
    # embedded in the email body.
    proposal = ActionProposal(
        action_id="R3-m008-send",
        message_id="m008",
        action_type="send",
        reason=(
            "A reply has been proposed, but sending "
            "email is an irreversible external action."
        ),
        payload={
            "to": target["from"],
            "subject": (
                f"Re: {target['subject']}"
            ),
            "body": (
                "I found relevant information in the "
                "earlier thread. Because it contains "
                "sensitive credentials, I won't resend "
                "the secret over email. I can share it "
                "through an approved secure channel."
            ),
        },
    )

    print(
        f"Proposed action: "
        f"{proposal.action_type}"
    )

    print(
        f"Message: "
        f"{proposal.message_id}"
    )

    print(
        f"Recipient: "
        f"{proposal.payload['to']}"
    )

    print(
        f"Reason: "
        f"{proposal.reason}"
    )

    gate = ActionGate()

    result = gate.evaluate(
        proposal,
        dry_run=dry_run,
    )

    artifact = {
        **proposal.to_dict(),
        "dry_run": dry_run,
        "human_response":
            result.human_response,
        "allowed":
            result.allowed,
        "outcome":
            result.outcome,
    }

    if not result.allowed:
        PENDING_ACTIONS_FILE.write_text(
            json.dumps(
                [artifact],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        print()
        print(
            "Action executed: NO"
        )

        print(
            f"Outcome: {result.outcome}"
        )

        return

    executor = ActionExecutor()

    execution = executor.execute(
        proposal
    )

    artifact["execution"] = execution

    PENDING_ACTIONS_FILE.write_text(
        json.dumps(
            [artifact],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    log_event(
        "action_execution",
        cap="R3",
        action_id=proposal.action_id,
        message_id=proposal.message_id,
        action_type=proposal.action_type,
        outcome=execution["status"],
        output_file=execution[
            "output_file"
        ],
    )

    print()
    print(
        "Action executed: YES"
    )

    print(
        f"Output: "
        f"{execution['output_file']}"
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

    if args.cap == "R2":
        run_r2(
            args.msg or "m008"
        )
        return
    
    if args.cap == "R3":
        run_r3(
            dry_run=args.dry_run
        )
        return

    print(
        "Capability not implemented yet."
    )


if __name__ == "__main__":
    main()
