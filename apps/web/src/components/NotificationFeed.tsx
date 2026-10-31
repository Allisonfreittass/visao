import { useCallback, useEffect, useState } from "react";

import type { Api, AppNotification } from "../api";

/** Invitations stay visible even when the conversation menu is closed. */
export function NotificationFeed({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const refresh = useCallback(async () => {
    setNotifications(await api.notifications());
  }, [api]);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const items = await api.notifications();
        if (alive) setNotifications(items);
      } catch (e) {
        if (alive) onError(e);
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 15_000);
    return () => { alive = false; clearInterval(timer); };
  }, [api, onError]);

  async function dismiss(id: string) {
    try { await api.markRead(id); await refresh(); } catch (e) { onError(e); }
  }

  const unread = notifications.filter((item) => !item.read_at);
  if (!unread.length) return null;
  return (
    <section className="notification-feed" aria-label="Iniciativas do VISÃO" aria-live="polite">
      {unread.map((item) => (
        <div className="card" key={item.id}>
          <strong>{item.title}</strong>
          <p className="note pre">{item.body}</p>
          <button className="ghost" onClick={() => void dismiss(item.id)}>Dispensar aviso</button>
        </div>
      ))}
    </section>
  );
}
