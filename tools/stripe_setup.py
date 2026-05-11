#!/usr/bin/env python3
r"""Automate Stripe Payment Link setup and wire it into the landing pages.

What this script does (after you've created your Stripe account manually):
  1. Create or reuse the "Plugfile — Founders early access" Product.
  2. Create or reuse the $1 USD one-time Price.
  3. Create or reuse the Payment Link with the right config:
       - customer email collected at checkout
       - confirmation message tells operator what comes next
       - Plugfile-specific metadata so we can find/regenerate it later
  4. Patch landing/index.html and landing/for-engineers.html to replace
     `REPLACE_WITH_YOUR_PAYMENT_LINK` with the real Payment Link URL.
  5. Optionally invoke tools/deploy_landing.py to push changes live.

Idempotent: re-running it finds existing objects by lookup_key / metadata
and reuses them. Won't double-charge or duplicate products.

What this script can NOT do (human required, one-time):
  - Stripe account signup (https://dashboard.stripe.com/register)
  - Identity verification, bank account linking
  - Activating live-mode payments

ONE-TIME PREREQUISITES (you do these in your browser):
  1. Sign up at https://dashboard.stripe.com/register. Use your Plugfile
     business name; pick "Sole proprietorship" if you haven't formed an LLC.
  2. Complete the business profile (address, industry, bank account).
     For testing-only, you can skip bank account — test mode works.
  3. Dashboard -> Developers -> API keys -> reveal Secret key. Looks like
     `sk_test_...` (test mode) or `sk_live_...` (live mode).
  4. Set the environment variable:
        $env:STRIPE_API_KEY = "sk_test_..."          # PowerShell
        export STRIPE_API_KEY=sk_test_...            # bash

USAGE:
  python tools\stripe_setup.py                  # full setup + patch HTML
  python tools\stripe_setup.py --skip-deploy    # patch HTML, don't redeploy
  python tools\stripe_setup.py --dry-run        # preview only, change nothing
  python tools\stripe_setup.py --print-link     # just print existing link

After this, the landing page Reserve buttons go to your real Payment Link.
Stripe handles the checkout, captures the customer email, sends them the
confirmation, and deposits $1 into your bank account ~2 business days later.
Stdlib only. No `pip install stripe` needed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.stripe.com/v1"

# Plugfile-specific identifiers used for idempotent lookup
PRODUCT_NAME = "Plugfile — Founders early access"
PRODUCT_LOOKUP_KEY = "plugfile_founders_deposit_product"
PRICE_LOOKUP_KEY = "plugfile_founders_deposit_price"
PAYMENT_LINK_TAG = "plugfile_founders_deposit_link"

CONFIRMATION_MESSAGE = (
    "Reserved. We'll email you when Plugfile opens to your district. "
    "Charged to your card as **PLUGFILE FILING**. "
    "Refundable any time before launch — email refund@plugfile.com."
)

PRODUCT_DESCRIPTION = (
    "$1 refundable deposit reserves early-access pricing for Plugfile, "
    "Texas RRC Form W-3 plugging-record automation. Deposit is fully "
    "refundable any time before launch (estimated Q3 2026). "
    "See https://plugfile.com."
)


# ---- HTTP / form encoding ---------------------------------------------------

class StripeError(RuntimeError):
    pass


def _encode_form(data: dict) -> bytes:
    """Stripe takes nested objects as bracketed form keys.
    {"line_items": [{"price": "p", "quantity": 1}]}
    becomes
    line_items[0][price]=p&line_items[0][quantity]=1
    """
    pairs: list[tuple[str, str]] = []

    def walk(prefix: str, value):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}[{k}]" if prefix else k, v)
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                walk(f"{prefix}[{i}]", item)
        elif value is None:
            return
        elif isinstance(value, bool):
            pairs.append((prefix, "true" if value else "false"))
        else:
            pairs.append((prefix, str(value)))

    walk("", data)
    return urllib.parse.urlencode(pairs).encode("utf-8")


def stripe(method: str, path: str, key: str, data: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {key}",
        "Stripe-Version": "2024-06-20",
    }
    body = None
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = _encode_form(data)
    req = urllib.request.Request(API + path, data=body, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": {"message": str(e)}}
        msg = err.get("error", {}).get("message", json.dumps(err))
        raise StripeError(f"{method} {path} -> HTTP {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise StripeError(f"{method} {path}: {e}") from None


# ---- Stripe object helpers --------------------------------------------------

def get_account(key: str) -> dict:
    return stripe("GET", "/account", key)


def find_product(key: str) -> dict | None:
    res = stripe("GET", f"/products/search?query=metadata[%27plugfile_id%27]:%27{PRODUCT_LOOKUP_KEY}%27&limit=1", key)
    items = res.get("data", [])
    return items[0] if items else None


def create_product(key: str, *, dry_run: bool) -> dict:
    if dry_run:
        return {"id": "<dry-run>", "name": PRODUCT_NAME, "_dry_run": True}
    return stripe("POST", "/products", key, data={
        "name": PRODUCT_NAME,
        "description": PRODUCT_DESCRIPTION,
        "metadata": {"plugfile_id": PRODUCT_LOOKUP_KEY},
    })


def find_price(key: str, product_id: str) -> dict | None:
    res = stripe(
        "GET",
        f"/prices?lookup_keys[]={PRICE_LOOKUP_KEY}&active=true&limit=1",
        key,
    )
    items = res.get("data", [])
    return items[0] if items else None


def create_price(key: str, product_id: str, *, dry_run: bool) -> dict:
    if dry_run:
        return {"id": "<dry-run>", "_dry_run": True}
    return stripe("POST", "/prices", key, data={
        "product": product_id,
        "currency": "usd",
        "unit_amount": 100,           # $1.00 in cents
        "lookup_key": PRICE_LOOKUP_KEY,
        "metadata": {"plugfile_id": PRICE_LOOKUP_KEY},
    })


def find_payment_link(key: str) -> dict | None:
    # Payment Links don't support search; list active and filter by metadata.
    res = stripe("GET", "/payment_links?active=true&limit=100", key)
    for pl in res.get("data", []):
        if pl.get("metadata", {}).get("plugfile_id") == PAYMENT_LINK_TAG:
            return pl
    return None


def create_payment_link(key: str, price_id: str, *, dry_run: bool) -> dict:
    if dry_run:
        return {"id": "<dry-run>", "url": "https://buy.stripe.com/<dry-run>",
                "_dry_run": True}
    return stripe("POST", "/payment_links", key, data={
        "line_items": [{"price": price_id, "quantity": 1}],
        # Email + name collection happens automatically at checkout. We
        # explicitly DO NOT collect billing address (less friction).
        "billing_address_collection": "auto",
        "after_completion": {
            "type": "hosted_confirmation",
            "hosted_confirmation": {
                "custom_message": CONFIRMATION_MESSAGE,
            },
        },
        "allow_promotion_codes": False,
        "submit_type": "book",  # button reads "Reserve" instead of "Pay"
        "metadata": {"plugfile_id": PAYMENT_LINK_TAG},
    })


# ---- HTML patching ----------------------------------------------------------

PLACEHOLDER = "https://buy.stripe.com/REPLACE_WITH_YOUR_PAYMENT_LINK"


def patch_landing(landing_dir: str, real_url: str, *, dry_run: bool) -> int:
    """Replace the Payment Link placeholder in every .html file in landing/.
    Returns count of files modified."""
    modified = 0
    for fname in os.listdir(landing_dir):
        if not fname.endswith(".html"):
            continue
        full = os.path.join(landing_dir, fname)
        content = open(full, "r", encoding="utf-8").read()
        if PLACEHOLDER not in content and real_url in content:
            print(f"  {fname}: already up to date")
            continue
        if PLACEHOLDER not in content:
            print(f"  {fname}: no placeholder found, skipping")
            continue
        new_content = content.replace(PLACEHOLDER, real_url)
        if dry_run:
            print(f"  {fname}: would replace placeholder with {real_url}")
        else:
            open(full, "w", encoding="utf-8").write(new_content)
            print(f"  {fname}: patched")
        modified += 1
    return modified


# ---- main -------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--landing-dir", default="landing")
    p.add_argument("--skip-deploy", action="store_true",
                   help="Patch HTML but don't run tools/deploy_landing.py.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview API calls + HTML edits, change nothing.")
    p.add_argument("--print-link", action="store_true",
                   help="Just print the existing Payment Link URL and exit.")
    args = p.parse_args()

    key = os.environ.get("STRIPE_API_KEY")
    if not key:
        sys.stderr.write(
            "ERROR: STRIPE_API_KEY not set.\n\n"
            "1. Sign up at https://dashboard.stripe.com/register\n"
            "2. Get your Secret key at Developers -> API keys\n"
            "3. Set it:\n"
            "     PowerShell:  $env:STRIPE_API_KEY = \"sk_test_...\"\n"
            "     bash:        export STRIPE_API_KEY=sk_test_...\n"
        )
        return 2

    mode = "TEST" if key.startswith("sk_test_") else "LIVE" if key.startswith("sk_live_") else "?"
    print(f"Mode: {mode}  ({'DRY-RUN' if args.dry_run else 'APPLY'})")
    print()

    # Verify the key works and print account info
    try:
        acct = get_account(key)
    except StripeError as e:
        sys.stderr.write(f"Stripe API key check failed: {e}\n")
        return 1
    print(f"Account: {acct.get('id')}  {acct.get('business_profile', {}).get('name', '(business name not set)')}")
    print(f"Email:   {acct.get('email', '(not set)')}")
    print(f"Country: {acct.get('country')}")
    print()

    if args.print_link:
        existing = find_payment_link(key)
        if existing:
            print(f"Payment Link URL: {existing['url']}")
            return 0
        print("No Plugfile Payment Link found in this account.")
        return 1

    # 1. Product
    print("[1] Product")
    product = find_product(key)
    if product:
        print(f"  exists: {product['id']}  ({product['name']})")
    else:
        print("  not found, creating...")
        product = create_product(key, dry_run=args.dry_run)
        print(f"  created: {product['id']}")

    # 2. Price
    print("\n[2] Price")
    price = find_price(key, product["id"])
    if price:
        print(f"  exists: {price['id']}  ${price['unit_amount']/100:.2f} {price['currency'].upper()}")
    else:
        print("  not found, creating $1.00 USD one-time...")
        price = create_price(key, product["id"], dry_run=args.dry_run)
        print(f"  created: {price['id']}")

    # 3. Payment Link
    print("\n[3] Payment Link")
    link = find_payment_link(key)
    if link:
        print(f"  exists: {link['id']}")
        print(f"  url:    {link['url']}")
    else:
        print("  not found, creating...")
        link = create_payment_link(key, price["id"], dry_run=args.dry_run)
        print(f"  created: {link['id']}")
        print(f"  url:     {link['url']}")

    real_url = link["url"]
    if args.dry_run:
        print(f"\nWould patch HTML files in {args.landing_dir}/ with {real_url}")
        return 0

    # 4. Patch HTML
    print(f"\n[4] Patching landing pages")
    landing_dir = os.path.abspath(args.landing_dir)
    if not os.path.isdir(landing_dir):
        sys.stderr.write(f"ERROR: {landing_dir} not found\n")
        return 1
    n = patch_landing(landing_dir, real_url, dry_run=False)
    print(f"  {n} file(s) modified")

    # 5. Optionally deploy
    if args.skip_deploy:
        print("\n[5] Skipping deploy (--skip-deploy). Run when ready:")
        print(f"    python tools/deploy_landing.py")
    else:
        print("\n[5] Deploying via tools/deploy_landing.py...")
        deploy = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "deploy_landing.py")
        if not os.path.exists(deploy):
            print(f"  WARN: {deploy} not found, skipping")
        else:
            subprocess.run([sys.executable, deploy], check=False)

    print("\n" + "=" * 70)
    print(f"DONE. Reserve buttons now point to: {real_url}")
    print("Test it: open https://plugfile.com, click Reserve, confirm checkout.")
    if mode == "TEST":
        print("\nTEST MODE: use card 4242 4242 4242 4242 with any future expiry + CVC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
