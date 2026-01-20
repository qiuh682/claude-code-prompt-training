"""Base classes for ML models."""

from abc import ABC, abstractmethod
from typing import Any


class BaseMLModel(ABC):
    """Abstract base class for all ML models."""

    @abstractmethod
    def load(self, path: str) -> None:
        """Load model from path."""
        pass

    @abstractmethod
    def predict(self, inputs: Any) -> Any:
        """Make predictions on inputs."""
        pass

    @abstractmethod
    def save(self, path: str) -> None:
        """Save model to path."""
        pass
