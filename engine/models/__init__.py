"""
engine/models/ -- Pydantic v2 models for the Worldbuilding Interactive Program.

Submodules:
    base        Base models (EntityMeta, WorldEntity) with shared fields.
    factory     Dynamic model generation from JSON Schema template files.
    validators  Custom worldbuilding validators (cross-refs, names, etc.).
"""

from engine.models.base import EntityMeta, WorldEntity

__all__ = ["EntityMeta", "WorldEntity"]
