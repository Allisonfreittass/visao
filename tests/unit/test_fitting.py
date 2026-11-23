"""Compact mode: each model gets the largest version of the prompt that fits its limit, and a 413
teaches the limit instead of costing the reply (docs/MODO_COMPACTO.md)."""

import pytest

from integrations.llm.base import ChatMessage, LLMError, compacting
from integrations.llm.fitting import FittingProvider, forget_learned, limit_in, tokens
from tests.fakes import FakeLLMProvider

FULL = [ChatMessage("system", "contexto " * 6000), ChatMessage("user", "oi")]
MEDIUM = [ChatMessage("system", "contexto " * 1500), ChatMessage("user", "oi")]
SMALL = [ChatMessage("system", "núcleo " * 200), ChatMessage("user", "oi")]
LEVELS = [FULL, MEDIUM, SMALL]


@pytest.fixture(autouse=True)
def fresh():
    forget_learned()
    yield
    forget_learned()


class Small(FakeLLMProvider):
    """Like Groq's free tier: refuses a request over its limit, prompt and answer together."""

    def __init__(self, limit=8000):
        super().__init__(name="groq", model="gpt-oss")
        self.limit, self.sizes, self.outputs = limit, [], []

    def complete(self, messages, *, max_output_tokens):
        asked = tokens(messages) + max_output_tokens
        self.sizes.append(tokens(messages))
        self.outputs.append(max_output_tokens)
        if asked > self.limit:
            raise LLMError(
                "too_large",
                f"Request too large for model on tokens per minute (TPM): Limit {self.limit}, "
                f"Requested {asked}",
            )
        return super().complete(messages, max_output_tokens=max_output_tokens)


def ask(provider, levels=LEVELS, output=3072):
    with compacting(levels):
        return provider.complete(levels[0], max_output_tokens=output)


def test_reads_the_limit_out_of_the_providers_413():
    assert limit_in("Limit 8000, Requested 14210") == 8000
    assert limit_in("limit: 30,000 tokens") == 30000
    assert limit_in("Request too large") is None


def test_a_model_with_a_known_limit_gets_the_version_that_fits():
    small = Small()
    ask(FittingProvider(small, max_request_tokens=8000))
    assert small.sizes == [tokens(MEDIUM)]  # the largest that fits, in one call
    assert small.outputs == [2000]  # the answer shares the limit, so it asks for less


def test_without_a_known_limit_a_413_teaches_it_and_the_reply_still_comes():
    small = Small()
    fitting = FittingProvider(small)
    assert ask(fitting).text == "resposta de teste"
    assert small.sizes == [tokens(FULL), tokens(MEDIUM)]
    assert fitting.limit == 8000
    ask(fitting)  # learned: the next request fits at once
    assert small.sizes[-1] == tokens(MEDIUM) and len(small.sizes) == 3


def test_a_model_without_a_limit_gets_the_whole_prompt():
    big = FakeLLMProvider()
    ask(FittingProvider(big))
    assert big.prompts == [FULL]


def test_it_never_loops_when_even_the_smallest_does_not_fit():
    tiny = Small(limit=1000)
    with pytest.raises(LLMError) as caught:
        ask(FittingProvider(tiny))
    assert caught.value.kind == "too_large" and len(tiny.sizes) == 2


def test_levels_offered_for_another_prompt_are_ignored():
    small = Small()
    other = [ChatMessage("user", "outra chamada")]
    with compacting(LEVELS):
        FittingProvider(small, max_request_tokens=8000).complete(other, max_output_tokens=100)
    assert small.sizes == [tokens(other)]
