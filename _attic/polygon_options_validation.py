import os
import requests
import json

api_key = os.getenv("POLYGON_API_KEY", "").strip()

if not api_key:
    raise SystemExit("[AUTH] POLYGON_API_KEY is missing")

headers = {"Authorization": f"Bearer {api_key}"}

url = "https://api.polygon.io/v3/snapshot/options/SPY"
params = {"limit": 50}

print("=" * 70)
print("AVSHUNTER POLYGON OPTIONS VALIDATION")
print("=" * 70)

r = requests.get(url, headers=headers, params=params, timeout=30)

print("HTTP Status:", r.status_code)

if r.status_code != 200:
    print(r.text[:1000])
    raise SystemExit("[FAIL] Snapshot request failed")

data = r.json()
results = data.get("results", [])

print("Contracts returned:", len(results))

if not results:
    raise SystemExit("[FAIL] No option contracts returned")

greeks_count = 0
iv_count = 0
quote_count = 0
underlying_count = 0

for c in results:
    greeks = c.get("greeks") or {}
    details_greeks = (c.get("details") or {}).get("greeks") or {}

    has_greeks = any(
        x is not None
        for x in [
            greeks.get("delta"),
            greeks.get("gamma"),
            greeks.get("theta"),
            greeks.get("vega"),
            details_greeks.get("delta"),
            details_greeks.get("gamma"),
            details_greeks.get("theta"),
            details_greeks.get("vega"),
        ]
    )

    has_iv = (
        c.get("implied_volatility") is not None
        or (c.get("details") or {}).get("implied_volatility") is not None
    )

    last_quote = c.get("last_quote") or {}
    has_quote = last_quote.get("bid") is not None or last_quote.get("ask") is not None

    underlying_asset = c.get("underlying_asset") or {}
    has_underlying = underlying_asset.get("price") is not None

    if has_greeks:
        greeks_count += 1
    if has_iv:
        iv_count += 1
    if has_quote:
        quote_count += 1
    if has_underlying:
        underlying_count += 1

print()
print("=== FIELD COVERAGE ===")
print(f"Greeks coverage:           {greeks_count} / {len(results)}")
print(f"Implied volatility cover:  {iv_count} / {len(results)}")
print(f"Bid/Ask quote coverage:    {quote_count} / {len(results)}")
print(f"Underlying price coverage: {underlying_count} / {len(results)}")

sample = None
for c in results:
    if c.get("greeks") or c.get("implied_volatility") or c.get("last_quote"):
        sample = c
        break

if sample is None:
    sample = results[0]

print()
print("=== SAMPLE CONTRACT ===")
print("Ticker:", sample.get("ticker"))
print("Contract type:", (sample.get("details") or {}).get("contract_type"))
print("Expiration:", (sample.get("details") or {}).get("expiration_date"))
print("Strike:", (sample.get("details") or {}).get("strike_price"))
print("IV:", sample.get("implied_volatility"))
print("Greeks:", sample.get("greeks"))
print("Last quote:", sample.get("last_quote"))
print("Underlying asset:", sample.get("underlying_asset"))

print()
print("=== AVSHUNTER VERDICT ===")

if greeks_count > 0 and iv_count > 0 and quote_count > 0:
    print("Mode: FULL_ANALYTICS_DELAYED_EXECUTION")
    print("Meaning: Greeks/IV appear available. Treat quotes as delayed unless broker confirms live bid/ask.")
elif greeks_count > 0 and iv_count > 0:
    print("Mode: ANALYTICS_ONLY_NO_QUOTES")
    print("Meaning: Greeks/IV available, but execution quotes must come from broker.")
elif results:
    print("Mode: STRUCTURE_ONLY_OPTIONS_CONTEXT")
    print("Meaning: Options chain exists, but Greeks/IV missing from sampled contracts.")
else:
    print("Mode: BLOCK_OPTIONS_INTELLIGENCE")

print("=" * 70)
