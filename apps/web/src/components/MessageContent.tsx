import { type ReactNode, useState } from "react";

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

/** A code block with its language and a copy button: the part of a reply meant to be used. */
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }
  return (
    <figure className="code-block">
      <figcaption>
        <span>{language || "código"}</span>
        <button type="button" className="link-button" onClick={copy} aria-live="polite">
          {copied ? "✓ Copiado" : "Copiar"}
        </button>
      </figcaption>
      <pre><code>{code}</code></pre>
    </figure>
  );
}

const INLINE_MARK = /\*\*|`|\[[^\]]*\]\(/;

/** The last paragraph while the text comes in: the newest chunks fade in (stream.ts). Only plain
 * text is split, so a half-written ** or link is never torn apart. */
function freshParagraph(block: string, start: number, chunks: number[], key: string): ReactNode {
  const cuts = chunks.map((c) => c - start).filter((c) => c > 0 && c < block.length);
  if (cuts.length === 0 || INLINE_MARK.test(block)) return <p key={key}>{inline(block)}</p>;
  const edges = [0, ...cuts, block.length];
  return (
    <p key={key}>
      {edges.slice(0, -1).map((from, n) => (
        <span key={start + from} className={n === 0 ? undefined : "reveal-fresh"}>
          {block.slice(from, edges[n + 1])}
        </span>
      ))}
    </p>
  );
}

/** Stable while it grows: an open code block is already a code block, an unfinished list is a
 * list, so nothing jumps from one shape to another as the text comes in. */
export function MessageContent({ text, chunks }: { text: string; chunks?: number[] }) {
  const segments = text.split(/(```[\s\S]*?(?:```|$))/g);
  // An unclosed fence (a reply cut short, or still being written) renders as code, not as ```.
  return <div className="message-content">{segments.map((part, i) => {
    if (part.startsWith("```")) {
      const language = (part.match(/^```([\w+#.-]*)/)?.[1] ?? "").toLowerCase();
      const code = part.replace(/^```[^\n]*\n?/, "").replace(/\n?```$/, "");
      return <CodeBlock key={i} language={language} code={code} />;
    }
    const blocks = part.split(/\n\s*\n/).filter(Boolean);
    const lastSegment = i === segments.length - 1 || segments.slice(i + 1).every((s) => !s);
    return blocks.map((block, j) => {
      const lines = block.split("\n");
      if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
        return <ul key={`${i}-${j}`}>{lines.map((line, k) => <li key={k}>{inline(line.replace(/^\s*[-*]\s+/, ""))}</li>)}</ul>;
      }
      if (lines.every((line) => /^\s*\d+\.\s+/.test(line))) {
        return <ol key={`${i}-${j}`}>{lines.map((line, k) => <li key={k}>{inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>)}</ol>;
      }
      if (/^#{1,6}\s+/.test(block)) return <h4 key={`${i}-${j}`}>{inline(block.replace(/^#{1,6}\s+/, ""))}</h4>;
      if (chunks && lastSegment && j === blocks.length - 1) {
        return freshParagraph(block, text.lastIndexOf(block), chunks, `${i}-${j}`);
      }
      return <p key={`${i}-${j}`}>{inline(block)}</p>;
    });
  })}</div>;
}
