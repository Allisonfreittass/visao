"""The reply's prompt fits under the ledger's per-call input limit instead of being refused.
Real case (16/11/2026): a long trip conversation got "Falha no provedor de LLM (budget_denied)"
because the prompt passed 80 000 bytes."""

from core.conversation.service import CUT_NOTE, FIT_MARGIN_BYTES, fit
from integrations.llm.base import ChatMessage
from integrations.llm.budget import input_estimate

SYSTEM = ChatMessage("system", "Você é o Visão." * 50)


def history(turns: int, size: int = 2000) -> list[ChatMessage]:
    messages = []
    for n in range(turns):
        messages.append(ChatMessage("user", f"pergunta {n} " + "a" * size))
        messages.append(ChatMessage("assistant", f"resposta {n} " + "b" * size))
    return messages


def test_a_prompt_that_fits_is_left_alone():
    prompt = [SYSTEM, *history(2), ChatMessage("user", "e agora?")]
    assert fit(prompt, 10**6) == prompt


def test_the_oldest_history_goes_first_and_the_conversation_restarts_at_the_person():
    prompt = [SYSTEM, *history(20), ChatMessage("user", "e agora?")]
    limit = input_estimate(prompt) // 3

    fitted = fit(prompt, limit)

    assert input_estimate(fitted) <= limit - FIT_MARGIN_BYTES
    assert fitted[0] == SYSTEM and fitted[-1].content == "e agora?"
    assert fitted[1].role == "user"
    # What stayed is the most recent part, in order.
    assert fitted[-2] == prompt[-2] and fitted[1:] == prompt[len(prompt) - len(fitted) + 1 :]


def test_pages_attached_to_the_message_are_cut_before_the_persons_words():
    pages = "<pagina>" + "preço R$ 2.019 " * 3000 + "</pagina>"
    own = "quanto tá a passagem?"
    prompt = [SYSTEM, ChatMessage("user", f"{own}\n\n{pages}")]
    limit = input_estimate([SYSTEM, ChatMessage("user", own)]) + 6000

    fitted = fit(prompt, limit, pages)

    assert input_estimate(fitted) <= limit - FIT_MARGIN_BYTES
    assert fitted[-1].content.startswith(own) and fitted[-1].content.endswith(CUT_NOTE)
    assert "preço R$ 2.019" in fitted[-1].content  # some of the pages stay


def test_when_the_system_prompt_alone_does_not_fit_it_is_not_cut():
    prompt = [SYSTEM, ChatMessage("user", "oi")]
    fitted = fit(prompt, 100)
    assert fitted[0] == SYSTEM and fitted[-1].content == "oi"
