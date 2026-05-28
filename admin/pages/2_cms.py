# Owner D — D-020: CMS pages — list, create, update, delete, publish toggle.
# Hits Owner B's /api/v1/cms/* routes. If the endpoint isn't live (501) the page
# degrades to a "not yet available" notice instead of erroring out.

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

render_user_panel()

st.title("CMS Pages")

# ── Probe ─────────────────────────────────────────────────────────────────────
probe = api_client.get("/api/v1/cms/pages")
if probe.status_code == 501:
    st.info("⏳ CMS API not yet available (Owner B). This page will populate once it lands.")
    st.stop()
if probe.status_code != 200:
    st.error(f"Failed to load CMS pages ({probe.status_code}).")
    st.stop()

# ── Create form ───────────────────────────────────────────────────────────────
with st.expander("Create a new page"):
    with st.form("create_cms"):
        title = st.text_input("Title")
        slug = st.text_input("Slug", help="URL-friendly identifier, e.g. about-us")
        content = st.text_area("Content (Markdown)", height=200)
        published = st.checkbox("Published", value=False)
        submitted = st.form_submit_button("Create")

    if submitted:
        if not title or not slug or not content:
            st.error("Title, slug, and content are required.")
        else:
            response = api_client.post(
                "/api/v1/cms/pages",
                json={
                    "title": title,
                    "slug": slug,
                    "content": content,
                    "published": published,
                },
            )
            if response.status_code in (200, 201):
                st.success("Page created. Indexing into RAG runs in the background.")
                st.rerun()
            else:
                st.error(f"Create failed ({response.status_code}): {response.text}")

# ── List + edit + delete ──────────────────────────────────────────────────────
pages = probe.json()
if not pages:
    st.info("No CMS pages yet — create one above.")

for page in pages:
    badge = "🟢 published" if page.get("published") else "⚫ draft"
    indexing = page.get("indexing_status")
    indexing_badge = " · 🔄 indexing in progress" if indexing == "pending" else ""
    with st.expander(f"{page.get('title', 'untitled')} ({page.get('slug', '?')}) — {badge}{indexing_badge}"):
        with st.form(f"edit-{page['id']}"):
            new_title = st.text_input("Title", value=page.get("title", ""), key=f"t-{page['id']}")
            new_slug = st.text_input("Slug", value=page.get("slug", ""), key=f"s-{page['id']}")
            new_content = st.text_area(
                "Content (Markdown)",
                value=page.get("content", ""),
                height=200,
                key=f"c-{page['id']}",
            )
            new_published = st.checkbox(
                "Published",
                value=bool(page.get("published")),
                key=f"p-{page['id']}",
            )
            col_save, col_delete = st.columns(2)
            with col_save:
                save = st.form_submit_button("Save")
            with col_delete:
                delete = st.form_submit_button("Delete", type="secondary")

        if save:
            r = api_client.put(
                f"/api/v1/cms/pages/{page['id']}",
                json={
                    "title": new_title,
                    "slug": new_slug,
                    "content": new_content,
                    "published": new_published,
                },
            )
            if r.status_code == 200:
                st.success("Saved. Re-indexing in the background.")
                st.rerun()
            else:
                st.error(f"Save failed ({r.status_code}): {r.text}")

        if delete:
            r = api_client.delete(f"/api/v1/cms/pages/{page['id']}")
            if r.status_code in (200, 204):
                st.rerun()
            else:
                st.error(f"Delete failed ({r.status_code}).")
