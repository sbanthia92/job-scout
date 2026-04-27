from __future__ import annotations

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class SearchConfig(BaseModel):
    queries: list[str]
    locations: list[str]
    date_posted: str = "week"

    @model_validator(mode="after")
    def _validate_date_posted(self) -> Self:
        valid = {"today", "week", "month"}
        if self.date_posted not in valid:
            raise ValueError(
                f"date_posted must be one of {sorted(valid)!r}, got {self.date_posted!r}"
            )
        return self


class ScoringConfig(BaseModel):
    threshold: int = Field(default=70, ge=0, le=100)
    alert_threshold: int = Field(default=90, ge=0, le=100)

    @model_validator(mode="after")
    def _threshold_below_alert(self) -> Self:
        if self.threshold >= self.alert_threshold:
            raise ValueError(
                f"threshold ({self.threshold}) must be less than "
                f"alert_threshold ({self.alert_threshold})"
            )
        return self


class FiltersConfig(BaseModel):
    deal_breakers: list[str] = Field(default_factory=list)


class GistConfig(BaseModel):
    id: str
    filename: str = "seen_jobs.json"


class EmailConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_address: str = Field(alias="from")
    to: str


class Config(BaseModel):
    search: SearchConfig
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    gist: GistConfig
    email: EmailConfig


def load_config(path: Path | str = "config.yaml") -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and fill in your values."
        )

    with config_path.open() as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Config must be a YAML mapping, got {type(raw).__name__}"
        )

    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        lines = [f"Invalid configuration in {config_path}:"]
        for error in exc.errors():
            loc = " → ".join(str(p) for p in error["loc"])
            lines.append(f"  {loc}: {error['msg']}")
        raise ValueError("\n".join(lines)) from exc
