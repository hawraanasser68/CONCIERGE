// Owner D — Phase 3 D-014: chat UI rendered inside the iframe.
// On mount: pulls token + session_id + widget_id from window.location.hash,
// fetches /widget/{id}/config, shows the greeting. On send: POSTs to /chat/message
// and maps known error statuses (401/429/501/503) to user-facing text.

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
  expired: "Session expired — please refresh the page.",
  rate_limit: "Too many messages — please wait a moment.",
  unavailable: "I'm having trouble right now — please try again.",
  error: "Something went wrong. Please try again.",
};

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
      <div style={styles.header}>{config?.persona_name ?? "Concierge"}</div>
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
          placeholder={ready ? "Type a message..." : "Loading..."}
          disabled={!ready || sending}
        />
        <button
          style={styles.button}
          onClick={() => void handleSend()}
          disabled={!ready || sending || !input.trim()}
        >
          {sending ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}
