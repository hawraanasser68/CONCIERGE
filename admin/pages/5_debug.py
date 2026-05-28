# Owner D — Debug & Trace console.
#
# The agent's tool choices, classifier intents, RAG retrievals, and LLM calls
# all emit OpenTelemetry spans (see backend/app/tracing.py). Spans land in
# Jaeger, which the docker-compose stack already runs at localhost:16686.
#
# This page embeds the Jaeger UI in an iframe so a tenant_admin can trace
# any chat turn end-to-end without leaving the admin app.
# It also surfaces recent leads + escalations as a quick "what did the agent
# decide" timeline derived from real DB rows.

import os

import streamlit as st
import streamlit.components.v1 as components

from lib import api_client
from lib.sidebar import render_user_panel

JAEGER_URL = os.environ.get("JAEGER_URL", "http://localhost:16686")

if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

render_user_panel()

st.title("Debug & Trace")
st.caption(
    "Every chat turn emits OpenTelemetry spans for classifier, router, agent, "
    "tool calls, RAG retrieval, and LLM calls. Use the Jaeger console below "
    "(filter by service `concierge-backend`) to follow a single turn through "
    "the full stack. The timeline on the right shows recent agent decisions "
    "as visible in DB rows."
)

# ── Layout: Jaeger embed (left, wide) + decision timeline (right) ────────────

trace_col, timeline_col = st.columns([3, 2])

with trace_col:
    st.subheader("Jaeger trace explorer")
    st.markdown(f"Open in a new tab: [{JAEGER_URL}]({JAEGER_URL})")
    try:
        components.iframe(JAEGER_URL, height=720, scrolling=True)
    except Exception as e:
        st.error(f"Could not embed Jaeger UI: {e}")
        st.info(
            "If the iframe is blank, your browser may be blocking the cross-origin frame. "
            "Open the link above in a new tab instead."
        )

with timeline_col:
    st.subheader("Recent agent decisions")

    # Recent leads (capture_lead tool fired)
    leads_resp = api_client.get("/api/v1/admin/leads", page=1, page_size=10)
    if leads_resp.status_code == 200:
        leads = leads_resp.json()
        if leads:
            st.markdown("**🧲 capture_lead**")
            for lead in leads[:5]:
                ts = lead.get("created_at", "")[:19].replace("T", " ")
                name = lead.get("visitor_name") or "(anon)"
                intent = (lead.get("intent") or "")[:80]
                st.markdown(f"- _{ts}_ — **{name}**: {intent}")
        else:
            st.caption("No capture_lead calls yet.")
    else:
        st.warning(f"Leads endpoint returned {leads_resp.status_code}")

    st.divider()

    # Recent escalations (escalate tool fired)
    esc_resp = api_client.get("/api/v1/admin/escalations", page=1, page_size=10)
    if esc_resp.status_code == 200:
        escalations = esc_resp.json()
        if escalations:
            st.markdown("**🚨 escalate**")
            for esc in escalations[:5]:
                ts = esc.get("created_at", "")[:19].replace("T", " ")
                reason = (esc.get("reason") or "")[:80]
                status = esc.get("status", "open")
                st.markdown(f"- _{ts}_ — `{status}` · {reason}")
        else:
            st.caption("No escalate calls yet.")
    else:
        st.warning(f"Escalations endpoint returned {esc_resp.status_code}")

    st.divider()
    st.markdown("**🔍 rag_search**")
    st.caption("RAG retrievals are visible in Jaeger spans (`rag.retrieve`) — no DB row is written.")
