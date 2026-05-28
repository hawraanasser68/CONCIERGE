# Owner D — D-021: agent + guardrail config page.
# Lets a tenant_admin edit persona, enabled tools, topic rails, and the
# tool-iteration cap. Platform-level rails (injection, jailbreak, cross-tenant,
# PII) are deliberately NOT shown — they're locked and not tenant-editable.

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

AVAILABLE_TOOLS = ["rag_search", "capture_lead", "escalate"]

if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

render_user_panel()

st.title("Agent & Guardrails")
st.caption(
    "Platform security rails (prompt-injection, jailbreak detection, "
    "cross-tenant defense, PII redaction) are always active and cannot be "
    "modified here."
)

response = api_client.get("/api/v1/admin/agent-config")
if response.status_code != 200:
    st.error(f"Failed to load agent config ({response.status_code}).")
    st.stop()

config = response.json()

with st.form("agent_config_form"):
    persona_name = st.text_input("Persona name", value=config.get("persona_name", ""))
    persona_description = st.text_area(
        "Persona description",
        value=config.get("persona_description", ""),
        height=120,
    )
    enabled_tools = st.multiselect(
        "Enabled tools",
        options=AVAILABLE_TOOLS,
        default=[t for t in config.get("enabled_tools", []) if t in AVAILABLE_TOOLS],
    )
    blocked_topics_text = st.text_area(
        "Blocked topics (comma-separated)",
        value=", ".join(config.get("blocked_topics", [])),
    )
    allowed_topics_text = st.text_area(
        "Allowed topics (comma-separated)",
        value=", ".join(config.get("allowed_topics", [])),
    )
    max_iterations = st.number_input(
        "Max tool iterations per turn",
        min_value=1,
        max_value=10,
        value=int(config.get("max_tool_iterations", 5)),
        step=1,
    )
    submitted = st.form_submit_button("Save")

if submitted:
    body = {
        "persona_name": persona_name,
        "persona_description": persona_description,
        "enabled_tools": enabled_tools,
        "blocked_topics": [t.strip() for t in blocked_topics_text.split(",") if t.strip()],
        "allowed_topics": [t.strip() for t in allowed_topics_text.split(",") if t.strip()],
        "max_tool_iterations": int(max_iterations),
    }
    r = api_client.put("/api/v1/admin/agent-config", json=body)
    if r.status_code == 200:
        st.success("Saved.")
        st.rerun()
    else:
        st.error(f"Save failed ({r.status_code}): {r.text}")
