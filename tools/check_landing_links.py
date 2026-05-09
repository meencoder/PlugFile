#!/usr/bin/env python3
r"""Verify every link on the Kaproq landing site.

Two modes:

  --local                        Parse landing/*.html locally. Verifies that
                                 internal page links resolve to existing files,
                                 anchor links (#section) resolve to existing
                                 IDs, and external links return 2xx-3xx.

  --live https://kaproq.com  Fetch the live site, follow internal links,
                                 verify same as above plus that every page
                                 actually returns 200.

Exit code 0 if all checks pass, 1 if any fail.

Stdlib only.

Usage:
  python tools\check_landing_links.py --local
  python tools\check_landing_links.py --live https://kaproq.com
  python tools\check_landing_links.py --live https://kaproq.com --skip-external
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


class _LimitedRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect handler that caps the number of hops to avoid infinite loops."""
    def __init__(self, max_redirects: int = 3) -> None:
        self.max_redirects = max_redirects
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > self.max_redirects:
            raise urllib.error.HTTPError(
                req.full_url, code,
                f"redirect cap ({self.max_redirects}) exceeded; possible loop",
                headers, fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# ---- HTML parsing -----------------------------------------------------------

class LinkExtractor(HTMLParser):
    """Pull every link, anchor target, and src out of a single HTML doc."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.images: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if "id" in a and a["id"]:
            self.ids.add(a["id"])
        if "name" in a and tag == "a" and a["name"]:
            self.ids.add(a["name"])  # legacy <a name="...">

        if tag == "a":
            href = a.get("href")
            if href:
                self.links.append(href)
        elif tag == "link":
            href = a.get("href")
            if href and "stylesheet" in (a.get("rel") or "").lower():
                self.stylesheets.append(href)
        elif tag == "img":
            src = a.get("src")
            if src:
                self.images.append(src)


def parse(content: str) -> LinkExtractor:
    p = LinkExtractor()
    p.feed(content)
    return p


# ---- HTTP HEAD with GET fallback -------------------------------------------

# Patterns that should not be treated as broken links
_CF_EMAIL_OBFUSCATION = "/cdn-cgi/l/email-protection"
_STRIPE_PLACEHOLDER = "REPLACE_WITH_YOUR_PAYMENT_LINK"


def _is_known_safe(url: str) -> tuple[bool, str] | None:
    """Pre-flight checks for URL patterns that are valid but would fail HTTP
    fetch. Returns (ok, info) if we recognize the URL, else None."""
    if _CF_EMAIL_OBFUSCATION in url:
        return True, "(Cloudflare email obfuscation; resolves via JS)"
    if _STRIPE_PLACEHOLDER in url:
        return True, "(Stripe Payment Link placeholder — set in Step 2)"
    return None


def http_check(url: str, *, timeout: int = 12) -> tuple[bool, str]:
    """HEAD then GET fallback. Returns (ok, info)."""
    known = _is_known_safe(url)
    if known is not None:
        return known
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url, method=method,
                headers={"User-Agent": "kaproq-linkcheck/1.0",
                         "Accept": "*/*"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return True, f"{resp.status}"
        except urllib.error.HTTPError as e:
            if 200 <= e.code < 400:
                return True, f"{e.code}"
            if method == "GET":
                return False, f"HTTP {e.code}"
        except urllib.error.URLError as e:
            if method == "GET":
                return False, f"network: {e.reason}"
        except Exception as e:
            if method == "GET":
                return False, f"error: {e}"
    return False, "no response"


# ---- local mode -------------------------------------------------------------

def check_local(landing_dir: str, *, skip_external: bool) -> tuple[int, int]:
    """Parse all .html files in landing_dir; verify links + anchors + assets."""
    landing_dir = os.path.abspath(landing_dir)
    if not os.path.isdir(landing_dir):
        print(f"ERROR: no such directory: {landing_dir}")
        return 0, 1

    html_files = [
        f for f in os.listdir(landing_dir)
        if f.endswith(".html") and not f.startswith(".")
    ]
    if not html_files:
        print(f"ERROR: no .html files in {landing_dir}")
        return 0, 1

    page_index: dict[str, LinkExtractor] = {}
    for f in html_files:
        with open(os.path.join(landing_dir, f), "r", encoding="utf-8") as fh:
            page_index[f] = parse(fh.read())

    passes = 0
    fails = 0
    print(f"=== Local link check on {landing_dir} ({len(html_files)} pages) ===\n")

    for page, doc in page_index.items():
        print(f"[{page}]")
        unique_links = list(dict.fromkeys(doc.links + doc.images + doc.stylesheets))
        for link in unique_links:
            ok, info = check_local_link(link, page, page_index, landing_dir,
                                        skip_external=skip_external)
            mark = "OK   " if ok else "FAIL "
            if ok:
                passes += 1
            else:
                fails += 1
            print(f"  {mark} {link:<60} {info}")
        if not unique_links:
            print(f"  (no links)")
        print()
    return passes, fails


def check_local_link(link: str, page: str,
                     page_index: dict[str, LinkExtractor],
                     landing_dir: str, *, skip_external: bool) -> tuple[bool, str]:
    if link.startswith("#"):
        # Same-page anchor
        anchor = link[1:]
        if not anchor:
            return True, "(empty fragment ok)"
        if anchor in page_index[page].ids:
            return True, f"#{anchor} found in {page}"
        return False, f"#{anchor} not found in {page}"

    if link.startswith(("mailto:", "tel:")):
        return True, "(scheme link)"

    if link.startswith(("http://", "https://")):
        if skip_external:
            return True, "(external, skipped)"
        return http_check(link)

    # Relative or root-relative path (possibly with #fragment)
    if "#" in link:
        path, frag = link.split("#", 1)
    else:
        path, frag = link, ""

    if not path or path == ".":
        path = page
    elif path == "/":
        path = "index.html"  # root maps to index.html
    elif path.startswith("/"):
        path = path.lstrip("/")  # treat as relative to landing_dir
    target = os.path.normpath(os.path.join(landing_dir, path))
    if not target.startswith(landing_dir):
        return False, "escapes landing dir"

    if not os.path.exists(target):
        # Cloudflare Pages clean-URL: /for-engineers -> for-engineers.html
        if os.path.exists(target + ".html"):
            target_file = path + ".html"
        else:
            return False, "file not found"
    else:
        target_file = path

    if frag:
        if target_file in page_index:
            if frag in page_index[target_file].ids:
                return True, f"{target_file}#{frag} found"
            return False, f"#{frag} not found in {target_file}"
        return True, f"{target_file} exists (anchor not checked, non-html)"
    return True, f"{target_file} exists"


# ---- live mode --------------------------------------------------------------

def check_live(start_url: str, *, skip_external: bool) -> tuple[int, int]:
    """Fetch start_url, recursively crawl same-origin pages, verify all links."""
    parsed = urllib.parse.urlparse(start_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    visited: dict[str, LinkExtractor] = {}
    queue: list[str] = [start_url.rstrip("/") or origin]
    print(f"=== Live link check from {start_url} ===\n")

    passes = 0
    fails = 0

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "kaproq-linkcheck/1.0"})
            # Limit redirect-follow depth (default urllib follows up to 10).
            # 308 -> rewrite -> 308 chains would otherwise hang the crawler.
            opener = urllib.request.build_opener(_LimitedRedirect(max_redirects=3))
            with opener.open(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                final_url = resp.url
            doc = parse(content)
            visited[url] = doc
            print(f"[{url}]")
        except Exception as e:
            print(f"FAIL fetch {url}: {e}")
            fails += 1
            continue

        unique_links = list(dict.fromkeys(doc.links + doc.images + doc.stylesheets))
        for link in unique_links:
            absolute = urllib.parse.urljoin(url, link)
            ok, info = check_live_link(absolute, url, doc, origin,
                                       skip_external=skip_external)
            mark = "OK   " if ok else "FAIL "
            if ok:
                passes += 1
            else:
                fails += 1
            print(f"  {mark} {link:<60} {info}")
            # Crawl same-origin HTML links we haven't seen
            if (absolute.startswith(origin)
                    and absolute not in visited
                    and absolute not in queue
                    and _CF_EMAIL_OBFUSCATION not in absolute
                    and not absolute.endswith((".svg", ".png", ".jpg",
                                               ".css", ".js", ".pdf"))):
                queue.append(absolute.split("#")[0])
        print()
    return passes, fails


def check_live_link(absolute: str, page: str, doc: LinkExtractor,
                    origin: str, *, skip_external: bool) -> tuple[bool, str]:
    if absolute.startswith(("mailto:", "tel:")):
        return True, "(scheme link)"
    if "#" in absolute:
        base, frag = absolute.split("#", 1)
    else:
        base, frag = absolute, ""

    if base.startswith(origin) and base.rstrip("/") == page.rstrip("/").split("#")[0]:
        # Same-page anchor
        if frag and frag in doc.ids:
            return True, f"#{frag} found"
        if frag:
            return False, f"#{frag} not found"

    if not absolute.startswith(("http://", "https://")):
        return False, f"not a URL: {absolute}"

    if not absolute.startswith(origin) and skip_external:
        return True, "(external, skipped)"
    return http_check(absolute)


# ---- main -------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--local", action="store_true",
                   help="Check files in --landing-dir (default: ./landing).")
    g.add_argument("--live",
                   help="URL of the live site, e.g. https://kaproq.com")
    p.add_argument("--landing-dir", default="landing")
    p.add_argument("--skip-external", action="store_true",
                   help="Don't fetch external URLs (offline check).")
    args = p.parse_args()

    if args.local:
        passes, fails = check_local(args.landing_dir,
                                    skip_external=args.skip_external)
    else:
        passes, fails = check_live(args.live, skip_external=args.skip_external)

    print("=" * 72)
    print(f"PASS: {passes}    FAIL: {fails}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
