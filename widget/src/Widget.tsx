// Owner D - chat UI rendered inside the iframe.
// On mount: pulls token + session_id + widget_id from window.location.hash,
// fetches /widget/{id}/config, shows the greeting. On send: POSTs to /chat/message
// and maps known error statuses (401/429/501/503) to user-facing text.
// Close (X) posts "concierge:close" to the parent loader, which hides the iframe.

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  extractSessionFromHash,
  getConfig,
  sendMessage,
  setSession,
  type WidgetConfig,
} from "./api";
import { themeStyles, type MessageRole } from "./theme";

interface Message {
  role: MessageRole;
  text: string;
}

const ERROR_TEXT: Record<string, string> = {
  expired: "Session expired - please refresh the page.",
  rate_limit: "Too many messages - please wait a moment.",
  unavailable: "I'm having trouble right now - please try again.",
  error: "Something went wrong. Please try again.",
};

function closeToParent(): void {
  try {
    window.parent.postMessage("concierge:close", "*");
  } catch (_) {
    // No parent (e.g. opened directly) - silently ignore.
  }
}

export function Widget(): JSX.Element {
  const [config, setConfig] = useState<WidgetConfig | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const session = extractSessionFromHash();
    if (!session) {
      setMessages([
        { role: "system", text: "Widget session missing. Reload the host page." },
      ]);
      return;
    }
    setSession(session.token, session.sessionId);

    getConfig(session.widgetId)
      .then((cfg) => {
        setConfig(cfg);
        setMessages([{ role: "assistant", text: cfg.greeting }]);
      })
      .catch(() => {
        setMessages([
          { role: "system", text: "Failed to load widget config." },
        ]);
      });
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(): Promise<void> {
    const text = input.trim();
    if (!text || sending || !config) return;

    setInput("");
    setSending(true);
    setMessages((prev) => [...prev, { role: "user", text }]);

    const result = await sendMessage(text);
    if (result.ok) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: result.reply },
      ]);
    } else {
      setMessages((prev) => [
        ...prev,
        { role: "system", text: ERROR_TEXT[result.code] },
      ]);
    }
    setSending(false);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  const styles = themeStyles(config?.theme.primary_color ?? "#0066cc");
  const ready = config !== null;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.headerTitle}>{config?.persona_name ?? "Concierge"}</div>
        <button
          type="button"
          aria-label="Close chat"
          title="Close"
          style={styles.closeBtn}
          onClick={closeToParent}
        >
          {/* X icon */}
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div style={styles.messages}>
        {messages.map((m, i) => (
          <div key={i} style={styles.bubble(m.role)}>
            {m.text}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div style={styles.inputRow}>
        <input
          style={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={ready ? "Message Bloom..." : "Loading..."}
          disabled={!ready || sending}
        />
        <button
          type="button"
          aria-label="Send message"
          title="Send"
          style={{
            ...styles.button,
            opacity: !ready || sending || !input.trim() ? 0.5 : 1,
            cursor: !ready || sending || !input.trim() ? "default" : "pointer",
          }}
          onClick={() => void handleSend()}
          disabled={!ready || sending || !input.trim()}
        >
          {/* Up-arrow send icon */}
          <svg
            style={styles.buttonIcon}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="12" y1="19" x2="12" y2="5" />
            <polyline points="5 12 12 5 19 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
