"""The Cloudflare edge forwards an explicit allowlist of variables into the Python container.
A setting missing from that list is silently dropped in production, so keep them in sync."""

import json
import re
from pathlib import Path

from apps.api.settings import Settings

ROOT = Path(__file__).resolve().parents[2] / "infrastructure" / "cloudflare"
# Local model paths stay at their image defaults at the edge.
NOT_FORWARDED = {"VISION_TTS_MODELS_DIR", "VISION_STT_MODELS_DIR"}


def _app_keys() -> set[str]:
    source = (ROOT / "src" / "application.ts").read_text()
    block = re.search(r"APP_KEYS = \[(.*?)\] as const", source, re.S)
    assert block, "APP_KEYS list not found"
    return set(re.findall(r'"(VISION_[A-Z0-9_]+)"', block.group(1)))


def _wrangler_vars() -> dict[str, str]:
    text = (ROOT / "wrangler.jsonc").read_text()
    # Comments only: no value in this file contains "//" outside the "$schema" path.
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return json.loads(text)["vars"]


def test_every_setting_is_forwarded_by_the_edge():
    settings_keys = {f"VISION_{name.upper()}" for name in Settings.model_fields}
    missing = settings_keys - _app_keys() - NOT_FORWARDED
    assert not missing, f"add to APP_KEYS in application.ts: {sorted(missing)}"


def test_every_wrangler_var_is_a_real_forwarded_setting():
    settings_keys = {f"VISION_{name.upper()}" for name in Settings.model_fields}
    configured = {key for key in _wrangler_vars() if key.startswith("VISION_")}
    assert configured - settings_keys == set()
    assert configured - _app_keys() == set()
