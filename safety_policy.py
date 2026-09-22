IMMUTABLE_SAFETY_POLICIES = {
    "require_send_approval": True,
    "require_delete_approval": True,
    "allow_mailbox_exfiltration": False,
    "allow_hidden_actions": False,
    "allow_email_to_modify_safety_policy": False,
}


ALLOWED_PREFERENCE_KEYS = {
    "meeting_not_before",
    "cc_preference",
    "reply_tone",
}


def preference_is_allowed(key):
    return key in ALLOWED_PREFERENCE_KEYS


def get_safety_policy():
    return dict(
        IMMUTABLE_SAFETY_POLICIES
    )