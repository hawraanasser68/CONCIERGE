// Owner D — Phase 3 D-012: widget iframe API client.
// Token + sessionId live in module-scope closure — never localStorage / sessionStorage.
// Every chat request carries Authorization: Bearer + X-Session-Id headers.

const API_BASE = window.location.origin;

let _token: string | null = null;
let _sessionId: string | null = null;

export interface WidgetTheme {
  primary_color: string;
}

export interface WidgetConfig {
  greeting: string;
  persona_name: string;
  theme: WidgetTheme;
}

export type ChatResult =
  | { ok: true; reply: string }
  | { ok: false; code: "expired" | "rate_limit" | "unavailable" | "error" };

export function setSession(token: string, sessionId: string): void {
  _token = token;
  _sessionId = sessionId;
}

export function extractSessionFromHash(): {
  token: string;
  sessionId: string;
  widgetId: string;
} | null {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const token = params.get("token");
  const sessionId = params.get("session_id");
  const widgetId = params.get("widget_id");
  if (!token || !sessionId || !widgetId) return null;
  return { token, sessionId, widgetId };
}

export async function getConfig(widgetId: string): Promise<WidgetConfig> {
  const response = await fetch(
    `${API_BASE}/api/v1/widget/${encodeURIComponent(widgetId)}/config`,
    { credentials: "omit" }
  );
  if (!response.ok) {
    throw new Error(`config fetch failed: ${response.status}`);
  }
  return (await response.json()) as WidgetConfig;
}

export async function sendMessage(message: string): Promise<ChatResult> {
  if (!_token || !_sessionId) {
    return { ok: false, code: "expired" };
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/chat/message`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${_token}`,
        "X-Session-Id": _sessionId,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
      credentials: "omit",
    });
  } catch {
    return { ok: false, code: "unavailable" };
  }

  if (response.status === 401) return { ok: false, code: "expired" };
  if (response.status === 429) return { ok: false, code: "rate_limit" };
  // 501 added alongside 503 so we degrade gracefully while Owner B's chat.py
  // is still a stub. Both surface to the user as "service unavailable".
  if (response.status === 503 || response.status === 501) {
    return { ok: false, code: "unavailable" };
  }
  if (!response.ok) return { ok: false, code: "error" };

  try {
    const data = (await response.json()) as { reply?: string };
    return { ok: true, reply: data.reply ?? "" };
  } catch {
    return { ok: false, code: "error" };
  }
}
