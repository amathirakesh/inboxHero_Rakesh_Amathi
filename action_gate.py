from dataclasses import dataclass

from actions import (
    is_irreversible,
)

from audit_trace import log_event


@dataclass
class GateResult:
    allowed: bool
    human_response: str
    outcome: str


class ActionGate:

    def evaluate(
        self,
        proposal,
        dry_run=False,
    ):
        irreversible = is_irreversible(
            proposal.action_type
        )

        log_event(
            "gate_proposed",
            cap="R3",
            action_id=proposal.action_id,
            message_id=proposal.message_id,
            action_type=proposal.action_type,
            irreversible=irreversible,
            reason=proposal.reason,
        )

        # Reversible actions do not require approval.
        if not irreversible:
            result = GateResult(
                allowed=True,
                human_response=(
                    "not_required"
                ),
                outcome=(
                    "reversible_action_allowed"
                ),
            )

            self._log_result(
                proposal,
                result
            )

            return result

        # Dry-run NEVER performs an irreversible action.
        if dry_run:
            result = GateResult(
                allowed=False,
                human_response=(
                    "not_requested_dry_run"
                ),
                outcome=(
                    "blocked_by_dry_run"
                ),
            )

            self._log_result(
                proposal,
                result
            )

            return result

        print()
        print("=" * 60)
        print("HUMAN APPROVAL REQUIRED")
        print("=" * 60)

        print(
            f"Message: "
            f"{proposal.message_id}"
        )

        print(
            f"Action: "
            f"{proposal.action_type}"
        )

        print(
            f"Reason: "
            f"{proposal.reason}"
        )

        print()

        response = input(
            "Approve this action? [y/N]: "
        ).strip().lower()

        approved = response in {
            "y",
            "yes",
        }

        if approved:
            result = GateResult(
                allowed=True,
                human_response=response,
                outcome="approved",
            )

        else:
            result = GateResult(
                allowed=False,
                human_response=(
                    response or "no"
                ),
                outcome="denied",
            )

        self._log_result(
            proposal,
            result
        )

        return result

    def _log_result(
        self,
        proposal,
        result,
    ):
        log_event(
            "gate_decision",
            cap="R3",
            action_id=proposal.action_id,
            message_id=proposal.message_id,
            action_type=proposal.action_type,
            human_response=(
                result.human_response
            ),
            allowed=result.allowed,
            outcome=result.outcome,
        )