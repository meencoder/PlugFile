#!/usr/bin/env python3
r"""Diagnose and fix a stuck Cloudflare Pages domain attachment.

If `python tools\deploy_landing.py` succeeded with file upload but the
domain status sat at 'initializing' or 'pending' indefinitely and DNS
doesn't resolve, run this script. It:

  1. Lists current DNS records on the zone for the apex (and www).
  2. Lists the Pages project's attached domains and their statuses.
  3. Adds the missing CNAME records that point apex/www at <project>.pages.dev
     (proxied through Cloudflare so SSL provisions automatically).
  4. Polls until the local resolver can resolve the domain.
  5. Polls Pages until the domain status flips to active.

Idempotent. If records already exist correctly, it just polls.

Prereqs same as deploy_landing.py:
  CLOUDFLARE_API_TOKEN env var with Pages:Edit, DNS:Edit, Zone:Read.

Usage:
  python tools\fix_pages_dns.py
  python tools\fix_pages_dns.py --domain kaproq.com --project-name caprock
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"


class CFError(RuntimeError):
    pass


def cf(method: str, path: str, token: str, body=None) -> dict:
    req = urllib.request.Request(
        API + path,
        data=(json.dumps(body).encode("utf-8") if body is not None else None),
        method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
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


def ok(r: dict) -> dict:
    if not r.get("success", False):
        raise CFError(json.dumps(r.get("errors", r)))
    return r


def find_zone(token: str, domain: str) -> dict:
    z = ok(cf("GET", f"/zones?name={domain}", token))["result"]
    if not z:
        raise CFError(f"No zone found for {domain}")
    return z[0]


def find_account(token: str) -> str:
    accounts = ok(cf("GET", "/accounts?per_page=50", token))["result"]
    if len(accounts) == 1:
        return accounts[0]["id"]
    sys.stderr.write("Multiple accounts visible. Pass --account-id.\n")
    for a in accounts:
        sys.stderr.write(f"  {a['id']}  {a['name']}\n")
    raise SystemExit(1)


def list_records(token: str, zone_id: str, name: str) -> list[dict]:
    return ok(cf("GET", f"/zones/{zone_id}/dns_records?name={name}",
                 token))["result"]


def upsert_cname(token: str, zone_id: str, name: str,
                 target: str, *, apex: bool) -> dict:
    """Add or replace a CNAME (proxied) for the given name -> target.

    Cloudflare's DNS allows CNAME at the apex via CNAME-flattening, but only
    if no other A/AAAA/CNAME exists at that name. If conflicting records
    exist, delete them first.
    """
    existing = list_records(token, zone_id, name)
    keep: dict | None = None
    for r in existing:
        rtype = r["type"]
        if rtype == "CNAME" and r["content"].rstrip(".") == target.rstrip("."):
            keep = r
            continue
        if rtype in ("A", "AAAA", "CNAME"):
            print(f"  removing conflict: {rtype} {r['name']} -> {r['content']}")
            ok(cf("DELETE", f"/zones/{zone_id}/dns_records/{r['id']}", token))
    if keep:
        if not keep.get("proxied"):
            print(f"  enabling proxy on existing CNAME {name} -> {target}")
            ok(cf("PATCH", f"/zones/{zone_id}/dns_records/{keep['id']}",
                  token, body={"proxied": True}))
        else:
            print(f"  CNAME {name} -> {target} already correct (proxied)")
        return keep

    payload = {
        "type": "CNAME",
        "name": "@" if apex else name.split(".", 1)[0],
        "content": target,
        "proxied": True,
        "ttl": 1,  # automatic
        "comment": "Kaproq Pages: auto-attached by fix_pages_dns.py",
    }
    print(f"  creating CNAME {name} -> {target} (proxied)")
    return ok(cf("POST", f"/zones/{zone_id}/dns_records",
                 token, body=payload))["result"]


def get_pages_domain(token: str, account_id: str,
                     project: str, domain: str) -> dict | None:
    try:
        return ok(cf("GET",
                     f"/accounts/{account_id}/pages/projects/{project}/domains/{domain}",
                     token))["result"]
    except CFError as e:
        if "404" in str(e):
            return None
        raise


def reattach_pages_domain(token: str, account_id: str,
                          project: str, domain: str) -> dict:
    existing = get_pages_domain(token, account_id, project, domain)
    if existing:
        return existing
    return ok(cf("POST",
                 f"/accounts/{account_id}/pages/projects/{project}/domains",
                 token, body={"name": domain}))["result"]


def wait_dns_resolves(domain: str, timeout_s: int = 180) -> bool:
    deadline = time.time() + timeout_s
    last_state = None
    while time.time() < deadline:
        try:
            ip = socket.gethostbyname(domain)
            if last_state != ip:
                print(f"  {domain} resolves to {ip}")
                last_state = ip
            return True
        except socket.gaierror:
            if last_state != "no-record":
                print(f"  {domain}: no DNS yet, polling...")
                last_state = "no-record"
            time.sleep(10)
    return False


def wait_pages_active(token: str, account_id: str, project: str,
                      domain: str, timeout_s: int = 600) -> bool:
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        try:
            d = get_pages_domain(token, account_id, project, domain)
            status = (d or {}).get("status") or "unknown"
            if status != last_status:
                print(f"  pages status: {status}")
                last_status = status
            if status in ("active", "ready"):
                return True
        except CFError as e:
            print(f"  status query error: {e}")
        time.sleep(10)
    return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--domain", default="kaproq.com")
    p.add_argument("--project-name", default="caprock")
    p.add_argument("--account-id", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
    p.add_argument("--skip-www", action="store_true")
    args = p.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.stderr.write("ERROR: set CLOUDFLARE_API_TOKEN.\n")
        return 2

    account_id = args.account_id or find_account(token)
    print(f"Account: {account_id}")
    zone = find_zone(token, args.domain)
    zone_id = zone["id"]
    print(f"Zone:    {args.domain}  ({zone_id})")
    target = f"{args.project_name}.pages.dev"
    print(f"Target:  {target}")

    print(f"\n[1] Current DNS records on apex:")
    for r in list_records(token, zone_id, args.domain):
        print(f"  {r['type']:6s} {r['name']:30s} -> {r['content']}  proxied={r.get('proxied', False)}")

    if not args.skip_www:
        print(f"\n[1b] Current DNS records on www:")
        for r in list_records(token, zone_id, f"www.{args.domain}"):
            print(f"  {r['type']:6s} {r['name']:30s} -> {r['content']}  proxied={r.get('proxied', False)}")

    print(f"\n[2] Pages domain attachments:")
    apex_pd = get_pages_domain(token, account_id, args.project_name, args.domain)
    print(f"  {args.domain}: {(apex_pd or {}).get('status', 'NOT ATTACHED')}")
    if not args.skip_www:
        www_pd = get_pages_domain(token, account_id, args.project_name,
                                  f"www.{args.domain}")
        print(f"  www.{args.domain}: {(www_pd or {}).get('status', 'NOT ATTACHED')}")

    print(f"\n[3] Ensuring CNAME records:")
    upsert_cname(token, zone_id, args.domain, target, apex=True)
    if not args.skip_www:
        upsert_cname(token, zone_id, f"www.{args.domain}", target, apex=False)

    print(f"\n[4] Re-attaching Pages domains (idempotent):")
    reattach_pages_domain(token, account_id, args.project_name, args.domain)
    if not args.skip_www:
        reattach_pages_domain(token, account_id, args.project_name,
                              f"www.{args.domain}")

    print(f"\n[5] Waiting for DNS to resolve from this machine (3 min cap):")
    dns_ok = wait_dns_resolves(args.domain, 180)
    if not dns_ok:
        print("  DNS still doesn't resolve from this machine. The records ARE")
        print("  in Cloudflare; this is local-resolver caching. Try:")
        print("    Get-Process -Name 'dnscache' | Restart-Service")
        print("    or: ipconfig /flushdns")

    print(f"\n[6] Waiting for Pages SSL to go active (10 min cap):")
    ssl_ok = wait_pages_active(token, account_id, args.project_name,
                               args.domain, 600)

    print("\n" + "=" * 72)
    if dns_ok and ssl_ok:
        print(f"DONE. Visit https://{args.domain}")
    else:
        print("Partial success. State is correct in Cloudflare; SSL/DNS may")
        print("still be propagating. Curl from any other network to verify:")
        print(f"  curl -I https://{args.domain}")
    return 0 if (dns_ok and ssl_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
