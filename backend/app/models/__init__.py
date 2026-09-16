"""ORM model registry.

Importing this package registers every mapped table on ``Base.metadata``.
"""

from backend.app.models import entities as entities

__all__ = ["entities"]
