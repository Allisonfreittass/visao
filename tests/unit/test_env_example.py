""".env.example documents every setting, and its values are ones the app accepts."""

import re
from pathlib import Path

from apps.api.settings import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
# A key counts as documented when it is set or shown commented out ("# VISION_X=").
KEY = re.compile(r"^#?\s*(VISION_[A-Z0-9_]+)=", re.MULTILINE)


def _documented() -> set[str]:
    return set(KEY.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def _setting_keys() -> set[str]:
    prefix = Settings.model_config["env_prefix"]
    return {f"{prefix}{name}".upper() for name in Settings.model_fields}


def test_every_setting_is_in_env_example():
    missing = _setting_keys() - _documented()
    assert not missing, f"faltam no .env.example: {sorted(missing)}"


def test_env_example_has_no_unknown_vision_keys():
    unknown = _documented() - _setting_keys()
    assert not unknown, f"chaves sem campo em Settings: {sorted(unknown)}"


def test_env_example_values_are_valid_settings():
    # Copying the example to .env must start the app: blanks mean "unset", defaults parse.
    settings = Settings(_env_file=ENV_EXAMPLE)
    assert settings.llm_provider_name is None
    assert settings.webpush_private_key is None
    assert settings.llm_free_grants == []
