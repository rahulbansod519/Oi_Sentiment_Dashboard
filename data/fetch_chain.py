import pandas as pd
import json
from playwright.sync_api import sync_playwright

INDEX_NAME = "NIFTY"

def fetch_nifty_option_chain():
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto("https://www.nseindia.com", timeout=60000)
            page.wait_for_timeout(3000)
            response = page.goto(
                f"https://www.nseindia.com/api/option-chain-indices?symbol={INDEX_NAME}",
                timeout=60000
            )

            if not response or response.status != 200:
                print(f"[❌ NSE Response Error] Status: {response.status if response else 'None'}")
                return None, None

            raw_text = response.text()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                print("❌ Response not JSON — likely blocked or HTML fallback.")
                return None, None

            if "records" not in data or "data" not in data["records"]:
                print("❌ Expected keys missing in NSE data")
                return None, None

            # Filter only for nearest expiry
            nearest_expiry = data["records"]["expiryDates"][0]
            filtered = [row for row in data["records"]["data"] if row.get("expiryDate") == nearest_expiry]

            underlying_price = data["records"]["underlyingValue"]
            atm = round(underlying_price / 50) * 50
            strikes = [atm - 100, atm - 50, atm, atm + 50, atm + 100]

            rows = []
            for row in filtered:
                strike = row.get("strikePrice")
                if strike in strikes:
                    ce = row.get("CE", {})
                    pe = row.get("PE", {})
                    rows.append({
                        "strike": strike,
                        "ce_oi": ce.get("openInterest", 0),
                        "ce_chg_oi": ce.get("changeinOpenInterest", 0),
                        "ce_iv": ce.get("impliedVolatility", 0),
                        "pe_oi": pe.get("openInterest", 0),
                        "pe_chg_oi": pe.get("changeinOpenInterest", 0),
                        "pe_iv": pe.get("impliedVolatility", 0),
                    })

            df = pd.DataFrame(rows)

            # Deduplicate: Keep only one row per strike (highest OI)
            df = df.sort_values(by=["strike", "ce_oi", "pe_oi"], ascending=[True, False, False])
            df = df.drop_duplicates(subset=["strike"], keep="first")
            df = df.sort_values("strike")

            return df, underlying_price

        except Exception as e:
            print(f"❌ Playwright Error: {e}")
            return None, None

        finally:
            browser.close()

if __name__ == "__main__":
    df, price = fetch_nifty_option_chain()
    if df is not None:
        print("Nifty Spot:", price)
        print(df)
