// Owner D - per-tenant theme tokens.
// Primary color comes from the /widget/{id}/config endpoint at runtime; everything
// else is design tokens that stay constant across tenants. Inline styles only - no
// CSS file shipped, which keeps the bundle under the 100KB gzipped budget.
//
// ChatGPT-inspired layout: minimal header with close, scrollable message list with
// bubbles aligned by role (user right, assistant left), rounded pill input + send.

import type { CSSProperties } from "react";

export type MessageRole = "user" | "assistant" | "system";

export interface ThemeStyles {
  container: CSSProperties;
  header: CSSProperties;
  headerTitle: CSSProperties;
  closeBtn: CSSProperties;
  messages: CSSProperties;
  bubble: (role: MessageRole) => CSSProperties;
  inputRow: CSSProperties;
  input: CSSProperties;
  button: CSSProperties;
  buttonIcon: CSSProperties;
}

// Florist palette - matches the Bloom Florista host page.
const ROSE      = "#c8607a";
const ROSE_DARK = "#8e4055";
const ROSE_SOFT = "#f6e3e8";
const CREAM     = "#faf6f1";
const SAGE_SOFT = "#eaf0e3";
const INK       = "#2c2420";
const MUTED     = "#6b5d56";
const BORDER    = "rgba(0,0,0,0.08)";

export function themeStyles(primaryColorFromBackend: string): ThemeStyles {
  // We intentionally ignore the backend's primary_color for now and use the
  // florist palette so the widget visually matches the host page. The argument
  // is kept so the call site contract does not change; a future improvement is
  // per-tenant theme objects from /widget/{id}/config.
  void primaryColorFromBackend;
  const primary = ROSE;

  return {
    container: {
      display: "flex",
      flexDirection: "column",
      height: "100vh",
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      background: "#fff",
      color: INK,
      overflow: "hidden",
    },
    header: {
      padding: "14px 16px",
      background: "#fff",
      borderBottom: `1px solid ${BORDER}`,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 8,
    },
    headerTitle: {
      fontWeight: 600,
      fontSize: 15,
      color: INK,
      letterSpacing: "-0.01em",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
    },
    closeBtn: {
      width: 30,
      height: 30,
      border: "none",
      borderRadius: 8,
      background: "transparent",
      color: MUTED,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 18,
      lineHeight: 1,
    },
    messages: {
      flex: 1,
      overflowY: "auto",
      padding: "16px",
      display: "flex",
      flexDirection: "column",
      gap: 10,
      background: CREAM,
    },
    bubble: (role) => {
      const base: CSSProperties = {
        maxWidth: "85%",
        padding: "10px 14px",
        borderRadius: 16,
        fontSize: 14,
        lineHeight: 1.45,
        wordBreak: "break-word",
        whiteSpace: "pre-wrap",
      };
      if (role === "user") {
        return {
          ...base,
          alignSelf: "flex-end",
          background: primary,
          color: "#fff",
          borderBottomRightRadius: 4,
        };
      }
      if (role === "system") {
        return {
          ...base,
          alignSelf: "center",
          background: ROSE_SOFT,
          color: ROSE_DARK,
          fontSize: 13,
          maxWidth: "92%",
          textAlign: "center",
          borderRadius: 12,
          padding: "8px 14px",
        };
      }
      return {
        ...base,
        alignSelf: "flex-start",
        background: "#fff",
        color: INK,
        border: `1px solid ${BORDER}`,
        borderBottomLeftRadius: 4,
      };
    },
    inputRow: {
      display: "flex",
      gap: 8,
      padding: "12px",
      background: "#fff",
      borderTop: `1px solid ${BORDER}`,
      alignItems: "center",
    },
    input: {
      flex: 1,
      padding: "10px 16px",
      border: `1px solid ${BORDER}`,
      borderRadius: 999,
      fontSize: 14,
      outline: "none",
      background: SAGE_SOFT,
      color: INK,
    },
    button: {
      width: 38,
      height: 38,
      flexShrink: 0,
      background: primary,
      color: "#fff",
      border: "none",
      borderRadius: "50%",
      fontSize: 14,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      transition: "background 0.15s ease",
    },
    buttonIcon: {
      width: 18,
      height: 18,
      display: "block",
    },
  };
}
