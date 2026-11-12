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

export function MessageContent({ text }: { text: string }) {
  // An unclosed fence (a reply cut short) still renders as code, not as a stray ```.
  return <div className="message-content">{text.split(/(```[\s\S]*?(?:```|$))/g).map((part, i) => {
    if (part.startsWith("```")) {
      const language = (part.match(/^```([\w+#.-]*)/)?.[1] ?? "").toLowerCase();
      const code = part.replace(/^```[^\n]*\n?/, "").replace(/\n?```$/, "");
      return <CodeBlock key={i} language={language} code={code} />;
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
