"""Protocols, ABCs, and utility classes for testing."""

from abc import ABC, abstractmethod
from typing import Protocol


class Serializer(Protocol):
    def serialize(self, data: dict) -> str: ...
    def deserialize(self, raw: str) -> dict: ...


class BaseProcessor(ABC):
    @abstractmethod
    def process(self, item: dict) -> dict:
        pass

    @abstractmethod
    def validate(self, item: dict) -> bool:
        pass


class ItemProcessor(BaseProcessor):
    def process(self, item: dict) -> dict:
        return {"processed": True, **item}

    def validate(self, item: dict) -> bool:
        return "id" in item


def format_date(timestamp: float) -> str:
    """Format a timestamp as ISO date."""
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).isoformat()


def helper_function(x: int, y: int) -> int:
    """Simple helper."""
    return x + y


def _private_helper():
    """Should not be detected in non-deep mode."""
    pass
