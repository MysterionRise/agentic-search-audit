"""Configuration loading and management."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .types import AuditConfig


def load_yaml(file_path: Path) -> dict[str, Any]:
    """Load YAML configuration file.

    Args:
        file_path: Path to YAML file

    Returns:
        Parsed YAML as dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If YAML is invalid
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Config file not found: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two configuration dictionaries.

    Args:
        base: Base configuration
        override: Override configuration (takes precedence)

    Returns:
        Merged configuration
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def load_config(
    config_path: Path | None = None,
    site_config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> AuditConfig:
    """Load and merge configuration from files and overrides.

    Args:
        config_path: Path to base config file (default: configs/default.yaml)
        site_config_path: Path to site-specific config file
        overrides: Additional runtime overrides

    Returns:
        Validated AuditConfig instance

    Raises:
        ValidationError: If configuration is invalid
    """
    # Load base config
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent.parent / "configs" / "default.yaml"

    if config_path.exists():
        config_dict = load_yaml(config_path)
    else:
        config_dict = {}

    # Merge site-specific config
    if site_config_path and site_config_path.exists():
        site_dict = load_yaml(site_config_path)
        config_dict = merge_configs(config_dict, site_dict)

    # Apply runtime overrides
    if overrides:
        config_dict = merge_configs(config_dict, overrides)

    # Validate and return
    try:
        return AuditConfig(**config_dict)
    except ValidationError as e:
        raise ValidationError(f"Invalid configuration: {e}") from e


def get_run_dir(base_dir: Path, site_name: str) -> Path:
    """Create a timestamped run directory.

    Args:
        base_dir: Base output directory
        site_name: Site being audited (for subdirectory)

    Returns:
        Path to created run directory
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / site_name / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    (run_dir / "screenshots").mkdir(exist_ok=True)
    (run_dir / "html_snapshots").mkdir(exist_ok=True)

    return run_dir
