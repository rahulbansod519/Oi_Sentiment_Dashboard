import streamlit as st
import pandas as pd
import datetime
import time
from data.fetch_chain import fetch_nifty_option_chain
from logic.signal_engine import analyze_sentiment, detect_oi_shift, check_exit_conditions
import streamlit.components.v1 as components

# --- Page Setup ---
st.set_page_config(page_title="Nifty Options Dashboard", layout="wide")

# --- Constants ---
REFRESH_INTERVAL_MINUTES = 5

# --- Time Setup ---
now = datetime.datetime.now()

# --- Initialize next_refresh_time ONCE ---
if "next_refresh_time" not in st.session_state:
    minutes_to_add = REFRESH_INTERVAL_MINUTES - (now.minute % REFRESH_INTERVAL_MINUTES)
    st.session_state["next_refresh_time"] = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=minutes_to_add)

# --- Time Check (FIXED VERSION) ---
if now >= st.session_state["next_refresh_time"]:
    # Calculate next refresh time properly to avoid infinite loops
    while st.session_state["next_refresh_time"] <= now:
        st.session_state["next_refresh_time"] += datetime.timedelta(minutes=REFRESH_INTERVAL_MINUTES)
    st.rerun()

# --- Countdown ---
seconds_left = int((st.session_state["next_refresh_time"] - now).total_seconds())

# Ensure we don't have negative countdown
if seconds_left < 0:
    seconds_left = 0

components.html(f"""
    <div style="padding:0.5em 1em; background:#f0f2f6; border-radius:0.5em; font-size:1.2em; font-weight:500; display:inline-block;">
        🕒 Auto-refresh in: <span id="countdown">{seconds_left//60:02d}:{seconds_left%60:02d}</span>
    </div>

    <script>
        var seconds = {seconds_left};
        const el = document.getElementById("countdown");

        function tick() {{
            if (seconds > 0) {{
                seconds--;
                const m = Math.floor(seconds / 60);
                const s = seconds % 60;
                el.innerText = ('0' + m).slice(-2) + ":" + ('0' + s).slice(-2);
                setTimeout(tick, 1000);
            }} else {{
                el.innerText = "Refreshing...";
                // Optional: Force page refresh when countdown reaches 0
                setTimeout(() => window.parent.location.reload(), 1000);
            }}
        }}
        tick();
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

# --- Fetch Option Chain ---
with st.spinner("🔄 Fetching live option chain..."):
    df, spot_price = fetch_nifty_option_chain()

if df is None or spot_price is None:
    st.error("❌ Failed to fetch Option Chain data. Please try again.")
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
    "time": pd.Timestamp.now().strftime("%H:%M:%S"),
    "signal": signal["signal"],
    "strike": signal["suggested_strike"],
    "pcr": signal["pcr"],
    "reasons": "; ".join(signal["reason"]),
    "spot": round(spot_price, 2)
}
st.session_state["trade_log"].insert(0, log_entry)

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
    st.session_state["next_refresh_time"] = datetime.datetime.now()  # force immediate refresh
    st.rerun()

# --- Save OI Snapshot ---
st.session_state["last_oi"] = current_oi_map