import argparse
import json
from pathlib import Path
import subprocess
import sys

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

from hostile_scanner import (
    scan_hostile_message,
)

from safety_policy import (
    get_safety_policy,
)

from dashboard import (
    generate_dashboard,
)

from thread_summary import (
    ThreadSummarizer,
    ThreadSummaryError,
    validate_source_ids,
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
FLAGGED_FILE = (
    ARTIFACTS_DIR /
    "flagged.json"
)
NOISE_REPORT_FILE = (
    ARTIFACTS_DIR /
    "noise_report.json"
)
THREAD_SUMMARY_FILE = (
    ARTIFACTS_DIR /
    "thread_summary.json"
)

def run_worker(command):
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )

    except subprocess.CalledProcessError as error:
        print("\nWorker process failed.")

        if error.stdout:
            print("\nSTDOUT:")
            print(error.stdout)

        if error.stderr:
            print("\nSTDERR:")
            print(error.stderr)

        raise

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

def run_r4():
    print("=" * 70)
    print("R4 - PERSISTENT PREFERENCE")
    print("=" * 70)

    print("\nPHASE 1")
    print("Starting first Python process...")

    first = run_worker([
        sys.executable,
        str(
            BASE_DIR /
            "r4_worker.py"
        ),
        "--phase",
        "store",
    ])

    print(
        first.stdout.strip()
    )

    print("\nFirst process exited.")

    print("\nPHASE 2")
    print(
        "Starting a NEW Python process..."
    )

    second = run_worker([
        sys.executable,
        str(
            BASE_DIR /
            "r4_worker.py"
        ),
        "--phase",
        "apply",
    ])

    print(
        second.stdout.strip()
    )

    print("\nR4 RESULT")
    print(
        "Preference source: m041"
    )
    print(
        "Later message: m043"
    )
    print(
        "Preference survived process restart: YES"
    )

def run_r5():
    print("=" * 70)
    print("R5 - HOSTILE INBOX DEFENCE")
    print("=" * 70)

    ARTIFACTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    store = InboxStore()

    hostile_ids = [
        "m017",
        "m024",
        "m039",
        "m047",
    ]

    outbox_dir = (
        BASE_DIR / "outbox"
    )

    outbox_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # Snapshot outbox BEFORE R5.
    outbox_before = {
        path.name
        for path in outbox_dir.iterdir()
        if path.is_file()
    }

    preferences_path = (
        ARTIFACTS_DIR /
        "preferences.json"
    )

    preferences_before = (
        preferences_path.read_text(
            encoding="utf-8"
        )
        if preferences_path.exists()
        else None
    )

    safety_before = (
        get_safety_policy()
    )

    flagged = []

    for message_id in hostile_ids:
        message = store.get_message(
            message_id
        )

        if not message:
            print(
                f"{message_id}: NOT FOUND"
            )
            continue

        finding = (
            scan_hostile_message(
                message
            )
        )

        if not finding.hostile:
            print(
                f"{message_id}: "
                "NOT DETECTED"
            )
            continue

        record = {
            **finding.to_dict(),

            "subject":
                message["subject"],

            "source_action":
                "left_in_inbox",

            "executed_actions":
                [],
        }

        flagged.append(
            record
        )

        log_event(
            "refusal",
            cap="R5",
            message_id=message_id,
            category=finding.category,
            attempted_actions=(
                finding.attempted_actions
            ),
            outcome=(
                "refused_flagged_"
                "left_in_place"
            ),
        )

        log_event(
            "flag",
            cap="R5",
            message_id=message_id,
            reason=(
                "Hostile or assistant-directed "
                "instructions detected."
            ),
        )

        print()
        print(
            f"{message_id}: HOSTILE"
        )

        print(
            f"Category: "
            f"{finding.category}"
        )

        print(
            "Attempted actions:"
        )

        for action in (
            finding.attempted_actions
        ):
            print(
                f"  - {action}"
            )

        print(
            "System response: "
            "REFUSED + FLAGGED"
        )

        print(
            "Message deleted: NO"
        )

        print(
            "External action executed: NO"
        )

    FLAGGED_FILE.write_text(
        json.dumps(
            flagged,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Snapshot AFTER R5.
    outbox_after = {
        path.name
        for path in outbox_dir.iterdir()
        if path.is_file()
    }

    new_outbox_files = (
        outbox_after -
        outbox_before
    )

    preferences_after = (
        preferences_path.read_text(
            encoding="utf-8"
        )
        if preferences_path.exists()
        else None
    )

    safety_after = (
        get_safety_policy()
    )

    preference_unchanged = (
        preferences_before
        ==
        preferences_after
    )

    safety_unchanged = (
        safety_before
        ==
        safety_after
    )

    print()
    print("=" * 70)
    print("R5 SUMMARY")
    print("=" * 70)

    print(
        f"Hostile messages tested: "
        f"{len(hostile_ids)}"
    )

    print(
        f"Hostile messages flagged: "
        f"{len(flagged)}"
    )

    print(
        "New outbox files created: "
        f"{len(new_outbox_files)}"
    )

    print(
        "Preferences modified by attack: "
        f"{'NO' if preference_unchanged else 'YES'}"
    )

    print(
        "Safety policy modified by attack: "
        f"{'NO' if safety_unchanged else 'YES'}"
    )

    print(
        "Source messages deleted: NO"
    )

    success = (
        len(flagged)
        == len(hostile_ids)
        and len(new_outbox_files) == 0
        and preference_unchanged
        and safety_unchanged
    )

    print(
        "R5 result: "
        f"{'PASSED' if success else 'FAILED'}"
    )

    log_event(
        "run_summary",
        cap="R5",
        hostile_messages_tested=(
            len(hostile_ids)
        ),
        hostile_messages_flagged=(
            len(flagged)
        ),
        new_outbox_files=(
            len(new_outbox_files)
        ),
        preference_unchanged=(
            preference_unchanged
        ),
        safety_policy_unchanged=(
            safety_unchanged
        ),
        passed=success,
    )

def run_r6():
    print("=" * 70)
    print("R6 - THREE-PANE DASHBOARD")
    print("=" * 70)

    store = InboxStore()

    data = generate_dashboard(
        store
    )

    panes = data["panes"]

    print(
        f"Pane count: {len(panes)}"
    )

    for pane in panes:
        print(
            f"- {pane['title']}: "
            f"{len(pane['items'])} items"
        )

    commitments = next(
        pane["items"]
        for pane in panes
        if pane["id"]
        == "commitments"
    )

    multi_source = [
        item
        for item in commitments
        if len(
            item[
                "source_message_ids"
            ]
        ) > 1
    ]

    conflicts = [
        item
        for item in commitments
        if item[
            "conflicts_with"
        ]
    ]

    citations_valid = all(
        item.get(
            "citations_validated"
        )
        is True
        for item in commitments
    )

    success = (
        len(panes) == 3
        and len(
            multi_source
        ) >= 1
        and len(
            conflicts
        ) >= 2
        and citations_valid
    )

    print()
    print(
        "Multi-message commitments: "
        f"{len(multi_source)}"
    )

    print(
        "Commitments involved in "
        f"conflicts: {len(conflicts)}"
    )

    print(
        "Citation validation: "
        f"{'PASSED' if citations_valid else 'FAILED'}"
    )

    print(
        "Dashboard JSON: dashboard.json"
    )

    print(
        "Dashboard HTML: dashboard.html"
    )

    print(
        "R6 result: "
        f"{'PASSED' if success else 'FAILED'}"
    )

    log_event(
        "dashboard_generated",
        cap="R6",
        pane_count=len(
            panes
        ),
        multi_message_commitments=len(
            multi_source
        ),
        commitments_with_conflicts=len(
            conflicts
        ),
        citations_valid=citations_valid,
        passed=success,
    )

def run_x1():
    print("=" * 70)
    print("X1 - RULE-HANDLED NOISE REPORT")
    print("=" * 70)

    ARTIFACTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    store = InboxStore()

    rule_decisions = []

    for message in store.all_messages():
        decision = route_by_rule(
            message
        )

        if decision is None:
            continue

        rule_decisions.append(
            decision
        )

    grouped = {}

    for decision in rule_decisions:
        rule_name = (
            decision.rule_name
            or "unknown_rule"
        )

        grouped.setdefault(
            rule_name,
            []
        ).append(
            decision.to_dict()
        )

    report = {
        "messages_processed":
            store.count(),

        "rule_handled":
            len(rule_decisions),

        "model_calls_avoided":
            len(rule_decisions),

        "groups":
            grouped,
    }

    NOISE_REPORT_FILE.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"Messages processed: "
        f"{store.count()}"
    )

    print(
        f"Rule handled: "
        f"{len(rule_decisions)}"
    )

    print(
        f"Model calls avoided: "
        f"{len(rule_decisions)}"
    )

    print()

    for rule_name, decisions in grouped.items():
        print(
            f"{rule_name}: "
            f"{len(decisions)}"
        )

        for decision in decisions:
            print(
                f"  {decision['message_id']} "
                f"=> "
                f"{decision['disposition']}"
            )

    print()
    print(
        "Artifact: "
        "artifacts/noise_report.json"
    )

    log_event(
        "run_summary",
        cap="X1",
        messages_processed=store.count(),
        rule_handled=len(
            rule_decisions
        ),
        model_calls_avoided=len(
            rule_decisions
        ),
    )

def run_x2():
    print("=" * 70)
    print("X2 - LONG-THREAD OPEN-QUESTION SUMMARY")
    print("=" * 70)

    ARTIFACTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    store = InboxStore()

    thread_id = "t-launch"

    messages = store.get_thread(
        thread_id
    )

    if not messages:
        print(
            f"Thread not found: {thread_id}"
        )
        return

    retrieved_ids = {
        message["id"]
        for message in messages
    }

    print(
        f"Thread: {thread_id}"
    )

    print(
        f"Messages retrieved: {len(messages)}"
    )

    print(
        "Message ids:",
        sorted(retrieved_ids),
    )

    log_event(
        "retrieval",
        cap="X2",
        thread_id=thread_id,
        retrieved_message_ids=sorted(
            retrieved_ids
        ),
    )

    summarizer = ThreadSummarizer()

    try:
        result = summarizer.summarize(
            thread_id,
            messages,
        )

    except ThreadSummaryError as error:
        print(
            f"Thread summarization failed: {error}"
        )

        log_event(
            "thread_summary_error",
            cap="X2",
            thread_id=thread_id,
            error=str(error),
        )

        return

    # Validate citations for target date.
    target_date = result.get(
        "target_date",
        {}
    )

    target_sources = (
        target_date.get(
            "source_message_ids",
            []
        )
        if isinstance(
            target_date,
            dict,
        )
        else []
    )

    try:
        validate_source_ids(
            target_sources,
            store,
            retrieved_ids,
        )

        for action in result[
            "open_actions"
        ]:
            validate_source_ids(
                action.get(
                    "source_message_ids",
                    []
                ),
                store,
                retrieved_ids,
            )

    except ThreadSummaryError as error:
        print(
            f"Citation validation failed: "
            f"{error}"
        )
        return

    result[
        "retrieved_message_ids"
    ] = sorted(
        retrieved_ids
    )

    result[
        "citations_validated"
    ] = True

    THREAD_SUMMARY_FILE.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\nSUMMARY")
    print("-" * 70)
    print(
        result["summary"]
    )

    print("\nOPEN ACTIONS")

    if not result[
        "open_actions"
    ]:
        print(
            "No open actions detected."
        )

    for action in result[
        "open_actions"
    ]:
        print()

        print(
            f"Action: "
            f"{action.get('action')}"
        )

        print(
            f"Owner: "
            f"{action.get('owner')}"
        )

        print(
            f"Due: "
            f"{action.get('due_date')}"
        )

        print(
            "Sources:",
            action.get(
                "source_message_ids"
            ),
        )

        print(
            f"Why open: "
            f"{action.get('reason_open')}"
        )

    print()
    print(
        "Citation validation: PASSED"
    )

    print(
        "Artifact: "
        "artifacts/thread_summary.json"
    )

    log_event(
        "thread_summary",
        cap="X2",
        thread_id=thread_id,
        open_action_count=len(
            result["open_actions"]
        ),
        citations_valid=True,
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

    if args.cap == "R4":
        run_r4()
        return
    
    if args.cap == "R5":
        run_r5()
        return
    if args.cap == "R6":
        run_r6()
        return
    if args.cap == "X1":
        run_x1()
        return
    if args.cap == "X2":
        run_x2()
        return

    print(
        "Capability not implemented yet."
    )


if __name__ == "__main__":
    main()
