#!/usr/bin/env python3
r"""Deploy landing/ to Cloudflare Pages and attach kaproq.com.

Automates Steps 2-4 of the deployment walkthrough:
  Step 2 - Create the Pages project (if missing) and upload landing/ contents.
  Step 3 - Attach apex domain (kaproq.com) and www subdomain to the project.
  Step 4 - Poll until SSL provisioned, then run HTTPS + security-header checks.

Prerequisites:
  - CLOUDFLARE_API_TOKEN env var
  - Node + Wrangler installed:    winget install OpenJS.NodeJS  &&  npm install -g wrangler
  - landing/index.html exists

API token scopes (create at dash.cloudflare.com -> My Profile -> API Tokens):
  Account -> Cloudflare Pages       -> Edit
  Account -> Account Settings       -> Read
  Zone    -> DNS                    -> Edit
  Zone    -> Zone                   -> Read

Usage:
  $env:CLOUDFLARE_API_TOKEN = "..."           # PowerShell
  python tools\deploy_landing.py              # full deploy with defaults
  python tools\deploy_landing.py --skip-verify
  python tools\deploy_landing.py --project-name caprock --domain kaproq.com
  python tools\deploy_landing.py --landing-dir landing
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"


# ---- HTTP helpers ----------------------------------------------------------

class CFError(RuntimeError):
    pass


def cf(method: str, path: str, token: str, body=None) -> dict:
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data,
                                 method=method, headers=headers)
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


def ok(resp: dict) -> dict:
    if not resp.get("success", False):
        raise CFError(f"API error: {json.dumps(resp.get('errors', resp))}")
    return resp


# ---- account / zone discovery ----------------------------------------------

def list_accounts(token: str) -> list[dict]:
    return ok(cf("GET", "/accounts?per_page=50", token))["result"]


def list_zones(token: str) -> list[dict]:
    return ok(cf("GET", "/zones?per_page=50", token))["result"]


# ---- pages project ---------------------------------------------------------

def get_pages_project(account_id: str, name: str, token: str) -> dict | None:
    try:
        return ok(cf("GET",
                     f"/accounts/{account_id}/pages/projects/{name}",
                     token))["result"]
    except CFError as e:
        if "404" in str(e) or "not found" in str(e).lower():
            return None
        raise


def create_pages_project(account_id: str, name: str, token: str) -> dict:
    body = {
        "name": name,
        "production_branch": "main",
    }
    return ok(cf("POST", f"/accounts/{account_id}/pages/projects",
                 token, body=body))["result"]


def attach_domain(account_id: str, project: str, domain: str, token: str) -> dict:
    """Attach a custom domain to the Pages project. Idempotent."""
    # Check if already attached
    try:
        existing = ok(cf("GET",
                         f"/accounts/{account_id}/pages/projects/{project}/domains",
                         token))["result"] or []
        for d in existing:
            if d.get("name") == domain:
                return d
    except CFError:
        pass
    return ok(cf("POST",
                 f"/accounts/{account_id}/pages/projects/{project}/domains",
                 token, body={"name": domain}))["result"]


def domain_status(account_id: str, project: str, domain: str, token: str) -> dict:
    return ok(cf("GET",
                 f"/accounts/{account_id}/pages/projects/{project}/domains/{domain}",
                 token))["result"]


# ---- wrangler shell-out -----------------------------------------------------

def check_wrangler() -> str:
    path = shutil.which("wrangler") or shutil.which("wrangler.cmd")
    if path:
        return path
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return f"{npx} wrangler"
    sys.stderr.write(
        "ERROR: wrangler not found.\n"
        "  Install Node:    winget install OpenJS.NodeJS\n"
        "  Install Wrangler: npm install -g wrangler\n"
    )
    raise SystemExit(2)


def wrangler_deploy(landing_dir: str, project_name: str,
                    account_id: str, token: str) -> str:
    """Run `wrangler pages deploy <dir> --project-name <name>`. Returns
    the deployment URL printed by wrangler."""
    bin_ = check_wrangler()
    cmd = (
        f'{bin_} pages deploy "{landing_dir}" '
        f'--project-name "{project_name}" --branch main --commit-dirty=true'
    )
    env = {**os.environ,
           "CLOUDFLARE_API_TOKEN": token,
           "CLOUDFLARE_ACCOUNT_ID": account_id}
    print(f"  $ {cmd}")
    proc = subprocess.run(cmd, shell=True, env=env,
                          capture_output=True, text=True, timeout=300,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out)
    if proc.returncode != 0:
        raise CFError(f"wrangler exit {proc.returncode}")
    # Pull the deployment URL out of wrangler's output if present
    for line in out.splitlines():
        if ".pages.dev" in line:
            for tok in line.split():
                if tok.startswith("https://") and ".pages.dev" in tok:
                    return tok.rstrip(",.")
    return ""


# ---- verification -----------------------------------------------------------

def verify_https(url: str, expect_status: int = 200) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "kaproq-deploy/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            headers = dict(resp.headers)
            return status == expect_status, (
                f"{status}  hsts={headers.get('Strict-Transport-Security', 'absent')[:60]}"
            )
    except Exception as e:
        return False, str(e)


def wait_for_ssl(account_id: str, project: str, domain: str,
                 token: str, timeout_s: int = 300) -> bool:
    """Poll until the domain shows SSL active, or timeout."""
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        try:
            d = domain_status(account_id, project, domain, token)
            status = d.get("status") or d.get("certificate_authority", {}).get("status")
            if status != last_status:
                print(f"  {domain}: status = {status}")
                last_status = status
            if status in ("active", "ready"):
                return True
        except CFError as e:
            print(f"  status check error: {e}")
        time.sleep(5)
    return False


# ---- main -------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project-name", default="caprock",
                   help="Cloudflare Pages project name (default: caprock).")
    p.add_argument("--domain", default="kaproq.com",
                   help="Apex domain to attach (default: kaproq.com).")
    p.add_argument("--landing-dir", default="landing",
                   help="Local directory to deploy (default: landing).")
    p.add_argument("--account-id", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
                   help="Cloudflare account ID. Auto-detected if omitted.")
    p.add_argument("--skip-verify", action="store_true",
                   help="Skip the post-deploy HTTPS + headers check.")
    p.add_argument("--skip-www", action="store_true",
                   help="Don't attach the www. subdomain (apex only).")
    args = p.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.stderr.write("ERROR: set CLOUDFLARE_API_TOKEN.\n")
        return 2

    landing_dir = os.path.abspath(args.landing_dir)
    if not os.path.isdir(landing_dir):
        sys.stderr.write(f"ERROR: landing directory not found: {landing_dir}\n")
        return 2
    if not os.path.exists(os.path.join(landing_dir, "index.html")):
        sys.stderr.write(f"ERROR: {landing_dir}\\index.html missing.\n")
        return 2

    print("=" * 72)
    print(f"Deploying {args.landing_dir}/ -> Cloudflare Pages project '{args.project_name}'")
    print(f"Custom domain: {args.domain}" + ("" if args.skip_www else f" + www.{args.domain}"))
    print("=" * 72)

    # Resolve account
    if args.account_id:
        account_id = args.account_id
    else:
        accounts = list_accounts(token)
        if not accounts:
            sys.stderr.write("ERROR: no accounts visible to this token.\n")
            return 1
        if len(accounts) > 1:
            sys.stderr.write(
                "ERROR: token sees multiple accounts; pass --account-id explicitly.\n"
                "Available:\n"
            )
            for a in accounts:
                sys.stderr.write(f"  {a['id']}  {a['name']}\n")
            return 1
        account_id = accounts[0]["id"]
    print(f"Account: {account_id}")

    # Step 2a: project
    print(f"\n[2a] Pages project '{args.project_name}':")
    project = get_pages_project(account_id, args.project_name, token)
    if project is None:
        print("  not found, creating...")
        project = create_pages_project(account_id, args.project_name, token)
        print(f"  created: {project.get('subdomain')}")
    else:
        print(f"  exists: {project.get('subdomain')}")

    # Step 2b: upload via Wrangler
    print(f"\n[2b] Uploading {args.landing_dir}/ via Wrangler:")
    deploy_url = wrangler_deploy(landing_dir, args.project_name,
                                 account_id, token)
    if deploy_url:
        print(f"  deployed: {deploy_url}")

    # Step 3: attach domains
    print(f"\n[3] Attaching custom domain(s):")
    apex = attach_domain(account_id, args.project_name, args.domain, token)
    print(f"  apex     : {args.domain} -> {apex.get('status', 'pending')}")
    if not args.skip_www:
        www_domain = f"www.{args.domain}"
        www = attach_domain(account_id, args.project_name, www_domain, token)
        print(f"  www      : {www_domain} -> {www.get('status', 'pending')}")

    # Wait for SSL
    print(f"\n[3.5] Waiting for SSL on {args.domain} (up to 5 min)...")
    if wait_for_ssl(account_id, args.project_name, args.domain, token):
        print(f"  {args.domain}: ready")
    else:
        print(f"  {args.domain}: still pending after 5 min; check the dashboard.")

    if args.skip_verify:
        print("\nSkipping verification (--skip-verify).")
        return 0

    # Step 4: verify
    print(f"\n[4] Verifying deployment:")
    checks = [
        (f"https://{args.domain}", 200),
        (f"https://{args.domain}/for-engineers", 200),
    ]
    if not args.skip_www:
        checks.append((f"https://www.{args.domain}", 200))  # may 301 - both OK
    all_ok = True
    for url, want in checks:
        ok_, info = verify_https(url, want)
        flag = "OK   " if ok_ else "FAIL "
        print(f"  {flag} {url}  [{info}]")
        if not ok_:
            all_ok = False

    print()
    print("=" * 72)
    if all_ok:
        print(f"DONE. Live at https://{args.domain}")
        print("Next: replace the Stripe Payment Link placeholder in landing/index.html,")
        print("commit, push, and re-run this script (it will re-upload).")
    else:
        print("Some checks failed. SSL may still be provisioning; wait 2-5 min and retry.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
