"""
Quick diagnostic — tests chain fetch and contract selection for AMD and AMZN.
Run in the AVSHUNTER venv.
"""
import sys, os

# Add the scripts dir to path so we can import the module
sys.path.insert(0, r'C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\scripts')

# We need to replicate just the chain fetch + IV + contract logic inline
# by importing the actual script functions

# The script uses sys.argv for args — mock them so import doesn't crash
sys.argv = ['avshunter_options_intelligence.py',
            'dummy.csv', 'dummy.csv', '20260220_001145', 'C:\\Temp', '1']

# Patch CSV reads so they don't fail on import
import unittest.mock as mock
import pandas as pd

dummy_df = pd.DataFrame({'ticker':['AMD'],'tier':[0]})

with mock.patch('pandas.read_csv', return_value=dummy_df):
    try:
        import avshunter_options_intelligence as opts
        print("Import OK")
    except SystemExit:
        pass
    except Exception as e:
        print(f"Import error: {e}")
        sys.exit(1)

# Now test chain fetch directly
print("\n=== TESTING fetch_chain('AMD') ===")
try:
    chain = opts.fetch_chain('AMD')
    print(f"Chain rows: {len(chain)}")
    if not chain.empty:
        print(f"Columns: {list(chain.columns)}")
        print(f"Sample:\n{chain.head(3).to_string()}")
    else:
        print("CHAIN IS EMPTY after quality gates")
except Exception as e:
    print(f"Chain fetch error: {e}")
    import traceback; traceback.print_exc()

# Test AMZN (liquid, should definitely have chain)
print("\n=== TESTING fetch_chain('AMZN') ===")
try:
    chain2 = opts.fetch_chain('AMZN')
    print(f"Chain rows: {len(chain2)}")
    if not chain2.empty:
        print(f"Sample strikes: {sorted(chain2['strike'].unique())[:5]}")
        print(f"Implied vol sample: {chain2['implied_vol'].dropna().head(3).tolist()}")
        print(f"OI sample: {chain2['open_interest'].head(3).tolist()}")
    else:
        print("CHAIN IS EMPTY after quality gates")
        # Fetch raw to see what we get before gates
        print("\nFetching raw (no gate)...")
        base = f"https://api.polygon.io/v3/snapshot/options/AMZN"
        params = {'limit':5, 'expiration_date.gte': __import__('datetime').date.today().isoformat()}
        opts._add_auth(params)
        r = opts.SESSION.get(base, params=params, headers=opts.HEADERS, timeout=15)
        print(f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Keys: {list(data.keys())}")
            results = data.get('results', [])
            print(f"Raw results count: {len(results)}")
            if results:
                print(f"First result keys: {list(results[0].keys())}")
                print(f"First result: {results[0]}")
        else:
            print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()
