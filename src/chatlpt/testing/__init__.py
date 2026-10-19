"""Test doubles that implement the protocols with contract types. Shipped so tests never mock internals."""

from chatlpt.testing.fakes import FixedClock, MemoryStore, PlainHasher, ScriptedBackend, StaticPrices

__all__ = ["FixedClock", "MemoryStore", "PlainHasher", "ScriptedBackend", "StaticPrices"]
