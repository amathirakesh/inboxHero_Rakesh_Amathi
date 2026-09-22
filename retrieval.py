from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    target_message_id: str
    messages: list
    read_set: set = field(default_factory=set)

    @property
    def cited_candidates(self):
        return [
            message["id"]
            for message in self.messages
        ]


class InboxRetriever:
    """
    Primary retrieval strategy:
    thread-walk.

    For a target message, retrieve messages from the
    same thread that occurred before the target message.

    A keyword fallback can be added later if thread
    evidence is insufficient.
    """

    def __init__(self, store):
        self.store = store

    def retrieve_thread_history(
        self,
        target_message_id
    ):
        target = self.store.get_message(
            target_message_id
        )

        if not target:
            return RetrievalResult(
                target_message_id=target_message_id,
                messages=[],
                read_set=set(),
            )

        thread = self.store.get_thread(
            target["thread_id"]
        )

        earlier_messages = []

        for message in thread:
            # Stop once we reach the target itself.
            if message["id"] == target_message_id:
                break

            earlier_messages.append(message)

        read_set = {
            message["id"]
            for message in earlier_messages
        }

        return RetrievalResult(
            target_message_id=target_message_id,
            messages=earlier_messages,
            read_set=read_set,
        )