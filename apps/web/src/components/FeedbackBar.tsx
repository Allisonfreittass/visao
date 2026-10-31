import { useState } from "react";

const TAGS = ["muito longo", "muito curto", "faltou fonte", "perguntas demais"];

interface Props {
  onSend: (rating: 1 | -1, tags: string[]) => Promise<string | null>;
}

/** Feedback on one reply: the only evidence the behavior state learns from. */
export function FeedbackBar({ onSend }: Props) {
  const [tags, setTags] = useState<string[]>([]);
  const [done, setDone] = useState<string | null>(null);

  if (done) return <p className="feedback-done">{done}</p>;

  const toggle = (tag: string) =>
    setTags((current) =>
      current.includes(tag) ? current.filter((t) => t !== tag) : [...current, tag],
    );
  const send = async (rating: 1 | -1) => setDone((await onSend(rating, tags)) ?? "Obrigado.");

  return (
    <div className="feedback" aria-label="Avaliar resposta">
      <button className="ghost" onClick={() => send(1)} aria-label="Resposta boa">
        👍
      </button>
      <button className="ghost" onClick={() => send(-1)} aria-label="Resposta ruim">
        👎
      </button>
      {TAGS.map((tag) => (
        <button
          key={tag}
          className={tags.includes(tag) ? "chip active" : "chip ghost"}
          onClick={() => toggle(tag)}
          aria-pressed={tags.includes(tag)}
        >
          {tag}
        </button>
      ))}
    </div>
  );
}
