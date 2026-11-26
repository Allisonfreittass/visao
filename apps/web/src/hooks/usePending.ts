import { useCallback, useEffect, useRef, useState } from "react";

import type { Api, AppNotification, ArmDevice, ArmTask, Goal, GoogleAction, PanelOffer, ToolAction } from "../api";
import { moneyWords } from "../api";
import { confirmar } from "../ask";

const POLL_MS = 15_000;

export interface Pending {
  /** Work the agent proposed for the Mac, waiting for a yes. */
  armProposals: ArmTask[];
  /** Email to send or events to schedule, waiting for a yes. */
  googleActions: GoogleAction[];
  /** Changes in the owner's other apps (Composio), waiting for a yes. */
  toolActions: ToolAction[];
  /** After a live quote, the panel it offered to keep on the home screen. */
  panelOffers: PanelOffer[];
  goals: Goal[];
  /** Notices that live only here (an opening is already a message in the chat). */
  notices: AppNotification[];
  devices: ArmDevice[];
  tasks: ArmTask[];
  /** How many things wait for the owner right now. */
  count: number;
  /** How many of them are a yes or no to give (the ring lights its gap, DESIGN.md §6). */
  approvals: number;
  /** He opened a conversation that was not read yet (the ring's dot rises to the gap). */
  opening: boolean;
  /** His autonomy is paused in Ajustes (the ring's dot goes hollow). */
  paused: boolean;
  /** Ajustes changed the pause: the ring follows at once, the next poll only confirms. */
  setPaused: (paused: boolean) => void;
  refresh: () => void;
  decideArm: (task: ArmTask, decision: "approve" | "reject", via?: "toque" | "voz") => Promise<boolean>;
  decideGoal: (goal: Goal, decision: "approve" | "reject") => Promise<boolean>;
  decideGoogle: (action: GoogleAction, decision: "approve" | "reject", via?: "toque" | "voz") => Promise<boolean>;
  decideApp: (action: ToolAction, decision: "approve" | "reject", via?: "toque" | "voz") => Promise<boolean>;
  decidePanelOffer: (offer: PanelOffer, decision: "approve" | "reject", via?: "toque" | "voz") => Promise<boolean>;
  dismiss: (notice: AppNotification) => Promise<boolean>;
  reply: (notice: AppNotification, conversationId: string | null) => Promise<string | null>;
}

/**
 * Everything waiting for the owner, polled once and shared by the rail badge, the presence
 * panel and the inbox. Openings are marked read while the conversation is on screen: they are
 * already in the chat, so a second copy would only be noise.
 */
export function usePending(api: Api, enabled: boolean, onError: (e: unknown) => void, chatVisible: boolean): Pending {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [devices, setDevices] = useState<ArmDevice[]>([]);
  const [tasks, setTasks] = useState<ArmTask[]>([]);
  const [google, setGoogle] = useState<GoogleAction[]>([]);
  const [offers, setOffers] = useState<PanelOffer[]>([]);
  const [tools, setTools] = useState<ToolAction[]>([]);
  const [paused, setPausedState] = useState(false);
  // Bumped by every local change, so a poll that left before it cannot flip the ring back.
  const pauseVersion = useRef(0);
  const setPaused = useCallback((next: boolean) => {
    pauseVersion.current += 1;
    setPausedState(next);
  }, []);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const refresh = useCallback(() => {
    if (!enabled) return;
    // An older server without panel offers answers 404: that is just none.
    const panelOffers = api.panelOffers().catch(() => [] as PanelOffer[]);
    // Without the Composio key (or on an older server) there are none.
    const appActions = api.appActions().catch(() => [] as ToolAction[]);
    // Only the ring reads the pause; an error here must not hide what waits.
    const asked = pauseVersion.current;
    api.autonomy().then((a) => { if (pauseVersion.current === asked) setPausedState(a.paused); }, () => undefined);
    Promise.all([api.approvals(), api.notifications(), api.armDevices(), api.armTasks(), api.googleActions(), panelOffers, appActions])
      .then(([g, n, d, t, o, p, a]) => {
        setTools(a);
        setOffers(p);
        setGoals(g);
        setNotifications(n);
        setDevices(d);
        setTasks(t);
        setGoogle(o);
      })
      .catch((e) => onErrorRef.current(e));
  }, [api, enabled]);

  useEffect(() => {
    refresh();
    if (!enabled) return;
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh, enabled]);

  const unread = notifications.filter((n) => !n.read_at);
  const openings = unread.filter((n) => n.kind === "initiative");
  useEffect(() => {
    if (!chatVisible || !openings.length || document.visibilityState !== "visible") return;
    Promise.all(openings.map((n) => api.markRead(n.id))).then(refresh, () => undefined);
  }, [api, chatVisible, openings.map((n) => n.id).join(","), refresh]);

  /** True when the server accepted it: a spoken "pronto" must never follow a failure. */
  async function act(action: () => Promise<unknown>): Promise<boolean> {
    let ok = true;
    try {
      await action();
    } catch (e) {
      ok = false;
      onErrorRef.current(e);
    }
    refresh();
    return ok;
  }

  const armProposals = tasks.filter((t) => t.status === "proposed");
  const notices = unread.filter((n) => n.kind !== "initiative");
  return {
    armProposals,
    googleActions: google,
    toolActions: tools,
    panelOffers: offers,
    goals,
    notices,
    devices,
    tasks,
    count: armProposals.length + google.length + tools.length + offers.length + goals.length + notices.length,
    approvals: armProposals.length + google.length + tools.length + offers.length + goals.length,
    opening: openings.length > 0,
    paused,
    setPaused,
    refresh,
    decideArm: (task, decision, via) => act(() => api.decideArm(task.id, decision, via)),
    decideGoal: (goal, decision) => act(() => api.decideGoal(goal.id, decision)),
    decideGoogle: (action, decision, via) => act(() => api.decideGoogle(action.id, decision, via)),
    decideApp: async (action, decision, via) => {
      // A payment: the amount is confirmed here, on every card that approves (core/apps/money.py).
      if (decision === "approve" && action.money) {
        const ok = await confirmar(
          `Pagar ${moneyWords(action.money)} pelo ${action.app}? Sai agora e conta no teto de hoje.`,
          "Pagar",
        );
        if (!ok) return false;
        return act(() => api.decideApp(action.id, decision, via, action.money!.amount));
      }
      return act(() => api.decideApp(action.id, decision, via));
    },
    decidePanelOffer: (offer, decision, via) => act(() => api.decidePanelOffer(offer.id, decision, via)),
    dismiss: (notice) => act(() => api.markRead(notice.id)),
    reply: async (notice, conversationId) => {
      try {
        const { conversation_id: id } = await api.replyToNotification(notice.id, conversationId);
        refresh();
        return id;
      } catch (e) {
        onErrorRef.current(e);
        return null;
      }
    },
  };
}
