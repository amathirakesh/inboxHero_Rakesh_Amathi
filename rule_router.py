from models import Decision


AUTOMATED_SENDER_HINTS = (
    "no-reply",
    "noreply",
    "notifications",
    "notification",
    "alerts",
    "receipts",
    "receipt",
    "billing",
    "invoice",
)


ARCHIVE_SUBJECT_HINTS = (
    "receipt",
    "monthly summary",
    "weekly analytics",
    "screen time report",
    "campaign report",
    "usage",
    "statement is available",
    "order has shipped",
    "order is delivered",
    "cloud recording is ready",
    "monthly invoice",
    "invoice paid",
    "weekly digest",
)


ARCHIVE_BODY_HINTS = (
    "no action needed",
    "for your records only",
    "thanks for your purchase",
    "payment of",
    "charged to your card",
    "was charged",
    "view your invoice",
    "see full stats",
)


# If any of these appear, do NOT auto-archive using the cheap rules.
# They require model/safety processing.
RISK_HINTS = (
    "wire",
    "bank",
    "routing",
    "account:",
    "password",
    "verification code",
    "credential",
    "creds",
    "amqp://",
    "meeting",
    "calendar",
    "approve",
    "approval",
    "signature",
    "sign",
    "deadline",
    "urgent",
    "confidential",
    "forward",
    "delete",
    "assistant",
    "system notice",
    "directive",
    "remember",
    "cc'd",
    "cc ",
)


REQUEST_HINTS = (
    "can you",
    "could you",
    "would you",
    "please ",
    "need you",
    "do you want",
    "does ",
    "reply ",
    "confirm",
    "reschedule",
)


def _combined_text(message):
    return " ".join([
        message.get("from", ""),
        message.get("subject", ""),
        message.get("body", ""),
    ]).lower()


def _has_any(text, values):
    return any(
        value in text
        for value in values
    )


def route_by_rule(message):
    """
    Return a Decision if the message is safe and obvious
    enough to classify deterministically.

    Return None when model/reasoning is required.
    """

    text = _combined_text(message)

    # Safety-first: risky or action-oriented content should
    # not be auto-archived by a broad noise rule.
    if _has_any(text, RISK_HINTS):
        return None

    if _has_any(text, REQUEST_HINTS):
        return None

    subject = message["subject"].lower()
    body = message["body"].lower()
    sender = message["from"].lower()

    if _has_any(subject, ARCHIVE_SUBJECT_HINTS):
        return Decision(
            message_id=message["id"],
            disposition="archive",
            reason=(
                "Informational automated message with no "
                "clear action required."
            ),
            handled_by="rule",
            rule_name="informational_subject"
        )

    if _has_any(body, ARCHIVE_BODY_HINTS):
        return Decision(
            message_id=message["id"],
            disposition="archive",
            reason=(
                "Message explicitly indicates that it is "
                "informational or requires no action."
            ),
            handled_by="rule",
            rule_name="informational_body"
        )

    if (
        _has_any(sender, AUTOMATED_SENDER_HINTS)
        and not message["unread"]
    ):
        return Decision(
            message_id=message["id"],
            disposition="archive",
            reason=(
                "Previously read automated notification "
                "with no detected request or risk signal."
            ),
            handled_by="rule",
            rule_name="read_automated_notification"
        )

    return None