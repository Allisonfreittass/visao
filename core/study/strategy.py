"""Search candidates; editable by the bounded code-evolution experiment."""


def candidate_queries(query: str, topic: str) -> list[str]:
    return [candidate for candidate in dict.fromkeys([query.strip(), topic.strip()]) if candidate]
