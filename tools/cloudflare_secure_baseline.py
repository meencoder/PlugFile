#!/usr/bin/env python3
"""Apply a security baseline to every zone in your Cloudflare account.

Idempotent. Re-running is safe; nothing changes if everything is already at
the desired state. Defaults to --dry-run; you must pass --apply for anything
to actually change.

Settings applied per zone:
  - SSL/TLS mode           = strict (full SSL, validate origin cert)
  - Always Use HTTPS       = on
  - Automatic HTTPS Rewrites = on
  - Min TLS version        = 1.2
  - TLS 1.3                = on
  - Browser Integrity Check = on
  - Email Address Obfuscation = on
  - HSTS                   = enabled, 6 months, includeSubDomains
  - DNSSEC                 = enabled

DNS records added if missing:
  - TXT @       "v=spf1 -all"
  - TXT _dmarc  "v=DMARC1; p=reject; rua=mailto:<REPORT_EMAIL>"

Usage:
  export CLOUDFLARE_API_TOKEN=...
  python tools/cloudflare_secure_baseline.py --dry-run         # preview
  python tools/cloudflare_secure_baseline.py --apply           # apply to all zones
  python tools/cloudflare_secure_baseline.py --apply --zone kaproq.com
  python tools/cloudflare_secure_baseline.py --apply --skip-dns
  python tools/cloudflare_secure_baseline.py --apply --report-email you@example.com

API token scopes required (create at dash.cloudflare.com -> My Profile ->
API Tokens -> Create Token -> Custom token):
  Zone     -> Zone        -> Read
  Zone     -> Zone Settings -> Edit
  Zone     -> SSL and Certificates -> Edit
  Zone     -> DNS         -> Edit

Stdlib only. No external Python dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.cloudflare.com/client/v4"


# ---- desired state ---------------------------------------------------------

ZONE_SETTINGS = {
    "ssl": "strict",
    "always_use_https": "on",
    "automatic_https_rewrites": "on",
    "min_tls_version": "1.2",
    "tls_1_3": "on",
    "browser_check": "on",
    "email_obfuscation": "on",
}

HSTS_VALUE = {
    "strict_transport_security": {
        "enabled": True,
        "max_age": 15552000,        # 180 days; ratchet to 31536000 (1y) later
        "include_subdomains": True,
        "preload": False,
        "nosniff": True,
    },
}


# ---- HTTP helpers ----------------------------------------------------------

class CFError(RuntimeError):
    pass


def _req(method: str, path: str, token: str, body=None) -> dict:
    url = API + path
    data = None
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"errors": [{"message": str(e)}]}
        raise CFError(f"{method} {path} -> HTTP {e.code}: "
                      f"{json.dumps(err.get('errors', err))}") from None
    except urllib.error.URLError as e:
        raise CFError(f"{method} {path}: {e}") from None


def _ok(resp: dict) -> dict:
    if not resp.get("success", False):
        raise CFError(f"API error: {json.dumps(resp.get('errors', resp))}")
    return resp


def list_zones(token: str) -> list[dict]:
    zones: list[dict] = []
    page = 1
    while True:
        resp = _ok(_req("GET", f"/zones?per_page=50&page={page}", token))
        zones.extend(resp["result"])
        info = resp.get("result_info", {})
        if page >= info.get("total_pages", 1):
            break
        page += 1
    return zones


def get_setting(zone_id: str, setting: str, token: str) -> str:
    resp = _ok(_req("GET", f"/zones/{zone_id}/settings/{setting}", token))
    return resp["result"]["value"]


def patch_setting(zone_id: str, setting: str, value, token: str) -> dict:
    return _ok(_req("PATCH", f"/zones/{zone_id}/settings/{setting}",
                    token, body={"value": value}))


def get_dnssec(zone_id: str, token: str) -> dict:
    return _ok(_req("GET", f"/zones/{zone_id}/dnssec", token))["result"]


def enable_dnssec(zone_id: str, token: str) -> dict:
    return _ok(_req("PATCH", f"/zones/{zone_id}/dnssec",
                    token, body={"status": "active"}))["result"]


def list_dns_records(zone_id: str, token: str) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        resp = _ok(_req("GET",
                        f"/zones/{zone_id}/dns_records?per_page=100&page={page}",
                        token))
        out.extend(resp["result"])
        info = resp.get("result_info", {})
        if page >= info.get("total_pages", 1):
            break
        page += 1
    return out


def create_dns_record(zone_id: str, record: dict, token: str) -> dict:
    return _ok(_req("POST", f"/zones/{zone_id}/dns_records",
                    token, body=record))["result"]


# ---- baseline applier ------------------------------------------------------

def apply_baseline_to_zone(
    zone: dict, token: str, *, apply: bool, skip_dns: bool, report_email: str,
) -> dict:
    """Returns a dict summarising what changed (or would change) on this zone."""
    name = zone["name"]
    zone_id = zone["id"]
    changes: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    # Plain zone settings
    for setting, desired in ZONE_SETTINGS.items():
        try:
            current = get_setting(zone_id, setting, token)
        except CFError as e:
            errors.append(f"read {setting}: {e}")
            continue
        if current == desired:
            skipped.append(f"{setting}={current}")
            continue
        if apply:
            try:
                patch_setting(zone_id, setting, desired, token)
                changes.append(f"{setting}: {current} -> {desired}")
            except CFError as e:
                errors.append(f"set {setting}={desired}: {e}")
        else:
            changes.append(f"{setting}: {current} -> {desired}  [DRY-RUN]")

    # HSTS / security_header
    try:
        sh = get_setting(zone_id, "security_header", token)
    except CFError as e:
        errors.append(f"read security_header: {e}")
        sh = None
    desired_hsts = HSTS_VALUE["strict_transport_security"]
    current_hsts = (sh or {}).get("strict_transport_security") or {}
    needs_hsts = (
        not current_hsts.get("enabled") or
        current_hsts.get("max_age", 0) < desired_hsts["max_age"] or
        current_hsts.get("include_subdomains") != desired_hsts["include_subdomains"]
    )
    if needs_hsts:
        if apply:
            try:
                patch_setting(zone_id, "security_header", HSTS_VALUE, token)
                changes.append("hsts: enabled (180d, includeSubDomains)")
            except CFError as e:
                errors.append(f"set hsts: {e}")
        else:
            changes.append("hsts: enabled (180d, includeSubDomains)  [DRY-RUN]")
    else:
        skipped.append("hsts (already enabled)")

    # DNSSEC
    try:
        dnssec = get_dnssec(zone_id, token)
        if dnssec.get("status") == "active":
            skipped.append("dnssec (active)")
        else:
            if apply:
                enable_dnssec(zone_id, token)
                changes.append("dnssec: enabled")
            else:
                changes.append("dnssec: enabled  [DRY-RUN]")
    except CFError as e:
        errors.append(f"dnssec: {e}")

    # DNS records (SPF + DMARC)
    if not skip_dns:
        try:
            existing = list_dns_records(zone_id, token)
        except CFError as e:
            errors.append(f"list dns: {e}")
            existing = []
        existing_index = [
            (r["type"], r["name"], (r.get("content") or "").strip().strip('"'))
            for r in existing
        ]

        spf = ("TXT", name, "v=spf1 -all")
        if spf in existing_index:
            skipped.append("spf (present)")
        else:
            if apply:
                try:
                    create_dns_record(zone_id, {
                        "type": "TXT", "name": "@",
                        "content": '"v=spf1 -all"',
                        "comment": "Kaproq baseline: no senders authorized",
                    }, token)
                    changes.append('spf: added TXT @ "v=spf1 -all"')
                except CFError as e:
                    errors.append(f"create spf: {e}")
            else:
                changes.append('spf: would add TXT @ "v=spf1 -all"  [DRY-RUN]')

        dmarc_value = (
            f"v=DMARC1; p=reject; rua=mailto:{report_email}"
        )
        dmarc_present = any(
            t == "TXT" and n.startswith("_dmarc.") and c.startswith("v=DMARC1")
            for t, n, c in existing_index
        )
        if dmarc_present:
            skipped.append("dmarc (present)")
        else:
            if apply:
                try:
                    create_dns_record(zone_id, {
                        "type": "TXT", "name": "_dmarc",
                        "content": f'"{dmarc_value}"',
                        "comment": "Kaproq baseline: reject spoofed mail",
                    }, token)
                    changes.append("dmarc: added TXT _dmarc p=reject")
                except CFError as e:
                    errors.append(f"create dmarc: {e}")
            else:
                changes.append("dmarc: would add TXT _dmarc p=reject  [DRY-RUN]")

    return {
        "zone": name, "zone_id": zone_id,
        "changes": changes, "skipped": skipped, "errors": errors,
    }


# ---- CLI -------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="Actually change settings. Default is dry-run.")
    p.add_argument("--dry-run", action="store_true",
                   help="Force dry-run mode (default unless --apply).")
    p.add_argument("--zone", action="append", default=[],
                   help="Limit to specific zone name(s). Can pass multiple.")
    p.add_argument("--skip-dns", action="store_true",
                   help="Don't manage SPF/DMARC TXT records.")
    p.add_argument("--report-email", default=os.environ.get("DMARC_REPORT_EMAIL", ""),
                   help="Email for DMARC aggregate reports. Required unless --skip-dns.")
    args = p.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.stderr.write(
            "ERROR: set CLOUDFLARE_API_TOKEN in environment.\n"
            "Create one at dash.cloudflare.com -> My Profile -> API Tokens.\n"
            "Required scopes: Zone:Read, Zone Settings:Edit, SSL:Edit, DNS:Edit\n"
        )
        return 2

    apply = args.apply and not args.dry_run
    if not args.skip_dns and not args.report_email:
        sys.stderr.write(
            "ERROR: --report-email is required (or pass --skip-dns).\n"
            "DMARC needs an aggregate-report destination.\n"
        )
        return 2

    print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"DMARC report email: {args.report_email or '(skipped)'}")
    print()

    try:
        zones = list_zones(token)
    except CFError as e:
        sys.stderr.write(f"Failed to list zones: {e}\n")
        return 1

    if args.zone:
        wanted = set(args.zone)
        zones = [z for z in zones if z["name"] in wanted]
        if not zones:
            sys.stderr.write(f"No matching zones: {wanted}\n")
            return 1

    print(f"Targeting {len(zones)} zone(s): {', '.join(z['name'] for z in zones)}")
    print("-" * 76)

    total_changes = 0
    total_errors = 0
    for zone in zones:
        result = apply_baseline_to_zone(
            zone, token, apply=apply, skip_dns=args.skip_dns,
            report_email=args.report_email,
        )
        print(f"\n{result['zone']}")
        if result["changes"]:
            for c in result["changes"]:
                print(f"  CHANGE  {c}")
        if result["skipped"]:
            for s in result["skipped"]:
                print(f"  ok      {s}")
        if result["errors"]:
            for e in result["errors"]:
                print(f"  ERROR   {e}")
        total_changes += len(result["changes"])
        total_errors += len(result["errors"])

    print("-" * 76)
    print(f"\n{'Would change' if not apply else 'Changed'}: {total_changes}")
    print(f"Errors: {total_errors}")
    if not apply and total_changes > 0:
        print("\nRe-run with --apply to commit these changes.")
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
