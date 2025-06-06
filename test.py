# test.py

from data.fetch_chain import fetch_nifty_option_chain
from logic.signal_engine import analyze_sentiment

df, spot = fetch_nifty_option_chain()
signal = analyze_sentiment(df, spot)

print("🔎 Signal:", signal["signal"])
print("💥 Strike:", signal["suggested_strike"])
print("📊 PCR:", signal["pcr"])
print("📌 Reasons:")
for r in signal["reason"]:
    print(" -", r)
