from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal


class ToolDefinition(ABC):
    name: str
    label: str
    icon: str
    description: str
    security_level: Literal["safe", "approval", "unsafe"] = "safe"
    primary_param: str | None = None

    @abstractmethod
    def execute(self, action: dict, config, **ctx) -> str:
        ...
