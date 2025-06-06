# logic/signal_engine.py

def analyze_sentiment(df, spot_price, shift_text=None):
    result = {
        "signal": "AVOID",
        "reason": [],
        "suggested_strike": None,
        "instrument": None,
        "spot_price": spot_price
    }

    # --- PCR Calculation ---
    total_ce_oi = df['ce_oi'].sum()
    total_pe_oi = df['pe_oi'].sum()
    pcr = total_pe_oi / total_ce_oi if total_ce_oi != 0 else 0
    result["pcr"] = round(pcr, 2)

    # --- ATM Strike Logic ---
    atm_strike = df.iloc[(df['strike'] - spot_price).abs().argsort()[:1]]['strike'].values[0]
    result["suggested_strike"] = int(atm_strike)
    atm_row = df[df['strike'] == atm_strike].iloc[0]

    ce_oi_chg = atm_row['ce_chg_oi']
    pe_oi_chg = atm_row['pe_chg_oi']
    ce_iv = atm_row['ce_iv']
    pe_iv = atm_row['pe_iv']

    # --- Standard Signal Logic ---
    if pcr > 1.3 and pe_oi_chg > 0 and ce_oi_chg < 0:
        result["signal"] = "BUY CE"
        result["instrument"] = "CE"
        result["reason"].append("High PCR (>1.3)")
        result["reason"].append("Put writers active (PE OI↑)")
        result["reason"].append("Call writers unwinding (CE OI↓)")
        if pe_iv < ce_iv:
            result["reason"].append("PE IV dropping (momentum bullish)")

    elif pcr < 0.7 and ce_oi_chg > 0 and pe_oi_chg < 0:
        result["signal"] = "BUY PE"
        result["instrument"] = "PE"
        result["reason"].append("Low PCR (<0.7)")
        result["reason"].append("Call writers active (CE OI↑)")
        result["reason"].append("Put writers unwinding (PE OI↓)")
        if ce_iv < pe_iv:
            result["reason"].append("CE IV dropping (momentum bearish)")

    else:
        result["reason"].append("No clear directional bias or OI delta conflict")

    # --- Breakout Override: CE
    if result["signal"] == "AVOID":
        nearby = df[df["strike"].isin([atm_strike, atm_strike + 50])]
        pe_oi_jump = nearby["pe_chg_oi"].max() > 10000
        ce_oi_flat = nearby["ce_chg_oi"].max() < 2000
        spot_above_atm = spot_price > atm_strike
        if 0.7 <= pcr <= 1.1 and pe_oi_jump and ce_oi_flat and spot_above_atm:
            result["signal"] = "BUY CE"
            result["instrument"] = "CE"
            result["confidence"] = 3
            result["reason"] = [
                "📈 Spot breakout above ATM",
                "🟢 PE OI surged at ATM or nearby",
                "🔴 CE OI flat or unwinding",
                "🧠 PCR neutral but biased",
                "🔥 Breakout override triggered (CE)"
            ]

    # --- Breakout Override: PE
    if result["signal"] == "AVOID":
        nearby = df[df["strike"].isin([atm_strike, atm_strike - 50])]
        ce_oi_jump = nearby["ce_chg_oi"].max() > 10000
        pe_oi_flat = nearby["pe_chg_oi"].max() < 2000
        spot_below_atm = spot_price < atm_strike
        if 0.7 <= pcr <= 1.1 and ce_oi_jump and pe_oi_flat and spot_below_atm:
            result["signal"] = "BUY PE"
            result["instrument"] = "PE"
            result["confidence"] = 3
            result["reason"] = [
                "📉 Spot breakdown below ATM",
                "🔴 CE OI surged at ATM or nearby",
                "🟢 PE OI flat or unwinding",
                "🧠 PCR neutral but biased",
                "🔥 Breakout override triggered (PE)"
            ]

    # --- Shift-based Confidence Boost ---
    if shift_text:
        if "PE writers building at" in shift_text and result["signal"] == "BUY CE":
            result["confidence"] = min(result.get("confidence", 3) + 1, 5)
            result["reason"].append("OI shift confirms bullish bias (PE writers migrating up)")
        elif "CE writers building at" in shift_text and result["signal"] == "BUY PE":
            result["confidence"] = min(result.get("confidence", 3) + 1, 5)
            result["reason"].append("OI shift confirms bearish bias (CE writers migrating down)")
        elif result["signal"] == "AVOID" and ("PE writers building at" in shift_text or "CE writers building at" in shift_text):
            result["signal"] = "WEAK BUY CE" if "PE writers building at" in shift_text else "WEAK BUY PE"
            result["reason"].append("No strong PCR, but OI shift suggests directional bias")
            result["confidence"] = 2

    return result

def detect_oi_shift(prev, current):
    if prev is None:
        return "No OI history yet."

    movement = []
    for strike in current:
        prev_ce = prev.get(strike, {}).get("ce_oi", 0)
        prev_pe = prev.get(strike, {}).get("pe_oi", 0)
        now_ce = current[strike]["ce_oi"]
        now_pe = current[strike]["pe_oi"]

        if now_pe - prev_pe > 10000:
            movement.append(f"🟢 PE writers building at {strike}")
        if now_ce - prev_ce > 10000:
            movement.append(f"🔴 CE writers building at {strike}")

    if not movement:
        return "No major OI shifts detected."
    return "\n".join(movement)

def check_exit_conditions(df, signal_type, atm_strike):
    row = df[df["strike"] == atm_strike].iloc[0]

    ce_chg = row["ce_chg_oi"]
    pe_chg = row["pe_chg_oi"]
    ce_iv = row["ce_iv"]
    pe_iv = row["pe_iv"]

    reasons = []

    if signal_type == "BUY CE":
        if ce_chg > 0:
            reasons.append("🔁 CE writers returning at strike")
        if pe_chg < 0:
            reasons.append("⚠️ PE writers backing out (support weakening)")
        if pe_iv > ce_iv:
            reasons.append("🧨 IV flipping toward PE (bearish instability)")

    elif signal_type == "BUY PE":
        if pe_chg > 0:
            reasons.append("🔁 PE writers returning at strike")
        if ce_chg < 0:
            reasons.append("⚠️ CE writers backing out (resistance weakening)")
        if ce_iv > pe_iv:
            reasons.append("🧨 IV flipping toward CE (bullish instability)")

    if reasons:
        return {
            "exit_flag": True,
            "reasons": reasons
        }
    return {
        "exit_flag": False,
        "reasons": []
    }


