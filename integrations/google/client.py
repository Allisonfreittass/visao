"""Gmail and Google Calendar for one person, through Google's REST APIs at fixed hosts.

The refresh token is the only long-lived secret; an access token lives an hour and stays in
memory. Everything read here (subjects, bodies, event titles) is untrusted text: it only reaches
the model as data, and nothing is sent or scheduled without the owner approving it first
(core/google/actions.py).
"""

import base64
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from integrations.search.fetch import html_to_text

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (an endpoint, not a secret)
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary"
SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
)
MAX_BODY_CHARS = 6000
_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


class GoogleError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str
    refresh_token: str


@dataclass(frozen=True)
class Mail:
    id: str
    thread_id: str
    sender: str
    subject: str
    date: str
    snippet: str
    unread: bool
    message_id: str = ""  # the RFC 822 Message-ID, for a reply in the same thread
    body: str = ""


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    start: str
    end: str
    location: str = ""
    attendees: int = 0
    link: str = ""


@dataclass
class _Token:
    value: str = ""
    expires: float = 0.0


@dataclass
class GoogleClient:
    credentials: Credentials
    http: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=10.0))
    _token: _Token = field(default_factory=_Token)

    # Auth ---------------------------------------------------------------------------------------

    def access_token(self) -> str:
        if self._token.value and time.monotonic() < self._token.expires - 60:
            return self._token.value
        try:
            response = self.http.post(
                TOKEN_URL,
                data={
                    "client_id": self.credentials.client_id,
                    "client_secret": self.credentials.client_secret,
                    "refresh_token": self.credentials.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError as exc:
            raise GoogleError("network", "o Google não respondeu") from exc
        if response.status_code in (400, 401):
            raise GoogleError("revoked", "a conexão com o Google expirou ou foi revogada")
        if response.status_code != 200:
            raise GoogleError(f"http_{response.status_code}", "o Google recusou o token")
        data = response.json()
        self._token = _Token(
            str(data["access_token"]), time.monotonic() + int(data.get("expires_in", 3600))
        )
        return self._token.value

    def _call(self, method: str, url: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token()}"}
        try:
            response = self.http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise GoogleError("network", "o Google não respondeu") from exc
        if response.status_code == 401:
            raise GoogleError("revoked", "a conexão com o Google expirou ou foi revogada")
        if response.status_code == 403:
            raise GoogleError(
                "forbidden", "o Google negou (falta permissão ou a API está desligada)"
            )
        if response.status_code == 429:
            raise GoogleError("rate_limited", "limite do Google atingido")
        if response.status_code >= 400:
            raise GoogleError(f"http_{response.status_code}", "o Google devolveu um erro")
        return response.json() if response.content else {}

    def revoke(self) -> None:
        try:
            self.http.post(REVOKE_URL, params={"token": self.credentials.refresh_token})
        except httpx.HTTPError:
            pass  # forgetting it locally is what matters; Google drops unused tokens too

    # Gmail --------------------------------------------------------------------------------------

    def address(self) -> str:
        return str(self._call("GET", f"{GMAIL}/profile").get("emailAddress", ""))

    def search(self, query: str, limit: int = 8) -> list[Mail]:
        found = self._call(
            "GET", f"{GMAIL}/messages", params={"q": query[:300], "maxResults": min(limit, 15)}
        )
        return [self.headers(m["id"]) for m in found.get("messages", [])[:limit]]

    def headers(self, message_id: str) -> Mail:
        data = self._call(
            "GET",
            f"{GMAIL}/messages/{message_id}",
            params=[
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "Date"),
                ("metadataHeaders", "Message-ID"),
            ],
        )
        return _mail(data)

    def read(self, message_id: str) -> Mail:
        data = self._call("GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"})
        mail = _mail(data)
        body = _body(data.get("payload", {}))
        return Mail(**{**mail.__dict__, "body": body[:MAX_BODY_CHARS]})

    def send(self, *, to: str, subject: str, body: str, reply_to: Mail | None = None) -> str:
        if not _EMAIL.match(parseaddr(to)[1] or ""):
            raise GoogleError("bad_address", "endereço de email inválido")
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        if reply_to is not None and reply_to.message_id:
            message["In-Reply-To"] = reply_to.message_id
            message["References"] = reply_to.message_id
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        payload: dict = {"raw": raw}
        if reply_to is not None:
            payload["threadId"] = reply_to.thread_id
        return str(self._call("POST", f"{GMAIL}/messages/send", json=payload).get("id", ""))

    # Calendar -----------------------------------------------------------------------------------

    def events(self, start: datetime, end: datetime, limit: int = 20) -> list[Event]:
        data = self._call(
            "GET",
            f"{CALENDAR}/events",
            params={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": min(limit, 50),
            },
        )
        return [_event(item) for item in data.get("items", []) if item.get("status") != "cancelled"]

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        timezone: str,
        description: str = "",
        location: str = "",
        attendees: tuple[str, ...] = (),
    ) -> Event:
        for address in attendees:
            if not _EMAIL.match(address):
                raise GoogleError("bad_address", f"convidado inválido: {address}")
        body = {
            "summary": title[:300],
            "description": description[:4000],
            "location": location[:300],
            "start": {"dateTime": start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": timezone},
            "attendees": [{"email": a} for a in attendees],
        }
        params = {"sendUpdates": "all" if attendees else "none"}
        return _event(self._call("POST", f"{CALENDAR}/events", params=params, json=body))


def _header(data: dict, name: str) -> str:
    for item in data.get("payload", {}).get("headers", []):
        if item.get("name", "").lower() == name.lower():
            return str(item.get("value", ""))
    return ""


def _mail(data: dict) -> Mail:
    return Mail(
        id=str(data.get("id", "")),
        thread_id=str(data.get("threadId", "")),
        sender=_header(data, "From")[:200],
        subject=_header(data, "Subject")[:300],
        date=_header(data, "Date")[:60],
        snippet=str(data.get("snippet", ""))[:300],
        unread="UNREAD" in data.get("labelIds", []),
        message_id=_header(data, "Message-ID")[:300],
    )


def _decode(value: str) -> str:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8", "replace")
    except ValueError:
        return ""


def _body(payload: dict) -> str:
    """The plain text of a message: text/plain when there is one, else the HTML as text."""
    plain, html = [], []

    def walk(part: dict) -> None:
        kind = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and kind == "text/plain":
            plain.append(_decode(data))
        elif data and kind == "text/html":
            html.append(_decode(data))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    return html_to_text("\n".join(html))


def _when(value: dict) -> str:
    return str(value.get("dateTime") or value.get("date") or "")


def _event(item: dict) -> Event:
    return Event(
        id=str(item.get("id", "")),
        title=str(item.get("summary") or "(sem título)")[:300],
        start=_when(item.get("start", {})),
        end=_when(item.get("end", {})),
        location=str(item.get("location") or "")[:300],
        attendees=len(item.get("attendees", []) or []),
        link=str(item.get("htmlLink") or ""),
    )
