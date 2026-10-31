"""Day-2 step of scenario S5 for configuration C: one autonomous cycle, no new message."""

from apps.worker.handlers import autonomy_budget
from core.autonomy.cycle import run_cycle


def run_cycle_for_eval(world) -> dict:
    world.owner.autonomy_permissions = {"auto_research": True}
    world.session.commit()
    report = run_cycle(
        world.session,
        provider=world.provider,
        search=world.search,
        budget=autonomy_budget(world.settings),
    )
    print(f"\n[ciclo autônomo] pulado: {report.skipped} | ações: {report.actions}")
    return {"skipped": report.skipped, "actions": report.actions}
