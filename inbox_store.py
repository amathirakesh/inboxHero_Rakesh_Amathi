import json
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INBOX_PATH = BASE_DIR / "inbox.json"


REQUIRED_FIELDS = {
    "id",
    "thread_id",
    "from",
    "to",
    "subject",
    "timestamp",
    "body",
    "unread",
}


class InboxValidationError(Exception):
    pass


class InboxStore:
    def __init__(self, inbox_path=None):
        self.inbox_path = (
            Path(inbox_path)
            if inbox_path
            else DEFAULT_INBOX_PATH
        )

        self.messages = []
        self.by_id = {}
        self.by_thread = defaultdict(list)

        self._load()
        self._validate()
        self._build_indexes()

    def _load(self):
        if not self.inbox_path.exists():
            raise InboxValidationError(
                f"Inbox file not found: {self.inbox_path}"
            )

        try:
            with self.inbox_path.open(
                "r",
                encoding="utf-8"
            ) as file:
                self.messages = json.load(file)

        except json.JSONDecodeError as exc:
            raise InboxValidationError(
                f"Invalid JSON in inbox file: {exc}"
            ) from exc

    def _validate(self):
        if not isinstance(self.messages, list):
            raise InboxValidationError(
                "inbox.json must contain a JSON array"
            )

        seen_ids = set()

        for index, message in enumerate(self.messages):
            if not isinstance(message, dict):
                raise InboxValidationError(
                    f"Message at index {index} is not an object"
                )

            missing = REQUIRED_FIELDS - message.keys()

            if missing:
                raise InboxValidationError(
                    f"Message at index {index} "
                    f"is missing fields: {sorted(missing)}"
                )

            message_id = message["id"]

            if not isinstance(message_id, str) or not message_id.strip():
                raise InboxValidationError(
                    f"Invalid id at index {index}"
                )

            if message_id in seen_ids:
                raise InboxValidationError(
                    f"Duplicate message id: {message_id}"
                )

            seen_ids.add(message_id)

            if not isinstance(message["unread"], bool):
                raise InboxValidationError(
                    f"{message_id}: unread must be boolean"
                )

            for field in (
                "thread_id",
                "from",
                "to",
                "subject",
                "timestamp",
                "body",
            ):
                if not isinstance(message[field], str):
                    raise InboxValidationError(
                        f"{message_id}: {field} must be a string"
                    )

    def _build_indexes(self):
        for message in self.messages:
            self.by_id[message["id"]] = message

            self.by_thread[
                message["thread_id"]
            ].append(message)

        # Keep thread messages chronological.
        for messages in self.by_thread.values():
            messages.sort(
                key=lambda item: item["timestamp"]
            )

    def all_messages(self):
        return list(self.messages)

    def get_message(self, message_id):
        return self.by_id.get(message_id)

    def get_thread(self, thread_id):
        return list(
            self.by_thread.get(thread_id, [])
        )

    def get_thread_for_message(self, message_id):
        message = self.get_message(message_id)

        if not message:
            return []

        return self.get_thread(
            message["thread_id"]
        )

    def unread_messages(self):
        return [
            message
            for message in self.messages
            if message["unread"]
        ]

    def count(self):
        return len(self.messages)