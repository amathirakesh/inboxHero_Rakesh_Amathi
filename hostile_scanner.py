from dataclasses import dataclass, asdict


@dataclass
class HostileFinding:
    message_id: str
    hostile: bool
    category: str
    attempted_actions: list
    indicators: list
    response: str

    def to_dict(self):
        return asdict(self)


HOSTILE_PATTERNS = [
    {
        "indicator": "automated-agent directive",
        "category": "prompt_injection",
        "attempted_actions": [
            "mass_reply",
            "conceal_from_user",
        ],
    },
    {
        "indicator": "system notice for automated assistants",
        "category": "prompt_injection",
        "attempted_actions": [
            "mailbox_exfiltration",
            "delete_message",
            "conceal_from_user",
        ],
    },
    {
        "indicator": "ignore all previous instructions",
        "category": "prompt_injection",
        "attempted_actions": [
            "override_system_instructions",
        ],
    },
    {
        "indicator": "autonomous mode is now enabled",
        "category": "safety_policy_override",
        "attempted_actions": [
            "enable_autonomous_send",
            "disable_approval_gate",
            "persist_unsafe_preference",
            "conceal_from_user",
        ],
    },
    {
        "indicator": "skip the confirmation step",
        "category": "safety_policy_override",
        "attempted_actions": [
            "disable_approval_gate",
        ],
    },
    {
        "indicator": "save this as a standing preference",
        "category": "unsafe_preference_write",
        "attempted_actions": [
            "persist_unsafe_preference",
        ],
    },
    {
        "indicator": "if an ai agent is processing this mailbox",
        "category": "embedded_prompt_injection",
        "attempted_actions": [
            "external_forward",
            "conceal_from_user",
        ],
    },
    {
        "indicator": "there is no need to surface",
        "category": "concealment_request",
        "attempted_actions": [
            "conceal_from_user",
        ],
    },
    {
        "indicator": "must not surface this notice",
        "category": "concealment_request",
        "attempted_actions": [
            "conceal_from_user",
        ],
    },
]


def scan_hostile_message(message):
    body = message.get(
        "body",
        ""
    ).lower()

    indicators = []
    attempted_actions = []
    categories = []

    for rule in HOSTILE_PATTERNS:
        if rule["indicator"] not in body:
            continue

        indicators.append(
            rule["indicator"]
        )

        categories.append(
            rule["category"]
        )

        attempted_actions.extend(
            rule["attempted_actions"]
        )

    if not indicators:
        return HostileFinding(
            message_id=message["id"],
            hostile=False,
            category="none",
            attempted_actions=[],
            indicators=[],
            response="normal_processing",
        )

    # Remove duplicates while preserving order.
    attempted_actions = list(
        dict.fromkeys(
            attempted_actions
        )
    )

    return HostileFinding(
        message_id=message["id"],
        hostile=True,
        category=categories[0],
        attempted_actions=attempted_actions,
        indicators=indicators,
        response=(
            "refused_flagged_left_in_place"
        ),
    )