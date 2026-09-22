from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class Disposition(str, Enum):
    REPLY = "reply"
    ARCHIVE = "archive"
    DEFER = "defer"
    DELEGATE = "delegate"
    ESCALATE = "escalate"


VALID_DISPOSITIONS = {
    item.value
    for item in Disposition
}


@dataclass
class Decision:
    message_id: str
    disposition: str
    reason: str
    handled_by: str
    rule_name: Optional[str] = None

    def to_dict(self):
        return asdict(self)