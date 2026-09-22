from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
import json


BASE_DIR = Path(__file__).resolve().parent
OUTBOX_DIR = BASE_DIR / "outbox"


class ActionType(str, Enum):
    SEND = "send"
    DELETE = "delete"
    EXTERNAL_COMMITMENT = "external_commitment"
    FINANCIAL_ACTION = "financial_action"

    DRAFT = "draft"
    ARCHIVE = "archive"
    LABEL = "label"
    DEFER = "defer"
    FLAG = "flag"


IRREVERSIBLE_ACTIONS = {
    ActionType.SEND.value,
    ActionType.DELETE.value,
    ActionType.EXTERNAL_COMMITMENT.value,
    ActionType.FINANCIAL_ACTION.value,
}


REVERSIBLE_ACTIONS = {
    ActionType.DRAFT.value,
    ActionType.ARCHIVE.value,
    ActionType.LABEL.value,
    ActionType.DEFER.value,
    ActionType.FLAG.value,
}


@dataclass
class ActionProposal:
    action_id: str
    message_id: str
    action_type: str
    reason: str
    payload: dict

    def to_dict(self):
        return asdict(self)


def is_irreversible(action_type):
    return action_type in IRREVERSIBLE_ACTIONS


class ActionExecutor:
    """
    The only component allowed to perform side effects.

    For this assignment, sending an email means writing
    one JSON file per message into outbox/.
    """

    def __init__(self):
        OUTBOX_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

    def execute(self, proposal):
        if proposal.action_type == ActionType.SEND.value:
            return self._send(proposal)

        raise ValueError(
            f"Execution not implemented for "
            f"{proposal.action_type}"
        )

    def _send(self, proposal):
        message_id = proposal.message_id

        output_file = (
            OUTBOX_DIR /
            f"{message_id}.json"
        )

        record = {
            "action_id":
                proposal.action_id,

            "message_id":
                message_id,

            "action":
                "send",

            "to":
                proposal.payload["to"],

            "subject":
                proposal.payload["subject"],

            "body":
                proposal.payload["body"],

            "executed_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),
        }

        output_file.write_text(
            json.dumps(
                record,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return {
            "status": "executed",
            "output_file": str(
                output_file
            ),
        }