import { useCallback, useEffect, useState } from "react";

import type { Api, AppNotification } from "../api";

/** Invitations stay visible even when the conversation menu is closed. */
export function NotificationFeed({ api, current, onError, onReply }: {
  api: Api;
  current: string | null;
  onError: (e: unknown) => void;
  onReply: (conversationId: string) => void;
}) {
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

  async function reply(id: string) {
    try {
      const { conversation_id: conversationId } = await api.replyToNotification(id, current);
      await refresh();
      onReply(conversationId);
    } catch (e) { onError(e); }
  }

  const unread = notifications.filter((item) => !item.read_at);
  if (!unread.length) return null;
  return (
    <section className="notification-feed" aria-label="Iniciativas do VISÃO" aria-live="polite">
      {unread.map((item) => (
        <div className="card" key={item.id}>
          <strong>{item.title}</strong>
          <p className="note pre">{item.body}</p>
          <div className="notification-actions">
            <button onClick={() => void reply(item.id)}>Responder</button>
            <button className="ghost" onClick={() => void dismiss(item.id)}>Dispensar aviso</button>
          </div>
        </div>
      ))}
    </section>
  );
}
