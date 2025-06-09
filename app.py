import streamlit as st
import pandas as pd
import datetime
import time
from data.fetch_chain import fetch_nifty_option_chain
from logic.signal_engine import analyze_sentiment, detect_oi_shift, check_exit_conditions
import streamlit.components.v1 as components
import uuid
import os

# --- Helper: Next Interval ---
def get_next_interval(now, interval_minutes=5):
    """Return the next datetime rounded up to the next interval (e.g., 5 min)."""
    discard = datetime.timedelta(
        minutes=now.minute % interval_minutes,
        seconds=now.second,
        microseconds=now.microsecond
    )
    next_time = now - discard + datetime.timedelta(minutes=interval_minutes)
    return next_time.replace(second=0, microsecond=0)

# --- Constants ---
REFRESH_INTERVAL_MINUTES = 5

# --- Time Setup ---
now = datetime.datetime.now()

# --- Initialize next_refresh_time ONCE ---
if "next_refresh_time" not in st.session_state:
    st.session_state["next_refresh_time"] = get_next_interval(now, REFRESH_INTERVAL_MINUTES)

# --- Time Check (EXACT INTERVALS) ---
if now >= st.session_state["next_refresh_time"]:
    st.session_state["next_refresh_time"] = get_next_interval(now, REFRESH_INTERVAL_MINUTES)
    st.rerun()

# --- Improved Countdown with Real-time Sync ---
next_refresh = st.session_state["next_refresh_time"]

components.html(f"""
    <div style="padding:0.5em 1em; background:#f0f2f6; border-radius:0.5em; font-size:1.2em; font-weight:500; display:inline-block;">
        🕒 Auto-refresh in: <span id="countdown">--:--</span>
    </div>
    <script>
        const targetTime = new Date("{next_refresh.isoformat()}").getTime();
        const el = document.getElementById("countdown");
        let refreshTriggered = false;
        
        function updateCountdown() {{
            const now = new Date().getTime();
            const timeLeft = targetTime - now;
            
            if (timeLeft <= 0) {{
                if (!refreshTriggered) {{
                    refreshTriggered = true;
                    el.innerText = "Refreshing...";
                    // Let Streamlit handle the refresh naturally
                    setTimeout(() => {{
                        if (window.parent && window.parent.location) {{
                            window.parent.location.reload();
                        }} else {{
                            window.location.reload();
                        }}
                    }}, 500);
                }}
                return;
            }}
            
            const minutes = Math.floor(timeLeft / 60000);
            const seconds = Math.floor((timeLeft % 60000) / 1000);
            el.innerText = ('0' + minutes).slice(-2) + ":" + ('0' + seconds).slice(-2);
            
            // Use requestAnimationFrame for better performance and accuracy
            if (document.hidden) {{
                // When tab is hidden, use setTimeout with longer interval
                setTimeout(updateCountdown, 1000);
            }} else {{
                // When tab is visible, use requestAnimationFrame for smoother updates
                setTimeout(updateCountdown, 100);
            }}
        }}
        
        // Handle visibility changes
        document.addEventListener('visibilitychange', function() {{
            if (!document.hidden) {{
                // Tab became visible - immediately sync with real time
                updateCountdown();
            }}
        }});
        
        // Start the countdown
        updateCountdown();
    </script>
""", height=50)

st.write("✅ App running at:", now.strftime("%H:%M:%S"))

# --- Session State Setup ---
if "trade_log" not in st.session_state:
    st.session_state["trade_log"] = []
if "last_oi" not in st.session_state:
    st.session_state["last_oi"] = None

# --- Title ---
st.title("📊 Nifty Intraday Options Dashboard — OI-Delta Strategy")

# --- Fetch Option Chain with Retry ---
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2

warning_placeholder = st.empty()  # Create a placeholder for warnings

with st.spinner("🔄 Fetching live option chain..."):
    for attempt in range(1, MAX_RETRIES + 1):
        df, spot_price = fetch_nifty_option_chain()
        if df is not None and spot_price is not None:
            warning_placeholder.empty()  # Clear warning if fetch is successful
            break
        if attempt < MAX_RETRIES:
            warning_placeholder.warning(f"Fetch attempt {attempt} failed. Retrying in {RETRY_DELAY_SEC} seconds...")
            time.sleep(RETRY_DELAY_SEC)

if df is None or spot_price is None:
    st.error("❌ Failed to fetch Option Chain data after multiple attempts. Please try again.")
    st.stop()

# --- OI Processing ---
current_oi_map = {
    row["strike"]: {"ce_oi": row["ce_oi"], "pe_oi": row["pe_oi"]}
    for _, row in df.iterrows()
}
shift_info = detect_oi_shift(st.session_state["last_oi"], current_oi_map)
signal = analyze_sentiment(df, spot_price, shift_info)
exit_info = check_exit_conditions(df, signal["signal"], signal["suggested_strike"])

# --- Top Metrics ---
st.markdown("### 🔎 Signal Snapshot")
col1, col2, col3, col4 = st.columns(4)
col1.metric("📈 Nifty Spot", f"{spot_price:.2f}")
col2.metric("📊 PCR", signal["pcr"])
col3.metric("🎯 Signal", signal["signal"], delta=f"Strike {signal['suggested_strike']}" if signal["suggested_strike"] else "—")
col4.metric("🧠 Confidence", f"{signal.get('confidence', 0)}/5")

# --- Signal Explanation ---
with st.expander("💬 Strategy Explainer", expanded=True):
    explain = []
    if signal["pcr"] > 1.3:
        explain.append("📈 PCR is high → Put writers dominating → Bullish bias")
    elif signal["pcr"] < 0.7:
        explain.append("📉 PCR is low → Call writers aggressive → Bearish bias")
    else:
        explain.append("⚖️ PCR is neutral → No strong directional edge")

    if "PE OI↑" in " ".join(signal["reason"]):
        explain.append("🟢 PE OI increased → Support forming")
    if "CE OI↑" in " ".join(signal["reason"]):
        explain.append("🔴 CE OI increased → Resistance forming")
    if "CE OI↓" in " ".join(signal["reason"]):
        explain.append("✅ CE unwinding → Resistance weakening")
    if "PE OI↓" in " ".join(signal["reason"]):
        explain.append("✅ PE unwinding → Support weakening")
    if any("IV dropping" in r for r in signal["reason"]):
        explain.append("📉 IV dropping → Trend confirmation from volatility")

    if signal["signal"] == "BUY CE":
        explain.append("🚀 Bullish CE Entry Opportunity")
    elif signal["signal"] == "BUY PE":
        explain.append("📉 Bearish PE Entry Opportunity")
    else:
        explain.append("⛔ No actionable setup — Avoid zone")

    for line in explain:
        st.write(line)

# --- Exit Signal ---
st.subheader("🚪 Exit Signal Monitor")
if exit_info["exit_flag"]:
    st.error("⚠️ Exit triggers detected:")
    for r in exit_info["reasons"]:
        st.write(f"- {r}")
else:
    st.success("✅ No exit triggers — trend intact.")

# --- Signal Breakdown ---
with st.expander("📌 Signal Breakdown"):
    for r in signal["reason"]:
        st.write(f"- {r}")

# --- OI Shift Tracker ---
st.subheader("📡 OI Shift Tracker")
st.code(shift_info)

# --- Trade Log ---
st.subheader("📒 Signal History")
log_entry = {
    "id": str(uuid.uuid4()),  # Unique ID for each entry
    "time": pd.Timestamp.now().strftime("%H:%M:%S.%f"),  # Include microseconds for uniqueness
    "signal": signal["signal"],
    "strike": signal["suggested_strike"],
    "pcr": signal["pcr"],
    "reasons": "; ".join(signal["reason"]),
    "spot": round(spot_price, 2)
}

# Always add to log, even if duplicate
st.session_state["trade_log"].insert(0, log_entry)

# --- Save to CSV ---
today_str = datetime.datetime.now().strftime("%d-%m-%Y")
csv_filename = f"{today_str}.csv"

# If file exists, append only the new entry; else, write all
if os.path.exists(csv_filename):
    pd.DataFrame([log_entry]).to_csv(csv_filename, mode='a', header=False, index=False)
else:
    pd.DataFrame(st.session_state["trade_log"]).to_csv(csv_filename, index=False)

log_df = pd.DataFrame(st.session_state["trade_log"])
if not log_df.empty:
    st.dataframe(log_df[["time", "signal", "strike", "pcr", "spot"]], use_container_width=True)
else:
    st.info("No signals logged yet.")

# --- Chain Data ---
st.subheader("🔬 ATM ±2 Strike Data")
st.dataframe(df.set_index("strike"), use_container_width=True)

# --- Manual Refresh ---
st.divider()
if st.button("🔁 Refresh"):
    now = datetime.datetime.now()
    st.session_state["next_refresh_time"] = get_next_interval(now, REFRESH_INTERVAL_MINUTES)
    st.rerun()

# --- Save OI Snapshot ---
st.session_state["last_oi"] = current_oi_map