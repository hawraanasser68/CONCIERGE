# Owner D — D-019: widget management page.
# List + search + create + toggle active + delete + ready-to-paste embed snippet per widget.

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

render_user_panel()

st.title("Widgets")

# ── Create form ───────────────────────────────────────────────────────────────
with st.expander("Create a new widget"):
    with st.form("create_widget"):
        name = st.text_input("Name")
        origins_text = st.text_area(
            "Allowed origins (one per line)",
            help="Each origin must match the embedding site exactly, including scheme. "
            "e.g. https://example.com",
        )
        greeting = st.text_input("Greeting", value="Hi! How can I help you today?")
        persona = st.text_input("Persona name", value="Assistant")
        submitted = st.form_submit_button("Create")

    if submitted:
        allowed_origins = [o.strip() for o in origins_text.splitlines() if o.strip()]
        if not name or not allowed_origins:
            st.error("Name and at least one allowed origin are required.")
        else:
            response = api_client.post(
                "/api/v1/admin/widgets",
                json={
                    "name": name,
                    "allowed_origins": allowed_origins,
                    "greeting": greeting,
                    "persona_name": persona,
                },
            )
            if response.status_code in (200, 201):
                st.success("Widget created.")
                st.rerun()
            else:
                st.error(f"Create failed ({response.status_code}): {response.text}")

# ── List ──────────────────────────────────────────────────────────────────────
st.subheader("Existing widgets")
list_response = api_client.get("/api/v1/admin/widgets")
if list_response.status_code != 200:
    st.error(f"Failed to load widgets ({list_response.status_code}).")
    st.stop()

widgets = list_response.json()

# Search + status filter
search_col, status_col = st.columns([3, 1])
with search_col:
    query = st.text_input("Search by name or origin", placeholder="e.g. bloom or localhost")
with status_col:
    status_filter = st.selectbox("Status", ["all", "active", "inactive"])

def _matches(widget: dict) -> bool:
    if status_filter == "active" and not widget["is_active"]:
        return False
    if status_filter == "inactive" and widget["is_active"]:
        return False
    if query:
        haystack = (widget["name"] + " " + " ".join(widget["allowed_origins"])).lower()
        if query.lower() not in haystack:
            return False
    return True


filtered = [w for w in widgets if _matches(w)]

if not widgets:
    st.info("No widgets yet — create one above.")
elif not filtered:
    st.info(f"No widgets match the current filter ({len(widgets)} total).")
else:
    st.caption(f"Showing {len(filtered)} of {len(widgets)} widgets.")

for widget in filtered:
    status_icon = "🟢 active" if widget["is_active"] else "⚫ inactive"
    with st.expander(f"{widget['name']} — {status_icon}"):
        left, right = st.columns([2, 1])

        with left:
            st.write(f"**ID:** `{widget['id']}`")
            st.write(f"**Greeting:** {widget['greeting']}")
            st.write(f"**Persona:** {widget['persona_name']}")
            st.write("**Allowed origins:**")
            for origin in widget["allowed_origins"]:
                st.code(origin, language=None)

        with right:
            toggle_label = "Deactivate" if widget["is_active"] else "Activate"
            if st.button(toggle_label, key=f"toggle-{widget['id']}"):
                r = api_client.patch(f"/api/v1/admin/widgets/{widget['id']}/toggle")
                if r.status_code == 200:
                    st.rerun()
                else:
                    st.error(f"Toggle failed ({r.status_code}).")

            if st.button("Delete", key=f"delete-{widget['id']}", type="secondary"):
                r = api_client.delete(f"/api/v1/admin/widgets/{widget['id']}")
                if r.status_code in (200, 204):
                    st.rerun()
                else:
                    st.error(f"Delete failed ({r.status_code}).")

        st.markdown("**Embed snippet** — paste into the host site `<head>` or before `</body>`:")
        snippet = (
            "<script\n"
            f'  src="{api_client.WIDGET_PUBLIC_URL}/widget.js"\n'
            f'  data-widget-id="{widget["id"]}"\n'
            "></script>"
        )
        st.code(snippet, language="html")
