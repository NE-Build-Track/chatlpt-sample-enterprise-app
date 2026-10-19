"""History as the model sees it (D24, D25), and the tool the assistant may call."""

from collections.abc import Sequence
from uuid import UUID

from chatlpt.contracts import ChatTurn, Message, ToolSpec
from chatlpt.services.images import SIZES

GENERATE_IMAGE = ToolSpec(
    name="generate_image",
    description=(
        "Generate an image from a text prompt. Call this whenever the user asks you to draw, paint, render, "
        "illustrate, sketch or create a picture or photo. Write a vivid, specific prompt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "A detailed description of the image to generate"},
            "image_size": {"type": "string", "enum": sorted(SIZES), "description": "Aspect ratio and size"},
        },
        "required": ["prompt"],
    },
)


def turns_from(messages: Sequence[Message]) -> list[ChatTurn]:
    """History as the model should see it: continuation segments fold into the message they extend."""
    turns: list[ChatTurn] = []
    for message in messages:
        if message.role in ("system", "tool"):
            continue
        content = message.content
        if message.kind == "tool_call":
            prompts = [i.prompt for i in message.images] or [
                str(c.arguments.get("prompt", "")) for c in message.tool_calls
            ]
            content = "\n".join(f"[Generated an image from the prompt: {p}]" for p in prompts if p)
        if not content:
            continue
        if message.role == "assistant" and turns and turns[-1].role == "assistant":
            glue = "" if message.continues_message_id is not None else "\n"
            turns[-1] = ChatTurn(role="assistant", content=turns[-1].content + glue + content)
            continue
        turns.append(ChatTurn(role=message.role, content=content))
    return turns


def chain_text(messages: Sequence[Message], message_id: UUID) -> str:
    """The text of an assistant message plus every continuation that already extends it."""
    text = ""
    for message in messages:
        if message.id == message_id or message.continues_message_id == message_id:
            text += message.content
    return text
