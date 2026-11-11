"""One shared compute cooldown per Streamlit session."""

from time import monotonic

import streamlit as st

from src.config import COOLDOWN_SECONDS


def begin_compute():
    now = monotonic()
    last = st.session_state.get("last_compute_started")
    if last is not None and now - last < COOLDOWN_SECONDS:
        st.warning(f"Allow {COOLDOWN_SECONDS} seconds between compute requests.")
        return False
    st.session_state.last_compute_started = now
    return True
