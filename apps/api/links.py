from functools import lru_cache

from apps.api.settings import get_settings
from core.conversation.links import LinkReader
from integrations.github.reader import GitHubReader


@lru_cache
def get_link_reader() -> LinkReader:
    """Override point for tests. GitHub goes to api.github.com; other links through the safe
    page reader (integrations/search/fetch.py)."""
    token = get_settings().github_token
    return LinkReader(GitHubReader(token.get_secret_value() if token else None))
