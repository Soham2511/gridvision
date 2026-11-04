"""Authenticated per-request context. Only trusted host middleware may create it."""

from enum import Enum
from types import MappingProxyType
from typing import FrozenSet, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Persona(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    GOVERNMENT = "government"


class AuthenticatedRequestContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    principal_id: str = Field(min_length=1)
    persona: Persona
    permissions: FrozenSet[str] = frozenset()
    entity_scopes: Mapping[str, FrozenSet[str]] = Field(default_factory=dict)
    request_id: str = Field(min_length=1)

    @field_validator("permissions", mode="before")
    @classmethod
    def freeze_permissions(cls, value):
        return frozenset(value or ())

    @field_validator("entity_scopes", mode="before")
    @classmethod
    def freeze_scopes(cls, value):
        return {key: frozenset(ids) for key, ids in (value or {}).items()}

    def model_post_init(self, __context):
        object.__setattr__(self, "entity_scopes", MappingProxyType(dict(self.entity_scopes)))

    def allows_tool(self, name: str) -> bool:
        return name in self.permissions

    def allows_entity(self, kind: str, entity_id: str) -> bool:
        return bool(entity_id) and entity_id in self.entity_scopes.get(kind, frozenset())
