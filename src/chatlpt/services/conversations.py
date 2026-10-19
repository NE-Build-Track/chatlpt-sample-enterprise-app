"""Conversation rules: ownership, titles, listing and deletion (docs/product-specs/chatlpt.md#chat)."""

from uuid import UUID

from chatlpt.contracts import Conversation, Message, ThinkingLevel, User
from chatlpt.errors import NotFound
from chatlpt.protocols import Clock, ConversationStore
from chatlpt.utils import new_id

NEW_TITLE = "New chat"
TITLE_MAX = 60


def title_from(text: str) -> str:
    """The first user message, trimmed, is the title (D16)."""
    line = " ".join(text.strip().split())
    return line if len(line) <= TITLE_MAX else line[: TITLE_MAX - 1].rstrip() + "…"


class ConversationService:
    def __init__(
        self, store: ConversationStore, clock: Clock, *, default_thinking: ThinkingLevel = "medium"
    ) -> None:
        self._store = store
        self._clock = clock
        self._default_thinking = default_thinking

    async def create(self, user: User) -> Conversation:
        now = self._clock.now()
        conversation = Conversation(
            id=new_id(),
            user_id=user.id,
            title=NEW_TITLE,
            thinking=self._default_thinking,
            created_at=now,
            updated_at=now,
        )
        await self._store.create_conversation(conversation)
        return conversation

    async def list_for(self, user: User) -> list[Conversation]:
        return await self._store.list_conversations(user.id)

    async def get(self, user: User, conversation_id: UUID) -> Conversation:
        conversation = await self._store.get_conversation(conversation_id)
        if conversation is None or conversation.user_id != user.id:
            raise NotFound("conversation not found")  # never reveals another user's records
        return conversation

    async def rename(self, user: User, conversation_id: UUID, title: str) -> Conversation:
        conversation = await self.get(user, conversation_id)
        now = self._clock.now()
        await self._store.rename_conversation(conversation.id, title, now)
        return conversation.model_copy(update={"title": title, "updated_at": now})

    async def set_thinking(self, user: User, conversation_id: UUID, thinking: ThinkingLevel) -> Conversation:
        conversation = await self.get(user, conversation_id)
        await self._store.set_thinking(conversation.id, thinking)
        return conversation.model_copy(update={"thinking": thinking})

    async def delete(self, user: User, conversation_id: UUID) -> None:
        conversation = await self.get(user, conversation_id)
        await self._store.delete_conversation(conversation.id)

    async def messages(self, user: User, conversation_id: UUID) -> list[Message]:
        conversation = await self.get(user, conversation_id)
        return await self._store.list_messages(conversation.id)
