import { useCallback, useEffect, useRef, useState } from "react";

import type { Api, AppNotification, ArmDevice, ArmTask, Goal, GoogleAction } from "../api";

const POLL_MS = 15_000;

export interface Pending {
  /** Work the agent proposed for the Mac, waiting for a yes. */
  armProposals: ArmTask[];
  /** Email to send or events to schedule, waiting for a yes. */
  googleActions: GoogleAction[];
  goals: Goal[];
  /** Notices that live only here (an opening is already a message in the chat). */
  notices: AppNotification[];
  devices: ArmDevice[];
  tasks: ArmTask[];
  /** How many things wait for the owner right now. */
  count: number;
  refresh: () => void;
  decideArm: (task: ArmTask, decision: "approve" | "reject", via?: "toque" | "voz") => Promise<boolean>;
  decideGoal: (goal: Goal, decision: "approve" | "reject") => Promise<boolean>;
  decideGoogle: (action: GoogleAction, decision: "approve" | "reject", via?: "toque" | "voz") => Promise<boolean>;
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
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const refresh = useCallback(() => {
    if (!enabled) return;
    Promise.all([api.approvals(), api.notifications(), api.armDevices(), api.armTasks(), api.googleActions()])
      .then(([g, n, d, t, o]) => {
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
    goals,
    notices,
    devices,
    tasks,
    count: armProposals.length + google.length + goals.length + notices.length,
    refresh,
    decideArm: (task, decision, via) => act(() => api.decideArm(task.id, decision, via)),
    decideGoal: (goal, decision) => act(() => api.decideGoal(goal.id, decision)),
    decideGoogle: (action, decision, via) => act(() => api.decideGoogle(action.id, decision, via)),
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
