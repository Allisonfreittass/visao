import type { ReactNode } from "react";

/** A small, escaped subset of Markdown. HTML and executable URL schemes stay plain text. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
    if (link) return <a key={i} href={link[2]} target="_blank" rel="noopener noreferrer">{link[1]}</a>;
    return part;
  });
}

export function MessageContent({ text }: { text: string }) {
  return <div className="message-content">{text.split(/(```[\s\S]*?```)/g).map((part, i) => {
    if (part.startsWith("```")) {
      const code = part.replace(/^```[^\n]*\n?/, "").replace(/```$/, "");
      return <pre key={i}><code>{code}</code></pre>;
    }
    return part.split(/\n\s*\n/).filter(Boolean).map((block, j) => {
      const lines = block.split("\n");
      if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
        return <ul key={`${i}-${j}`}>{lines.map((line, k) => <li key={k}>{inline(line.replace(/^\s*[-*]\s+/, ""))}</li>)}</ul>;
      }
      if (lines.every((line) => /^\s*\d+\.\s+/.test(line))) {
        return <ol key={`${i}-${j}`}>{lines.map((line, k) => <li key={k}>{inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>)}</ol>;
      }
      if (/^#{1,6}\s+/.test(block)) return <h4 key={`${i}-${j}`}>{inline(block.replace(/^#{1,6}\s+/, ""))}</h4>;
      return <p key={`${i}-${j}`}>{inline(block)}</p>;
    });
  })}</div>;
}
