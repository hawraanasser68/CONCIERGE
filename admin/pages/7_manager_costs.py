# Owner D — platform-manager costs page.
# Visible to tenant_manager only — every other role gets a polite stop.
#
# Calls Owner A's /api/v1/platform/costs. Read-only: shows aggregate token
# and classifier counts per tenant over a rolling window. No tenant content
# is fetched or displayed — this view is by design content-blind.

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

# Anthropic Claude Sonnet 4.6 public list pricing (USD per million tokens).
# Update these constants when the model or pricing changes.
LLM_INPUT_USD_PER_MTOK = 3.0
LLM_OUTPUT_USD_PER_MTOK = 15.0


def llm_cost_usd(tokens_in: int, tokens_out: int) -> float:
    return (
        tokens_in * LLM_INPUT_USD_PER_MTOK / 1_000_000
        + tokens_out * LLM_OUTPUT_USD_PER_MTOK / 1_000_000
    )


if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

if st.session_state.get("role") != "tenant_manager":
    st.warning("This page is for platform managers only.")
    st.stop()

render_user_panel()

st.title("Platform — Costs")
st.caption(
    "Token usage and classifier calls per tenant over a rolling window. "
    "Platform managers see aggregate counts only — no tenant content."
)

# ── Window selector ──────────────────────────────────────────────────────────
window = st.selectbox(
    "Window",
    options=[7, 14, 30, 60, 90],
    index=2,
    format_func=lambda d: f"Last {d} days",
)

# ── Fetch ────────────────────────────────────────────────────────────────────
probe = api_client.get("/api/v1/platform/costs", days=window)

if probe.status_code == 501:
    st.info(
        "⏳ Costs API not yet available. This page will populate once "
        "/api/v1/platform/costs lands."
    )
    st.stop()
if probe.status_code != 200:
    st.error(f"Failed to load costs ({probe.status_code}): {probe.text}")
    st.stop()

rows = probe.json()
if not rows:
    st.info("No tenants on file yet — provision one from the Tenants page.")
    st.stop()

# ── KPI strip (totals across all tenants) ────────────────────────────────────
total_in       = sum(r.get("llm_tokens_in", 0)  for r in rows)
total_out      = sum(r.get("llm_tokens_out", 0) for r in rows)
total_embed    = sum(r.get("embed_tokens", 0)   for r in rows)
total_classify = sum(r.get("classify_calls", 0) for r in rows)

total_llm_cost = llm_cost_usd(total_in, total_out)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("LLM tokens in",  f"{total_in:,}")
k2.metric("LLM tokens out", f"{total_out:,}")
k3.metric(
    "LLM cost (USD)",
    f"${total_llm_cost:,.4f}",
    help=(
        f"USD figure uses public Anthropic list pricing for `claude-sonnet-4-6`: "
        f"${LLM_INPUT_USD_PER_MTOK}/M input + ${LLM_OUTPUT_USD_PER_MTOK}/M output."
    ),
)
k4.metric("Embed tokens",   f"{total_embed:,}")
k5.metric("Classify calls", f"{total_classify:,}")

st.divider()

# ── Per-tenant table ─────────────────────────────────────────────────────────
st.subheader("Per-tenant breakdown")
table_rows = [
    {
        "Slug":           r.get("slug"),
        "Name":           r.get("name"),
        "LLM tokens in":  f"{r.get('llm_tokens_in', 0):,}",
        "LLM tokens out": f"{r.get('llm_tokens_out', 0):,}",
        "LLM cost (USD)": f"${llm_cost_usd(r.get('llm_tokens_in', 0), r.get('llm_tokens_out', 0)):,.4f}",
        "Embed tokens":   f"{r.get('embed_tokens', 0):,}",
        "Classify calls": f"{r.get('classify_calls', 0):,}",
    }
    for r in rows
]
st.dataframe(table_rows, use_container_width=True, hide_index=True)
