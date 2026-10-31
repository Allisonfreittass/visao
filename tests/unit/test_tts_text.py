from integrations.tts.base import SynthesizedAudio
from integrations.tts.text import MAX_SENTENCE_CHARS, sentences, speakable


def test_markdown_is_not_read_aloud() -> None:
    reply = (
        "## Resumo\n"
        "Você escolheu o **pgloader** para a `migração`.\n"
        "- Teste em homologação\n"
        "- Veja [a documentação](https://exemplo.com/docs)\n"
        "```sql\nSELECT 1;\n```\n"
        "Mais em https://exemplo.com."
    )
    text = speakable(reply)
    for leftover in ("**", "`", "##", "](", "SELECT", "https://"):
        assert leftover not in text
    assert "Você escolheu o pgloader para a migração." in text
    assert "Teste em homologação." in text
    assert "a documentação" in text
    assert "trecho de código omitido" in text


def test_splits_into_sentences() -> None:
    assert sentences("Olá! Tudo bem? Hoje é dia 3. Vamos lá.") == [
        "Olá!",
        "Tudo bem?",
        "Hoje é dia 3.",
        "Vamos lá.",
    ]


def test_does_not_split_decimals_or_lowercase_continuations() -> None:
    assert sentences("Custa R$ 12,50 e versão 3.5 está ok. ex. de uso.") == [
        "Custa R$ 12,50 e versão 3.5 está ok. ex. de uso."
    ]


def test_long_sentences_are_chunked_at_punctuation() -> None:
    long = ", ".join(["um trecho razoavelmente comprido de texto"] * 20) + "."
    chunks = sentences(long)
    assert len(chunks) > 1
    assert all(len(c) <= MAX_SENTENCE_CHARS for c in chunks)
    assert " ".join(chunks).replace("  ", " ") == long


def test_empty_reply() -> None:
    assert sentences("   \n**  **\n") == []


def test_wav_encoding() -> None:
    audio = SynthesizedAudio(pcm16=b"\x00\x00" * 22050, sample_rate=22050)
    assert audio.duration_seconds == 1.0
    wav = audio.to_wav()
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert len(wav) == 44 + 44100
