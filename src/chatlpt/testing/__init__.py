"""Test doubles that implement the protocols with contract types. Shipped so tests never mock internals."""

from chatlpt.testing.fakes import (
    FixedClock,
    MemoryImageFiles,
    MemoryStore,
    PlainHasher,
    ScriptedBackend,
    ScriptedImageBackend,
    StaticImagePrices,
    StaticPrices,
)

__all__ = [
    "FixedClock",
    "MemoryImageFiles",
    "MemoryStore",
    "PlainHasher",
    "ScriptedBackend",
    "ScriptedImageBackend",
    "StaticImagePrices",
    "StaticPrices",
]
