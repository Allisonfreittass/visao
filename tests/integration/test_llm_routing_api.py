"""Ajustes > Escolha do provedor (ADR-0022): the owner switches, and sees the order per task."""

from decimal import Decimal

from pydantic import SecretStr

from apps.api.settings import Settings, get_settings
from tests.integration.test_mind import _owner_client

THREE = {
    "llm_provider_name": "gemini",
    "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "llm_api_key": SecretStr("k1"),
    "llm_model": "gemini-flash",
    "llm_price_input_per_mtok": Decimal(0),
    "llm_price_output_per_mtok": Decimal(0),
    "llm_fallback_provider_name": "anthropic",
    "llm_fallback_base_url": "https://api.anthropic.com",
    "llm_fallback_api_key": SecretStr("k2"),
    "llm_fallback_model": "claude-haiku-5-5",
    "llm_fallback_price_input_per_mtok": Decimal("0.1"),
    "llm_fallback_price_output_per_mtok": Decimal("0.5"),
    "llm_fallback2_provider_name": "openai",
    "llm_fallback2_base_url": "https://api.openai.com/v1",
    "llm_fallback2_api_key": SecretStr("k3"),
    "llm_fallback2_model": "gpt-mini",
    "llm_fallback2_price_input_per_mtok": Decimal("0.2"),
    "llm_fallback2_price_output_per_mtok": Decimal("0.8"),
}


def test_the_owner_switches_and_sees_the_order_per_task(client, db):
    _, owner = _owner_client(client, db)
    client.app.dependency_overrides[get_settings] = lambda: Settings(**THREE)
    fixed = client.get("/system/llm-routing", headers=owner).json()
    assert fixed == {
        "mode": "fixa",
        "configured": ["Gemini", "Claude", "OpenAI"],
        "personal": ["Gemini", "Claude", "OpenAI"],
        "public": ["Gemini", "Claude", "OpenAI"],
    }
    switched = client.put("/system/llm-routing", json={"mode": "por_tarefa"}, headers=owner).json()
    assert switched["personal"] == ["Claude", "OpenAI", "Gemini"]
    assert switched["public"] == ["Gemini", "Claude", "OpenAI"]
    # "auto" is the brain's mode (core/brain.py), not this one.
    assert (
        client.put("/system/llm-routing", json={"mode": "auto"}, headers=owner).status_code == 422
    )


def test_routing_needs_the_login(client):
    assert client.get("/system/llm-routing").status_code == 401
