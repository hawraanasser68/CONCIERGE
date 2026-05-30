# Owner D — escalations inbox.
# Read-only paginated list. Owner B's `escalate` tool writes rows; this page only displays.
# Mirrors the Leads page layout for consistency.

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

PAGE_SIZE = 20

if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

render_user_panel()

st.title("Escalations")

# ── Status filter ───────────────────────────────────────────────────────────
status_filter = st.selectbox(
    "Status",
    options=["all", "open", "resolved", "closed"],
    index=0,
)

if "esc_page" not in st.session_state:
    st.session_state["esc_page"] = 1

page = st.session_state["esc_page"]

params: dict[str, int | str] = {"page": page, "page_size": PAGE_SIZE}
if status_filter != "all":
    params["status"] = status_filter

response = api_client.get("/api/v1/admin/escalations", **params)
if response.status_code != 200:
    st.error(f"Failed to load escalations ({response.status_code}).")
    st.stop()

escalations = response.json()

if not escalations and page == 1:
    st.info("No escalations yet — they show up once the agent fires the escalate tool.")
    st.stop()

if not escalations:
    st.info("End of list.")
else:
    # Full-text view — one expander per row so the long reason isn't truncated.
    for esc in escalations:
        created = (esc.get("created_at") or "")[:19].replace("T", " ")
        status = esc.get("status", "open")
        icon = {"open": "🟠", "resolved": "🟢", "closed": "⚫"}.get(status, "❓")
        preview = (esc.get("reason") or "")[:90]
        with st.expander(f"{icon} {created} — {preview}"):
            st.write(f"**ID:** `{esc.get('id')}`")
            st.write(f"**Session:** `{esc.get('session_id')}`")
            st.write(f"**Status:** {status}")
            st.write(f"**Created:** {created}")
            st.markdown("**Full reason:**")
            st.markdown(f"> {esc.get('reason', '')}")

# ── Pagination ───────────────────────────────────────────────────────────────
prev_col, mid_col, next_col = st.columns([1, 6, 1])
with prev_col:
    if page > 1 and st.button("← Previous"):
        st.session_state["esc_page"] -= 1
        st.rerun()
with mid_col:
    st.write(f"Page {page}")
with next_col:
    if len(escalations) == PAGE_SIZE and st.button("Next →"):
        st.session_state["esc_page"] += 1
        st.rerun()