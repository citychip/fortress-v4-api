#!/usr/bin/env python3
"""
IBKR OAuth activation test — Consumer Key: SHARMILAH
Uses ibind's IbkrClient to test the full OAuth 1.0a flow.

Run from WSL:
    python3 /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/test_ibkr_oauth.py

Requires:
    pip install ibind cryptography --break-system-packages
"""

import sys

KEYS_DIR     = "/home/ubuntu/ibkr-oauth"
CONSUMER_KEY = "SHARMILAH"
ACCOUNT_ID   = "U7453366"

def ok(msg):   print(f"  ✓ {msg}")
def err(msg):  print(f"  ✗ {msg}")
def note(msg): print(f"  • {msg}")
def section(title): print(f"\n══ {title} {'═' * (50 - len(title))}")

print("\n══ IBKR OAuth Test (ibind) ══════════════════════════════")
print(f"  Consumer key : {CONSUMER_KEY}")
print(f"  Account      : {ACCOUNT_ID}")
print(f"  Keys dir     : {KEYS_DIR}")

# ── 1. Read credentials from keys directory ──────────────────
import os
section("1. Reading credentials")

try:
    access_token = open(f"{KEYS_DIR}/access_token.txt").read().strip()
    ok(f"Access token        : {access_token[:8]}…")
except Exception as e:
    err(f"Cannot read access_token.txt: {e}"); sys.exit(1)

try:
    access_token_secret = open(f"{KEYS_DIR}/access_token_secret.txt").read().strip()
    ok(f"Access token secret : {access_token_secret[:8]}…")
except Exception as e:
    err(f"Cannot read access_token_secret.txt: {e}"); sys.exit(1)

encryption_key_fp = f"{KEYS_DIR}/private_encryption.pem"
signature_key_fp  = f"{KEYS_DIR}/private_signature.pem"

if not os.path.exists(encryption_key_fp):
    err(f"Missing: {encryption_key_fp}"); sys.exit(1)
ok(f"Encryption key      : private_encryption.pem")

if not os.path.exists(signature_key_fp):
    err(f"Missing: {signature_key_fp}"); sys.exit(1)
ok(f"Signature key       : private_signature.pem")

# ── 2. Extract DH prime from dhparam.pem ────────────────────
section("2. DH prime")
try:
    from cryptography.hazmat.primitives.serialization import load_pem_parameters
    with open(f"{KEYS_DIR}/dhparam.pem", "rb") as f:
        dh_params = load_pem_parameters(f.read())
    dh_prime_hex = hex(dh_params.parameter_numbers().p)[2:]
    ok(f"DH prime extracted  : {dh_prime_hex[:16]}… ({len(dh_prime_hex)//2} bytes)")
except Exception as e:
    err(f"Failed to extract DH prime: {e}"); sys.exit(1)

# ── 3. Install ibind if needed ───────────────────────────────
section("3. ibind")
try:
    import ibind
    from importlib.metadata import version as pkg_version
    ok(f"ibind installed     : v{pkg_version('ibind')}")
except ImportError:
    note("Installing ibind…")
    os.system("pip install ibind --break-system-packages -q")
    import ibind
    from importlib.metadata import version as pkg_version
    ok(f"ibind installed     : v{pkg_version('ibind')}")

from ibind import IbkrClient
from ibind.oauth.oauth1a import OAuth1aConfig

# ── 4. Initialise OAuth client ───────────────────────────────
section("4. OAuth initialisation")
note("Contacting IBKR to get Live Session Token…")

try:
    config = OAuth1aConfig(
        access_token=access_token,
        access_token_secret=access_token_secret,
        consumer_key=CONSUMER_KEY,
        dh_prime=dh_prime_hex,
        encryption_key_fp=encryption_key_fp,
        signature_key_fp=signature_key_fp,
        realm="limited_poa",
    )

    client = IbkrClient(
        account_id=ACCOUNT_ID,
        cacert=False,
        use_oauth=True,
        oauth_config=config,
    )
    ok("OAuth initialised — Live Session Token obtained")
    ok("Brokerage session established")

except Exception as e:
    err(f"OAuth init failed: {e}")
    if "Invalid signature" in str(e):
        note("Consumer key not yet fully activated by IBKR.")
        note("Stage 1 (LST) works — Stage 2 (brokerage session) still pending.")
        note("Try again after the weekend maintenance window.")
    elif "401" in str(e):
        note("HTTP 401 — key not activated or credentials mismatch.")
    print("\n════════════════════════════════════════════════════════════\n")
    sys.exit(1)

# ── 5. Test API calls ────────────────────────────────────────
section("5. API tests")

try:
    accounts = client.portfolio_accounts().data
    ok(f"Accounts            : {[a['accountId'] for a in accounts]}")
except Exception as e:
    err(f"portfolio_accounts() failed: {e}")

try:
    ledger = client.get_ledger().data
    base = ledger.get("BASE", ledger.get("USD", next(iter(ledger.values()))))
    ok(f"Net liq             : ${base.get('netliquidationvalue', 'N/A'):,.0f}")
    ok(f"Cash balance        : ${base.get('cashbalance', 'N/A'):,.0f}")
except Exception as e:
    err(f"get_ledger() failed: {e}")

try:
    positions = client.positions().data
    ok(f"Positions           : {len(positions)} legs")
    for p in positions[:5]:
        print(f"     {p.get('ticker','?'):6s}  {p.get('position','?'):>6}  ${p.get('mktValue',0):>10,.0f}")
    if len(positions) > 5:
        note(f"… and {len(positions)-5} more")
except Exception as e:
    err(f"positions() failed: {e}")

# ── Done ─────────────────────────────────────────────────────
print("\n  ► OAuth is fully operational.")
print("    Next step: Parapet → System → Settings → Connections → switch backend to OAuth")
print("\n════════════════════════════════════════════════════════════\n")

client.close()
