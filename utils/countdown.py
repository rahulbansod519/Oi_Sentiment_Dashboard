# utils/countdown.py

import datetime
import time
import threading

def get_next_5min_mark(now=None):
    if now is None:
        now = datetime.datetime.now()

    # Round up to next 5-minute slot
    next_minute = (now.minute // 5 + 1) * 5
    if next_minute >= 60:
        next_time = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    else:
        next_time = now.replace(minute=next_minute, second=0, microsecond=0)

    return next_time


def start_countdown(target_time, slot):
    def countdown():
        while True:
            now = datetime.datetime.now()
            delta = target_time - now
            seconds_left = int(delta.total_seconds())
            if seconds_left <= 0:
                import streamlit as st
                st.experimental_rerun()
                break
            mins, secs = divmod(seconds_left, 60)
            try:
                slot.info(f"🕒 Auto-refresh in: `{mins:02d}:{secs:02d}`")
            except:
                break
            time.sleep(1)
    threading.Thread(target=countdown, daemon=True).start()
