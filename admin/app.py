# Owner D — D-017: Concierge Admin login + role-based navigation.
#
# Flow:
#   1. If no token in session_state → show login form (st.navigation not used).
#   2. On submit → POST /api/v1/auth/login → store access_token in session_state.
#   3. Probe role by hitting each role's canonical endpoint.
#   4. Build a role-conditional st.navigation() page list so the sidebar only
#      shows pages the signed-in role can actually use. Per-page role guards
#      remain in place as defense-in-depth (they become unreachable through the
#      UI, but still protect against URL-poking and against future regressions).

from datetime import datetime

import streamlit as st

from lib import api_client
from lib.sidebar import render_user_panel

# Must be the FIRST Streamlit command, called exactly once per script run.
# Both the login screen and post-login pages run inside the same script run as
# this entrypoint, so individual pages/callables must NOT call set_page_config.
st.set_page_config(page_title="Concierge Admin", page_icon="🔐", layout="wide")


# ── Login ─────────────────────────────────────────────────────────────────────

def _login_screen() -> None:
    st.title("Concierge Admin — Sign in")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign in")

    if not submit:
        return

    token, error = api_client.login(email, password)
    if error:
        st.error(error)
        return

    st.session_state["token"] = token
    st.session_state["email"] = email

    # Detect role by probing each role's canonical endpoint.
    admin_probe = api_client.get("/api/v1/admin/widgets")
    if admin_probe.status_code == 200:
        st.session_state["role"] = "tenant_admin"
        st.rerun()
        return

    manager_probe = api_client.get("/api/v1/platform/tenants")
    if manager_probe.status_code == 200:
        st.session_state["role"] = "tenant_manager"
        st.rerun()
        return

    # Neither probe succeeded → unauthorized for both.
    st.session_state.pop("token", None)
    st.error("Access denied — this account is neither a tenant admin nor a platform manager.")


# ── Role dashboards (registered as st.Page callables) ─────────────────────────

def _tenant_admin_dashboard() -> None:
    render_user_panel()

    st.title("Concierge — Overview")
    st.caption("Signed in as **tenant_admin**. Use the sidebar to drill into widgets, CMS, guardrails, leads, or the debug console.")

    widgets_resp = api_client.get("/api/v1/admin/widgets")
    leads_resp = api_client.get("/api/v1/admin/leads", page=1, page_size=100)
    escalations_resp = api_client.get("/api/v1/admin/escalations", page=1, page_size=100)

    widgets = widgets_resp.json() if widgets_resp.status_code == 200 else []
    leads = leads_resp.json() if leads_resp.status_code == 200 else []
    escalations = escalations_resp.json() if escalations_resp.status_code == 200 else []

    active_widgets = sum(1 for w in widgets if w.get("is_active"))
    open_escalations = sum(1 for e in escalations if e.get("status") in {None, "open"})

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Active widgets", active_widgets, delta=f"of {len(widgets)} total")
    k2.metric("Leads captured", len(leads))
    k3.metric("Open escalations", open_escalations)
    k4.metric("Recent activity", _humanize_recent(leads + escalations))

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Recent leads")
        if not leads:
            st.info("No leads yet — they show up once the agent fires capture_lead.")
        else:
            for lead in leads[:5]:
                name = lead.get("visitor_name") or "(anonymous)"
                contact = lead.get("contact", "")
                created = lead.get("created_at", "")[:19].replace("T", " ")
                st.markdown(f"- **{name}** · {contact} · _{created}_")

    with right:
        st.subheader("Open escalations")
        open_list = [e for e in escalations if e.get("status") in {None, "open"}][:5]
        if not open_list:
            st.info("No open escalations.")
        else:
            for esc in open_list:
                created = esc.get("created_at", "")[:19].replace("T", " ")
                st.markdown(f"- _{created}_ — {esc.get('reason', '')[:80]}")


def _tenant_manager_dashboard() -> None:
    render_user_panel()

    st.title("Platform — Overview")
    st.caption(
        "Signed in as **tenant_manager**. Use the sidebar to provision new tenants "
        "or trigger GDPR erasure. By design, platform managers cannot read any "
        "tenant's conversations, leads, or CMS content."
    )

    tenants_resp = api_client.get("/api/v1/platform/tenants")
    tenants = tenants_resp.json() if tenants_resp.status_code == 200 else []

    by_status: dict[str, int] = {}
    for t in tenants:
        by_status[t.get("status", "unknown")] = by_status.get(t.get("status", "unknown"), 0) + 1

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total tenants", len(tenants))
    k2.metric("Active", by_status.get("active", 0))
    k3.metric("Suspended", by_status.get("suspended", 0))
    k4.metric("Erased / erasing", by_status.get("erased", 0) + by_status.get("erasing", 0))

    st.divider()
    st.subheader("Tenants")
    if not tenants:
        st.info("No tenants yet — provision one from the Tenants page.")
    else:
        rows = [
            {
                "Slug": t.get("slug"),
                "Name": t.get("name"),
                "Status": t.get("status"),
                "Created": (t.get("created_at") or "")[:19].replace("T", " "),
            }
            for t in tenants
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _humanize_recent(rows: list[dict]) -> str:
    """Return a short label for the most recent created_at across leads+escalations."""
    timestamps = [r.get("created_at") for r in rows if r.get("created_at")]
    if not timestamps:
        return "—"
    latest = max(timestamps)
    try:
        dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
    except ValueError:
        return latest[:10]
    delta = datetime.now(dt.tzinfo) - dt
    if delta.total_seconds() < 3600:
        return f"{int(delta.total_seconds() / 60)}m ago"
    if delta.total_seconds() < 86400:
        return f"{int(delta.total_seconds() / 3600)}h ago"
    return f"{delta.days}d ago"


# ── Router ────────────────────────────────────────────────────────────────────

if "token" not in st.session_state:
    _login_screen()
    st.stop()

role = st.session_state.get("role")

if role == "tenant_admin":
    pages = [
        st.Page(_tenant_admin_dashboard, title="Overview", icon="🏠", default=True, url_path="overview"),
        st.Page("pages/1_widgets.py",   title="Widgets",    icon="🧩"),
        st.Page("pages/2_cms.py",       title="CMS",        icon="📝"),
        st.Page("pages/3_guardrails.py",title="Guardrails", icon="🛡️"),
        st.Page("pages/4_leads.py",     title="Leads",      icon="📥"),
        st.Page("pages/escalations.py", title="Escalations", icon="🚨"),
        st.Page("pages/5_debug.py",     title="Debug",      icon="🔧"),
    ]
elif role == "tenant_manager":
    pages = [
        st.Page(_tenant_manager_dashboard, title="Platform Overview", icon="🏠", default=True, url_path="overview"),
        st.Page("pages/6_manager_tenants.py", title="Tenants", icon="🏢"),
        st.Page("pages/7_manager_costs.py",   title="Costs",   icon="💰"),
    ]
else:
    st.error("Unknown role on session; please sign in again.")
    if st.button("Sign out"):
        st.session_state.clear()
        st.rerun()
    st.stop()

pg = st.navigation(pages)
pg.run()
