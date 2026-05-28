# Owner D — platform-manager tenants page.
# Visible to tenant_manager only — every other role gets a polite stop.
#
# Calls Owner A's /api/v1/platform/tenants endpoints (list / create / erase).
# Owner A's manager.py does not currently expose suspend or audit-log read,
# so those actions are deliberately absent here.

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

if "token" not in st.session_state:
    st.warning("Sign in from the home page first.")
    st.stop()

if st.session_state.get("role") != "tenant_manager":
    st.warning("This page is for platform managers only.")
    st.stop()

render_user_panel()

st.title("Platform — Tenants")
st.caption(
    "Provision new tenants and trigger right-to-erasure. "
    "Platform managers cannot read tenant content — these actions are "
    "audit-logged with your actor id."
)

# ── Provisioning form ────────────────────────────────────────────────────────
with st.expander("Provision a new tenant"):
    with st.form("create_tenant"):
        name = st.text_input("Display name", help="e.g. 'Bloom Florista'")
        slug = st.text_input(
            "Slug",
            help="URL-safe identifier, lowercase + hyphens. e.g. 'bloom-florista'",
        )
        submitted = st.form_submit_button("Provision")

    if submitted:
        if not name or not slug:
            st.error("Name and slug are required.")
        else:
            response = api_client.post(
                "/api/v1/platform/tenants",
                json={"name": name, "slug": slug},
            )
            if response.status_code in (200, 201):
                data = response.json()
                st.success(f"Tenant `{slug}` provisioned.")
                invite = data.get("invite_token")
                tenant_id = data.get("tenant_id") or data.get("id")
                if invite:
                    st.info(
                        "Share this **one-time** invite token with the first "
                        "tenant-admin to complete onboarding (expires in 24h):"
                    )
                    st.code(invite, language=None)
                if tenant_id:
                    st.caption(f"tenant_id: `{tenant_id}`")
            else:
                st.error(f"Provision failed ({response.status_code}): {response.text}")

# ── Tenant list ──────────────────────────────────────────────────────────────
st.subheader("All tenants")
list_response = api_client.get("/api/v1/platform/tenants")
if list_response.status_code != 200:
    st.error(f"Failed to load tenants ({list_response.status_code}).")
    st.stop()

tenants = list_response.json()
if not tenants:
    st.info("No tenants yet — provision one above.")

for tenant in tenants:
    status = tenant.get("status", "unknown")
    icon = {"active": "🟢", "suspended": "🟡", "erasing": "🟠", "erased": "⚫"}.get(status, "❓")
    label = f"{icon} {tenant.get('name', '?')} · `{tenant.get('slug', '?')}` — {status}"
    with st.expander(label):
        st.write(f"**ID:** `{tenant.get('id')}`")
        st.write(f"**Slug:** `{tenant.get('slug')}`")
        st.write(f"**Status:** {status}")
        st.write(f"**Created:** {(tenant.get('created_at') or '')[:19].replace('T', ' ')}")
        if tenant.get("erased_at"):
            st.write(f"**Erased at:** {tenant['erased_at'][:19].replace('T', ' ')}")

        if status in {"active", "suspended"}:
            confirm_key = f"erase_confirm_{tenant['id']}"
            if not st.session_state.get(confirm_key):
                if st.button("Erase tenant", key=f"erase_btn_{tenant['id']}", type="secondary"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                st.warning(
                    f"This will permanently delete **all data** for `{tenant.get('slug')}` "
                    "(DB rows, vectors, sessions, blobs). This action is irreversible "
                    "and audit-logged."
                )
                col_confirm, col_cancel = st.columns(2)
                if col_confirm.button("Yes, erase", key=f"erase_yes_{tenant['id']}", type="primary"):
                    r = api_client.delete(f"/api/v1/platform/tenants/{tenant['id']}")
                    st.session_state.pop(confirm_key, None)
                    if r.status_code in (200, 204):
                        st.success(f"Tenant {tenant.get('slug')} erased.")
                        st.rerun()
                    else:
                        st.error(f"Erasure failed ({r.status_code}): {r.text}")
                if col_cancel.button("Cancel", key=f"erase_no_{tenant['id']}"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
