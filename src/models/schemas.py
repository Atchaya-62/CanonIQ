from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectionFieldConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    rename: str | None = None
    remove: bool = False
    normalize: bool = False
    required: bool = False
    default: object | None = None
    on_missing: Literal["omit", "null", "empty", "default", "error"] = "omit"
    on_error: Literal["omit", "null", "empty", "default", "error"] = "omit"


class ProjectionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    format: Literal["canonical", "custom"] = "canonical"
    fields: dict[str, ProjectionFieldConfig] = Field(default_factory=dict)
