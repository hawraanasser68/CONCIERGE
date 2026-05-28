# Owner D — D-022: paginated lead inbox.
# Read-only. Owner B's capture_lead tool writes the rows; this page only displays.

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

PAGE_SIZE = 20

if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

render_user_panel()

st.title("Leads")

if "leads_page" not in st.session_state:
    st.session_state["leads_page"] = 1

page = st.session_state["leads_page"]

response = api_client.get("/api/v1/admin/leads", page=page, page_size=PAGE_SIZE)
if response.status_code != 200:
    st.error(f"Failed to load leads ({response.status_code}).")
    st.stop()

leads = response.json()

if not leads and page == 1:
    st.info("No leads yet — they appear here once the agent's capture_lead tool fires.")
    st.stop()

if not leads:
    st.info("End of list.")
else:
    rows = [
        {
            "Name": lead.get("visitor_name", ""),
            "Contact": lead.get("contact", ""),
            "Intent": lead.get("intent", ""),
            "Created": lead.get("created_at", ""),
            "Score": lead.get("classifier_score", ""),
        }
        for lead in leads
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

# ── Pagination ────────────────────────────────────────────────────────────────
prev_col, mid_col, next_col = st.columns([1, 6, 1])
with prev_col:
    if page > 1 and st.button("← Previous"):
        st.session_state["leads_page"] -= 1
        st.rerun()
with mid_col:
    st.write(f"Page {page}")
with next_col:
    if len(leads) == PAGE_SIZE and st.button("Next →"):
        st.session_state["leads_page"] += 1
        st.rerun()
