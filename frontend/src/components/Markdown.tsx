import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

// Mermaid is heavy, so it's imported dynamically — it only loads the first time a
// diagram actually needs to render, keeping it out of the main bundle.
let _mermaidPromise: Promise<any> | null = null;
function getMermaid() {
  if (!_mermaidPromise) {
    _mermaidPromise = import("mermaid").then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "dark",
        fontFamily: "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif",
        themeVariables: {
          primaryColor: "#1c232c",
          primaryBorderColor: "#ffb454",
          primaryTextColor: "#e6edf3",
          lineColor: "#8b98a5",
          background: "#161b22",
        },
      });
      return mermaid;
    });
  }
  return _mermaidPromise;
}

let _seq = 0;

function Mermaid({ code }: { code: string }) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const idRef = useRef(`mmd-${_seq++}`);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    getMermaid()
      .then(async (mermaid) => {
        // Validate first (suppressErrors → returns false, and does NOT inject
        // mermaid's default on-screen error graphic). Only render if valid.
        const ok = await mermaid.parse(code, { suppressErrors: true });
        if (!ok) throw new Error("invalid mermaid");
        return mermaid.render(idRef.current, code);
      })
      .then((res: { svg: string }) => { if (!cancelled) setSvg(res.svg); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [code]);

  if (failed) {
    return <pre className="mermaid-fallback"><code>{code}</code></pre>;
  }
  if (!svg) return <div className="mermaid-diagram loading">rendering diagram…</div>;
  return <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}

/** Drop-in replacement for <ReactMarkdown>: also renders ```mermaid blocks as diagrams. */
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={{
        code(props) {
          const { className, children: kids } = props as any;
          const lang = /language-(\w+)/.exec(className || "")?.[1];
          if (lang === "mermaid") {
            return <Mermaid code={String(kids).replace(/\n$/, "")} />;
          }
          return <code className={className}>{kids}</code>;
        },
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
