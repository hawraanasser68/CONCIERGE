// Owner D — Phase 3 D-013: per-tenant theme.
// Primary color comes from the /widget/{id}/config endpoint at runtime; everything
// else is design tokens that stay constant across tenants. Inline styles only — no
// CSS file shipped, which keeps the bundle under the 100KB gzipped budget.

import type { CSSProperties } from "react";

export type MessageRole = "user" | "assistant" | "system";

export interface ThemeStyles {
  container: CSSProperties;
  header: CSSProperties;
  messages: CSSProperties;
  bubble: (role: MessageRole) => CSSProperties;
  inputRow: CSSProperties;
  input: CSSProperties;
  button: CSSProperties;
}

export function themeStyles(primaryColor: string): ThemeStyles {
  return {
    container: {
      display: "flex",
      flexDirection: "column",
      height: "100vh",
      fontFamily: "system-ui, -apple-system, sans-serif",
      background: "#fff",
    },
    header: {
      padding: "12px 16px",
      background: primaryColor,
      color: "#fff",
      fontWeight: 600,
      fontSize: 15,
    },
    messages: {
      flex: 1,
      overflowY: "auto",
      padding: "12px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
    },
    bubble: (role) => ({
      maxWidth: "80%",
      padding: "8px 12px",
      borderRadius: 12,
      alignSelf:
        role === "user"
          ? "flex-end"
          : role === "system"
          ? "center"
          : "flex-start",
      background:
        role === "user"
          ? primaryColor
          : role === "system"
          ? "#fde2e2"
          : "#f0f0f0",
      color: role === "user" ? "#fff" : role === "system" ? "#7a1f1f" : "#222",
      fontSize: 14,
      lineHeight: 1.4,
      wordBreak: "break-word",
    }),
    inputRow: {
      display: "flex",
      gap: 8,
      padding: 12,
      borderTop: "1px solid #eee",
    },
    input: {
      flex: 1,
      padding: "8px 12px",
      border: "1px solid #ddd",
      borderRadius: 6,
      fontSize: 14,
      outline: "none",
    },
    button: {
      padding: "8px 16px",
      background: primaryColor,
      color: "#fff",
      border: "none",
      borderRadius: 6,
      fontSize: 14,
      cursor: "pointer",
    },
  };
}
