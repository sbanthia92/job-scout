from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from job_scout.config import load_config

VALID_YAML = textwrap.dedent("""\
    search:
      queries:
        - software engineer
        - backend engineer
      locations:
        - "San Francisco, CA"
        - Remote
      date_posted: week
    scoring:
      threshold: 70
      alert_threshold: 90
    filters:
      deal_breakers:
        - blockchain
    gist:
      id: abc123gistid
      filename: seen_jobs.json
    email:
      from: scout@example.com
      to: me@example.com
""")


def test_load_valid_config(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(VALID_YAML)
    cfg = load_config(cfg_file)

    assert cfg.search.queries == ["software engineer", "backend engineer"]
    assert cfg.search.locations == ["San Francisco, CA", "Remote"]
    assert cfg.search.date_posted == "week"
    assert cfg.scoring.threshold == 70
    assert cfg.scoring.alert_threshold == 90
    assert cfg.filters.deal_breakers == ["blockchain"]
    assert cfg.gist.id == "abc123gistid"
    assert cfg.gist.filename == "seen_jobs.json"
    assert cfg.email.from_address == "scout@example.com"
    assert cfg.email.to == "me@example.com"


def test_load_config_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="config.yaml"):
        load_config(tmp_path / "config.yaml")


def test_load_config_missing_gist(tmp_path: Path) -> None:
    yaml_text = textwrap.dedent("""\
        search:
          queries: [software engineer]
          locations: [Remote]
        scoring:
          threshold: 70
          alert_threshold: 90
        email:
          from: scout@example.com
          to: me@example.com
    """)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    with pytest.raises(ValueError, match="gist"):
        load_config(cfg_file)


def test_load_config_missing_email(tmp_path: Path) -> None:
    yaml_text = textwrap.dedent("""\
        search:
          queries: [software engineer]
          locations: [Remote]
        scoring:
          threshold: 70
          alert_threshold: 90
        gist:
          id: abc123
    """)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    with pytest.raises(ValueError, match="email"):
        load_config(cfg_file)


def test_load_config_invalid_date_posted(tmp_path: Path) -> None:
    yaml_text = VALID_YAML.replace("date_posted: week", "date_posted: yesterday")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    with pytest.raises(ValueError, match="date_posted"):
        load_config(cfg_file)


def test_load_config_threshold_above_alert(tmp_path: Path) -> None:
    yaml_text = VALID_YAML.replace("threshold: 70", "threshold: 95")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    with pytest.raises(ValueError, match="threshold"):
        load_config(cfg_file)


def test_load_config_threshold_equal_alert(tmp_path: Path) -> None:
    yaml_text = VALID_YAML.replace("threshold: 70", "threshold: 90")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    with pytest.raises(ValueError, match="threshold"):
        load_config(cfg_file)


def test_load_config_filters_absent_defaults_empty(tmp_path: Path) -> None:
    yaml_text = textwrap.dedent("""\
        search:
          queries: [software engineer]
          locations: [Remote]
        scoring:
          threshold: 70
          alert_threshold: 90
        gist:
          id: abc123
        email:
          from: scout@example.com
          to: me@example.com
    """)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    cfg = load_config(cfg_file)
    assert cfg.filters.deal_breakers == []


def test_load_config_scoring_defaults(tmp_path: Path) -> None:
    yaml_text = textwrap.dedent("""\
        search:
          queries: [software engineer]
          locations: [Remote]
        gist:
          id: abc123
        email:
          from: scout@example.com
          to: me@example.com
    """)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_text)
    cfg = load_config(cfg_file)
    assert cfg.scoring.threshold == 70
    assert cfg.scoring.alert_threshold == 90


def test_load_config_invalid_yaml_type(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- item1\n- item2\n")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(cfg_file)
