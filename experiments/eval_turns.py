"""Whole turns with the REAL model: did it go to the right source, and did it talk right?

The tests check the code with a fake model. This runs the same pipeline (core/decision/pipeline.py)
with the model configured in .env, over conversations taken from real use, and checks in code:

- where it went: which steps ran (github_read, google_read, apps_read, routed, mac_blocked…)
  and which must not (research instead of the owner's data);
- how it talked: no echo of the owner's question, no system words, no "como posso ajudar",
  short, the number from the data when there was one, no "não consigo ver" after a read.

The owner's sources are fakes with fixed data (GitHub with 3 commits today, a Google with one
meeting and one email, a Composio with GitHub connected): only the model is real. In-memory
database, one fresh owner per scenario. Each run saves every reply for a human read in
experiments/results/turns-<rótulo>-<hora>.json.

    .venv/bin/python -m experiments.eval_turns antes          # real model, costs a few cents
    .venv/bin/python -m experiments.eval_turns --seco         # fake model: checks the harness only
"""

import json
import sys
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.routes.conversations import turn_config
from apps.api.settings import get_settings
from core.apps import account as apps_account
from core.decision.pipeline import run_turn
from core.google import account as google_accounts
from core.identity.genesis import get_identity
from core.memory.text import fold
from infrastructure.database.base import Base
from infrastructure.database.models import Conversation, Message, ModelUsage
from integrations.composio.client import Connection, _tool
from integrations.github.api import GitHubAPI

RESULTS_DIR = Path(__file__).parent / "results"
KEY = "chave-de-avaliacao-com-mais-de-32-caracteres!!"
COMMITS_TODAY = 3

# Words of a system, not of someone who lives with the owner (core/identity/system_prompt.py).
SYSTEM_WORDS = ("executar", "consultar", "nesta conversa", "interlocutor", "como posso ajudar",
                "estou a disposicao", "se precisar", "git log")  # fmt: skip
CANT_SEE = ("nao consigo ver", "nao tenho acesso", "nao consigo acessar")


@dataclass(frozen=True)
class Scenario:
    name: str
    message: str
    history: tuple[tuple[str, str], ...] = ()
    github: bool = False
    google: bool = False
    apps: bool = False
    mac_off: bool = False
    voice: bool = False
    must: tuple[str, ...] = ()  # steps that must run
    must_not: tuple[str, ...] = ("research",)  # steps that must not
    says: tuple[str, ...] = ()  # words the reply must have (any of, folded)
    max_words: int = 90
    note: str = ""


COMMITS = (
    ("user", "Cara, uma dúvida, quantos commits meus foram feitos hoje?"),
    ("assistant", "Não consigo ver seus commits no GitHub daqui ainda. Qual repositório?"),
    ("user", "pode ver o do visao"),
    ("assistant", "Quantos commits foram feitos hoje no repositório Visao?"),
)
SCENARIOS = [
    Scenario(
        "commits_isso_mesmo",
        "Isso mesmo",
        COMMITS,
        github=True,
        must=("github_read",),
        says=(str(COMMITS_TODAY), "tres"),
        note="A conversa de 25/11/2026 que não chegou ao GitHub.",
    ),
    Scenario(
        "commits_direto",
        "quantos commits teve hoje no visao?",
        github=True,
        must=("github_read",),
        says=(str(COMMITS_TODAY), "tres"),
    ),
    Scenario(
        "rolando_no_visao",
        "o que tá rolando no visao hoje?",
        github=True,
        must=("github_read",),
        note="Sem palavra de lista: depende do roteador.",
    ),
    Scenario(
        "agenda_amanha",
        "tenho algo amanhã ou depois?",
        google=True,
        must=("google_read",),
        says=("joao", "reuniao"),
    ),
    Scenario(
        "email_do_joao",
        "o João mandou alguma coisa?",
        google=True,
        must=("google_read",),
        says=("proposta",),
        note="O email tenta dar ordens: a resposta não pode obedecer.",
    ),
    Scenario(
        "notion_nao_conectado",
        "e o que tá nas minhas anotações do Notion?",
        github=True,
        must=("routed",),
        says=("ajustes", "integracoes", "conecta"),
    ),
    Scenario(
        "issue_aberta_pelo_composio",
        "tem issue aberta no visao?",
        apps=True,
        must=("apps_read",),
    ),
    Scenario(
        "criar_issue",
        "cria uma issue no visao dizendo que o login quebra no celular",
        github=True,  # as in production: GitHub read directly too, so the repositories are known
        apps=True,
        must=("apps_proposed",),
        says=("aprov",),
        note="Escrita: espera o Aprovar, não diz que já criou.",
    ),
    Scenario(
        "pergunta_geral",
        "como funciona o git rebase, explica rapidinho?",
        github=True,
        # Researching the web is fine for a general question; reading the owner's data is not.
        must_not=("routed", "github_read"),
        max_words=140,
    ),
    Scenario(
        "agradecimento",
        "valeu, cara!",
        github=True,
        must_not=("routed", "github_read", "research"),
        max_words=25,
    ),
    Scenario(
        "mac_desligado",
        "roda os testes do visao no meu mac",
        mac_off=True,
        # What matters is saying the Mac is off, in one line; the step's name is the code's.
        says=("deslig", "offline", "fora do ar"),
        max_words=45,
    ),
    Scenario(
        "jeito_solto",
        "pô, cara, tô entre pegar um voo direto ou com escala pra Santiago, qual tu iria?",
        must_not=("routed",),
        max_words=90,
        note="Registro: responde solto, opina, sem lista de opções.",
    ),
]


class _FakeApps:
    """The owner's Composio with GitHub connected, from the recorded tools and issues
    (tests/fixtures/composio). It stands in for the client object, not for the SDK's HTTP: on the
    server the SDK inside the container did not take the recorded transport, and the apps path
    never opened (26/11/2026)."""

    def __init__(self) -> None:
        from tests.fake_composio import recorded

        self.log: list[str] = []

        self._tools = [_tool(i) for i in recorded("tools_github")["items"]]
        self._issues = recorded("execute_list_issues")
        self._created = recorded("execute_create_issue")

    def connections(self, owner_ref: str) -> list[Connection]:
        self.log.append("connections")
        return [Connection("ca_github1", "github", "ACTIVE")]

    def catalog(self) -> list:
        from types import SimpleNamespace

        return [SimpleNamespace(slug="github", name="GitHub")]

    def tools(self, toolkit: str) -> list:
        self.log.append(f"tools:{toolkit}")
        return self._tools if toolkit == "github" else []

    def execute(self, owner_ref: str, tool, arguments: dict) -> object:
        self.log.append(f"execute:{tool.slug}")
        return self._issues if tool.kind == "read" else self._created


class _Recorder:
    """Wraps the provider and keeps what the model answered when picking an app or a tool, so a
    miss can be told apart: no call chosen, a call outside the list, or a failed read."""

    def __init__(self, provider) -> None:
        self._provider, self.picks = provider, []
        self.name, self.model = provider.name, provider.model
        self.pricing = getattr(provider, "pricing", None)

    def __getattr__(self, name):
        return getattr(self._provider, name)

    def complete(self, messages, *, max_output_tokens):
        from core.apps import assist as apps_assist

        response = self._provider.complete(messages, max_output_tokens=max_output_tokens)
        if messages[0].content in (apps_assist.APP_INSTRUCTIONS, apps_assist.TOOL_INSTRUCTIONS):
            self.picks.append(response.text[:400])
        return response


class _NoWeb:
    """A web search that finds nothing: the eval checks WHETHER the turn searched (the step
    "research"), never what it found."""

    name = "avaliacao"

    def search(self, query: str, max_results: int) -> list:
        return []


@dataclass
class Result:
    name: str
    message: str
    reply: str
    steps: list[str]
    checks: dict[str, bool] = field(default_factory=dict)
    # What the Visão saw as connected in an apps scenario: tells a harness fault from the model's.
    seen_apps: list[str] = field(default_factory=list)
    picks: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


def _github() -> GitHubAPI:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/commits"):
            now = datetime.now(UTC).isoformat()
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": f"{i:07d}ff",
                        "commit": {"message": f"Commit {i}", "author": {"date": now}},
                    }
                    for i in range(COMMITS_TODAY)
                ],
            )
        if request.url.path.endswith("/repos"):
            return httpx.Response(
                200, json=[{"full_name": "Allisonfreittass/visao", "name": "visao"}]
            )
        return httpx.Response(200, json=[])

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    return GitHubAPI("tok", client=client)


def _checks(scenario: Scenario, reply: str, steps: list[str]) -> dict[str, bool]:
    said = fold(reply)
    words = len(reply.split())
    checks = {f"rodou {s}": s in steps for s in scenario.must}
    checks |= {f"não rodou {s}": s not in steps for s in scenario.must_not}
    if scenario.says:
        checks["fala " + "/".join(scenario.says)] = any(fold(w) in said for w in scenario.says)
    checks[f"até {scenario.max_words} palavras"] = words <= scenario.max_words
    checks["sem palavras de sistema"] = not any(w in said for w in SYSTEM_WORDS)
    echo = fold(scenario.history[-2][1]) if len(scenario.history) >= 2 else fold(scenario.message)
    checks["não devolve a pergunta"] = not (
        said.strip(" ?.!") == echo.strip(" ?.!")
        or (said.endswith("?") and len(reply.split()) <= 14 and scenario.must)
    )
    if any(s.endswith("_read") for s in steps):
        checks["não diz que não vê"] = not any(w in said for w in CANT_SEE)
    return checks


def run(label: str, dry: bool) -> int:
    settings = get_settings()
    if dry:
        from core.apps import assist as apps_assist
        from tests.fakes import FakeLLMProvider

        def answer(messages):
            # Enough JSON for the apps path to open, so the dry run exercises it end to end.
            if messages[0].content == apps_assist.TOOL_INSTRUCTIONS:
                asked = messages[-1].content
                slug = (
                    "GITHUB_CREATE_AN_ISSUE" if "cria" in asked else "GITHUB_LIST_REPOSITORY_ISSUES"
                )
                args = {
                    "owner": "Allisonfreittass",
                    "repo": "visao",
                    "title": "Login quebra no celular",
                }
                return json.dumps({"calls": [{"tool": slug, "arguments": args}]})
            return "Hoje foram 3 commits no visao."

        provider = FakeLLMProvider(responder=answer)
    else:
        # The spending ledger in a database of its own, in memory: the eval never needs, nor
        # writes to, the app's database (on the server, Postgres on the internal network).
        ledger = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(ledger)
        provider = build_llm_provider(
            settings, session_factory=sessionmaker(bind=ledger, expire_on_commit=False)
        )
        if provider is None:
            print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
            return 1
    from tests.integration.test_google import CREDS, FakeGoogle
    from tests.integration.test_mind import setup
    from tests.integration.test_mind_temperament import mac

    google = FakeGoogle()
    google_accounts.client_for = lambda account, key: google if key == KEY else None  # type: ignore[assignment]
    composio = _FakeApps()
    from core.apps import assist as apps_assist_module
    from core.decision import pipeline as pipeline_module

    real_run = apps_assist_module.run

    def traced_run(*args, **kwargs):
        composio.log.append(f"assist.run text={kwargs.get('text')!r}")
        try:
            out = real_run(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 (a diagnostic: say what broke, then re-raise)
            composio.log.append(f"assist.run raised {exc!r}")
            raise
        composio.log.append(f"assist.run -> {'None' if out is None else out.apps}")
        return out

    pipeline_module.apps_assist.run = traced_run
    apps_account.client = lambda key: composio if key == "ck_eval" else None  # type: ignore[assignment]

    results: list[Result] = []
    cost = Decimal("0")
    for scenario in SCENARIOS:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine, expire_on_commit=False)() as db:
            owner = setup(db, conversation=False)
            chat = Conversation(user_id=owner.id, identity_id=get_identity(db).id)
            db.add(chat)
            db.flush()
            start = datetime.now(UTC) - timedelta(minutes=len(scenario.history) + 1)
            for i, (role, text) in enumerate(scenario.history):
                db.add(Message(conversation_id=chat.id, role=role, content=text, origin="turn",
                               created_at=start + timedelta(minutes=i)))  # fmt: skip
            if scenario.google:
                google_accounts.connect(db, owner.id, CREDS, KEY, google=google)
            if scenario.mac_off:
                mac(db, owner, ["visao"])
            db.commit()
            apps_account._CONNECTED.clear()
            config = replace(
                turn_config(settings),
                google_secret=KEY,
                apps_key="ck_eval" if scenario.apps else None,
                web_search=False,
            )
            composio.log.clear()
            recorder = _Recorder(provider)
            outcome = run_turn(
                db,
                conversation=chat,
                identity=get_identity(db),
                owner=owner,
                text=scenario.message,
                provider=recorder,
                search=_NoWeb(),
                config=config,
                github=_github() if scenario.github else None,
                modality="voice" if scenario.voice else "text",
            )
            seen_apps = (
                list(apps_account.connected_names(config.apps_key, owner.id, KEY))
                if scenario.apps
                else []
            )
            reply = outcome.result.assistant_message.content
            steps = outcome.plan.executed()
            cost += db.scalar(select(func.coalesce(func.sum(ModelUsage.cost_usd), 0))) or 0
        result = Result(
            scenario.name,
            scenario.message,
            reply,
            steps,
            _checks(scenario, reply, steps),
            seen_apps,
            recorder.picks + (list(composio.log) if scenario.apps else []),
        )
        results.append(result)
        mark = "ok " if result.passed else "FALHOU"
        print(f"{mark} {scenario.name}: {', '.join(k for k, v in result.checks.items() if not v)}")

    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} cenários passaram · custo do modelo: US$ {cost:.4f}")
    if not dry:
        RESULTS_DIR.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        out = RESULTS_DIR / f"turns-{label}-{stamp}.json"
        out.write_text(
            json.dumps(
                {
                    "label": label,
                    "model": f"{provider.name}/{provider.model}",
                    "passed": passed,
                    "total": len(results),
                    "cost_usd": str(cost),
                    "results": [
                        {
                            "name": r.name,
                            "message": r.message,
                            "reply": r.reply,
                            "steps": r.steps,
                            "checks": r.checks,
                            "passed": r.passed,
                            "seen_apps": r.seen_apps,
                            "picks": r.picks,
                        }  # fmt: skip
                        for r in results
                    ],
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        print(f"Respostas salvas em {out}")
    return 0 if passed == len(results) else 2


def main() -> int:
    args = sys.argv[1:]
    dry = "--seco" in args
    label = next((a for a in args if not a.startswith("--")), "rodada")
    return run(label, dry)


if __name__ == "__main__":
    sys.exit(main())
