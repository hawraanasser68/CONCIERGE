# Owner D — shared sidebar widget rendered on every page.
# Shows the signed-in email (captured at login) and a Sign-out button that
# pops up a confirmation dialog before clearing the session.
#
# Tenant name is intentionally not displayed — fastapi-users gives us no /me
# endpoint, and inferring tenant slug from the email is unreliable across
# tenant naming schemes. The email is enough for "who am I" feedback; the
# tenant scoping is enforced server-side via the JWT's tenant_id claim regardless.

import streamlit as st


@st.dialog("Sign out?")
def _confirm_signout() -> None:
    st.write("You'll need to sign in again to use the admin.")
    col_confirm, col_cancel = st.columns(2)
    if col_confirm.button("Sign out", type="primary", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    if col_cancel.button("Cancel", use_container_width=True):
        st.rerun()


def render_user_panel() -> None:
    """Renders the user badge + sign-out at the bottom of the sidebar.
    Call once per page (anywhere — Streamlit collects sidebar writes in order).
    """
    if "token" not in st.session_state:
        return

    email = st.session_state.get("email", "(unknown)")

    with st.sidebar:
        # Spacer pushes the panel toward the bottom of the sidebar.
        st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)
        st.divider()
        st.caption(f"🔐 Signed in as")
        st.markdown(f"**{email}**")
        if st.button("Sign out", key="sidebar_signout", use_container_width=True):
            _confirm_signout()
