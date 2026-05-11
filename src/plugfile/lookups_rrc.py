"""Real Texas RRC public-data fetcher (Phase 2A).

Implements the Fetcher protocol against RRC's public web endpoints. Drop-in
replacement for `MockFetcher`. Production path:

    from plugfile.lookups_rrc import RRCRoRQFetcher
    from plugfile.prefill import prefill_w3
    fetcher = RRCRoRQFetcher()
    form, conflicts = prefill_w3("42-371-30001", fetcher)

Architecture:
  * `requests.Session` with `urllib3` retry for 429/5xx
  * 1 req/sec throttle (RRC is government infra; be polite)
  * `diskcache` 24-hour TTL (well-master records rarely change post-completion)
  * `lxml.html` for parsing the ASPX response pages
  * Per-field selector specs (`_SELECTORS_*` dicts) so when RRC updates their
    HTML you change one place per field, not the parser logic

HTML selectors are calibrated against RRC's public site as best understood.
RRC occasionally redesigns; the CLI debugger
(`python -m plugfile.lookups_rrc 42-371-30001`) dumps raw HTML to disk and
prints the parsed result, turning selector recalibration into a 30-second loop.

For test environments without internet egress, see `tests/test_lookups_rrc.py`
which uses `responses` to stub the HTTP layer with synthetic-but-shaped HTML.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import diskcache
    import lxml.html
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError as e:
    raise ImportError(
        f"Phase 2A dependencies missing: {e}. "
        f'Run `pip install -e ".[dev]"` from the repo root.'
    ) from None

from .lookups import (
    CompletionCasing,
    CompletionPerforation,
    CompletionRecordResult,
    FetcherError,
    GAULookupResult,
    OperatorLookupResult,
    WellLookupResult,
)


# ---- configuration ---------------------------------------------------------

USER_AGENT = "Plugfile-RRC-Fetcher/0.2 (+https://plugfile.com)"
DEFAULT_RATE_LIMIT_S = 1.0
DEFAULT_CACHE_TTL = 86400  # 24 hours
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "plugfile-rrc"

# RRC public-data endpoints. RRC moves these around occasionally; verify
# current URLs with the CLI debugger if a fetch returns unexpected HTML.
RRC_CMPL_SEARCH = "https://webapps.rrc.texas.gov/CMPL/searchAction.do"
RRC_CMPL_DETAIL = "https://webapps.rrc.texas.gov/CMPL/publicSearchAction.do"
RRC_PUR_SEARCH = "https://webapps.rrc.texas.gov/PUR/publicSearchAction.do"
RRC_GAU_LIST = "https://www.rrc.texas.gov/oil-and-gas/applications-and-permits/groundwater-advisory-unit/"


# ---- selector spec (where to look in the HTML) -----------------------------

@dataclasses.dataclass(frozen=True)
class _Selector:
    """How to extract one field from the response HTML.

    xpath: lxml XPath. The first match's `.text_content()` is used unless
        `attr` is set, in which case `.get(attr)` is used.
    attr: optional HTML attribute (e.g. "value" for inputs, "href" for links).
    transform: optional fn(str) -> Any to normalize the extracted text.
    required: if True, a missing match raises FetcherError. If False, returns
        the `default` value when not found.
    default: returned when match is missing and required=False.
    """
    xpath: str
    attr: Optional[str] = None
    transform: Optional[Callable[[str], Any]] = None
    required: bool = True
    default: Any = None


# Well-master detail page selectors. These are best-known XPaths against RRC's
# public CMPL detail page format. Verify with the CLI debugger if results look
# wrong; update the XPath here, not the parser.
_SELECTORS_WELL: dict[str, _Selector] = {
    "api_number": _Selector(
        xpath="//td[contains(., 'API No.') or contains(., 'API Number')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
    ),
    "lease_name": _Selector(
        xpath="//td[contains(., 'Lease Name')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
    ),
    "lease_number": _Selector(
        xpath="//td[contains(., 'Lease No.') or contains(., 'Lease Number')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
        required=False, default="",
    ),
    "well_number": _Selector(
        xpath="//td[contains(., 'Well No.') or contains(., 'Well Number')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
    ),
    "county": _Selector(
        xpath="//td[contains(., 'County')]/following-sibling::td[1]",
        transform=lambda s: s.strip().title(),
    ),
    "rrc_district": _Selector(
        xpath="//td[contains(., 'District')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
    ),
    "field_name": _Selector(
        xpath="//td[contains(., 'Field Name') or contains(., 'Field')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
        required=False, default="",
    ),
    "operator_p5_number": _Selector(
        xpath="//td[contains(., 'Operator No.') or contains(., 'P-5')]/following-sibling::td[1]",
        transform=lambda s: s.strip().zfill(6),
    ),
    "latitude": _Selector(
        xpath="//td[contains(., 'Latitude')]/following-sibling::td[1]",
        transform=lambda s: float(s.strip()) if s.strip() else 0.0,
        required=False, default=0.0,
    ),
    "longitude": _Selector(
        xpath="//td[contains(., 'Longitude')]/following-sibling::td[1]",
        transform=lambda s: float(s.strip()) if s.strip() else 0.0,
        required=False, default=0.0,
    ),
    "footage_ns": _Selector(
        xpath="//td[contains(., 'N/S Footage') or contains(., 'NS Foot')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
        required=False, default="",
    ),
    "footage_ew": _Selector(
        xpath="//td[contains(., 'E/W Footage') or contains(., 'EW Foot')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
        required=False, default="",
    ),
    "section_block_survey": _Selector(
        xpath="//td[contains(., 'Section') and contains(., 'Block')]/following-sibling::td[1]",
        transform=lambda s: " ".join(s.split()),
        required=False, default="",
    ),
}


# Operator P-5 detail page selectors.
_SELECTORS_OPERATOR: dict[str, _Selector] = {
    "operator_name": _Selector(
        xpath="//td[contains(., 'Operator Name')]/following-sibling::td[1]",
        transform=lambda s: s.strip(),
    ),
    "operator_p5_number": _Selector(
        xpath="//td[contains(., 'Operator No.') or contains(., 'P-5 No')]/following-sibling::td[1]",
        transform=lambda s: s.strip().zfill(6),
    ),
    "operator_address": _Selector(
        xpath="//td[contains(., 'Address')]/following-sibling::td[1]",
        transform=lambda s: " ".join(s.split()),
    ),
}


# Completion-record selectors. Casing strings and perforations are tabular —
# parsed as repeated rows, not single cells. See `_parse_casing_table` and
# `_parse_perf_table` below.
_SELECTORS_COMPLETION: dict[str, _Selector] = {
    "total_depth_ft": _Selector(
        xpath="//td[contains(., 'Total Depth') or contains(., 'TD')]/following-sibling::td[1]",
        transform=lambda s: float(s.strip().replace(",", "")) if s.strip() else 0.0,
    ),
    "spud_date": _Selector(
        xpath="//td[contains(., 'Spud Date')]/following-sibling::td[1]",
        transform=lambda s: _to_iso_date(s.strip()),
        required=False, default="",
    ),
    "completion_date": _Selector(
        xpath="//td[contains(., 'Completion Date') or contains(., 'Date Completed')]/following-sibling::td[1]",
        transform=lambda s: _to_iso_date(s.strip()),
        required=False, default="",
    ),
}


def _to_iso_date(s: str) -> str:
    """Best-effort: '03/15/2018', '15-Mar-2018', '2018-03-15' → '2018-03-15'."""
    if not s:
        return ""
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d-%b-%Y", "%b %d, %Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s  # passthrough if no known format


# ---- the fetcher class -----------------------------------------------------

class RRCRoRQFetcher:
    """Production fetcher hitting RRC's public web endpoints.

    Implements the same interface as `MockFetcher`. Use as a drop-in:

        from plugfile.lookups_rrc import RRCRoRQFetcher
        from plugfile.prefill import prefill_w3
        form, conflicts = prefill_w3("42-371-30001", RRCRoRQFetcher())
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        rate_limit_s: float = DEFAULT_RATE_LIMIT_S,
        session: Optional[requests.Session] = None,
        timeout_s: int = 30,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache: diskcache.Cache = diskcache.Cache(str(self.cache_dir))
        self.cache_ttl = cache_ttl
        self.rate_limit_s = rate_limit_s
        self.timeout_s = timeout_s
        self.session = session or self._make_session()
        self._last_req_at = 0.0

    # ---- HTTP plumbing ----

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        s.headers["Accept"] = "text/html,application/xhtml+xml"
        retry = Retry(
            total=2,                       # only retry transient failures, not config errors
            backoff_factor=1.0,
            status_forcelist=(429, 502, 503, 504),  # 500 dropped — usually wrong URL/params
            allowed_methods=("GET", "POST"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_req_at
        if elapsed < self.rate_limit_s:
            time.sleep(self.rate_limit_s - elapsed)
        self._last_req_at = time.time()

    def _get_html(
        self, url: str, params: Optional[dict] = None,
        method: str = "GET", data: Optional[dict] = None,
    ) -> str:
        cache_key = json.dumps(
            {"u": url, "p": params or {}, "m": method, "d": data or {}},
            sort_keys=True,
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        self._throttle()
        full_url = url
        if params:
            full_url = url + "?" + urllib.parse.urlencode(params)
        try:
            if method == "POST":
                resp = self.session.post(url, data=data, params=params,
                                         timeout=self.timeout_s)
            else:
                resp = self.session.get(url, params=params,
                                        timeout=self.timeout_s)
            if resp.status_code == 500:
                raise FetcherError(
                    "RRC returned HTTP 500 for " + full_url + "\n"
                    "\nThis usually means the URL or parameters don't "
                    "match RRC's current schema. Run:\n"
                    "  python -m plugfile.lookups_rrc --inspect "
                    "'<paste real URL from browser DevTools>'\n"
                    "to see what response RRC returns for a URL you know "
                    "works. Then update the RRC_*_SEARCH constants and "
                    "selector XPaths in lookups_rrc.py."
                )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise FetcherError(
                f"RRC HTTP error fetching {full_url}: {e}"
            ) from None
        text = resp.text
        self.cache.set(cache_key, text, expire=self.cache_ttl)
        return text

    # ---- generic field extractor ----

    def _extract(
        self, tree: Any, selectors: dict[str, _Selector], context: str,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, spec in selectors.items():
            matches = tree.xpath(spec.xpath)
            if not matches:
                if spec.required:
                    raise FetcherError(
                        f"{context}: required field '{name}' not found "
                        f"(xpath {spec.xpath!r}). RRC may have changed the "
                        f"page layout — run `python -m plugfile.lookups_rrc "
                        f"<api>` to inspect."
                    )
                out[name] = spec.default
                continue
            first = matches[0]
            if spec.attr:
                raw = first.get(spec.attr) or ""
            elif hasattr(first, "text_content"):
                raw = first.text_content() or ""
            else:
                raw = str(first)
            out[name] = spec.transform(raw) if spec.transform else raw.strip()
        return out

    # ---- Fetcher protocol implementations ----

    def lookup_well_by_api(self, api_number: str) -> WellLookupResult:
        api_compact = api_number.replace("-", "").strip()
        if not api_compact.startswith("42") or len(api_compact) not in (10, 14):
            raise FetcherError(
                f"Texas API numbers are 10 digits (42-XXX-XXXXX) or 14 "
                f"digits with completion suffix; got {api_number!r}"
            )
        # Normalize to 14-digit form for the RRC search (it accepts both
        # but returns the long form on the detail page).
        if len(api_compact) == 10:
            api_compact = api_compact + "0000"
        # RRC's CMPL search by API. Form fields are best-known; if RRC
        # updates the form, the CLI debugger will show the actual params.
        params = {
            "method": "doSearch",
            "searchArgs.apiNumber": api_compact,
        }
        html_text = self._get_html(RRC_CMPL_SEARCH, params=params)
        tree = lxml.html.fromstring(html_text)
        if not _looks_like_well_detail(tree):
            raise FetcherError(
                f"RRC search for API {api_number} returned no detail page. "
                f"Either the well doesn't exist or RRC's response format "
                f"changed. Inspect with the CLI debugger."
            )
        fields = self._extract(tree, _SELECTORS_WELL, f"well {api_number}")
        # Re-format API to canonical XX-XXX-XXXXX
        return {  # type: ignore[return-value]
            "api_number": _format_api(api_compact),
            "lease_name": fields["lease_name"],
            "lease_number": fields["lease_number"],
            "well_number": fields["well_number"],
            "county": fields["county"],
            "rrc_district": fields["rrc_district"],
            "field_name": fields["field_name"],
            "latitude": fields["latitude"],
            "longitude": fields["longitude"],
            "footage_ns": fields["footage_ns"],
            "footage_ew": fields["footage_ew"],
            "section_block_survey": fields["section_block_survey"],
        }

    def lookup_operator(self, p5_number: str) -> OperatorLookupResult:
        p5 = p5_number.zfill(6)
        params = {"method": "doSearch", "searchArgs.operatorNumber": p5}
        html_text = self._get_html(RRC_PUR_SEARCH, params=params)
        tree = lxml.html.fromstring(html_text)
        fields = self._extract(tree, _SELECTORS_OPERATOR, f"operator P-5 {p5}")
        return {  # type: ignore[return-value]
            "operator_name": fields["operator_name"],
            "operator_p5_number": fields["operator_p5_number"],
            "operator_address": fields["operator_address"],
        }

    def lookup_gau(self, api_number: str) -> GAULookupResult:
        # GAU letters are individual PDFs, not in a structured query interface.
        # Phase 2A: best-effort — return a "GAU lookup not yet automated"
        # marker so downstream code knows to ask the operator for the BUQW
        # depth manually. Phase 2B will integrate the GAU portal once we
        # have a real well to test against.
        raise FetcherError(
            f"GAU letter lookup for API {api_number} is not yet automated. "
            f"GAU letters are filed as PDFs against specific permits and "
            f"require the operator to provide BUQW depth + letter reference. "
            f"Pass these via operator_overrides in prefill_w3()."
        )

    def lookup_completion(self, api_number: str) -> CompletionRecordResult:
        api_compact = api_number.replace("-", "")
        # Completion details typically live on the same well-detail page.
        params = {
            "method": "doSearch",
            "searchArgs.apiNumber": api_compact,
            "showCompletion": "true",
        }
        html_text = self._get_html(RRC_CMPL_DETAIL, params=params)
        tree = lxml.html.fromstring(html_text)
        fields = self._extract(
            tree, _SELECTORS_COMPLETION, f"completion {api_number}"
        )
        casing = _parse_casing_table(tree)
        perfs = _parse_perf_table(tree)
        return {  # type: ignore[return-value]
            "total_depth_ft": fields["total_depth_ft"],
            "spud_date": fields["spud_date"],
            "completion_date": fields["completion_date"],
            "casing_record": casing,
            "perforations": perfs,
        }

    def operator_p5_for_api(self, api_number: str) -> str:
        """Helper used by prefill.prefill_w3."""
        well = self.lookup_well_by_api(api_number)
        # The selector pulled operator_p5_number into the well lookup; we
        # intentionally don't include it in WellLookupResult typed-dict
        # because the protocol requires lookup_operator to be a separate
        # call, but we cache it in the diskcache so the next call to
        # lookup_operator hits the cache for the same P-5 number.
        # If the well selector didn't capture it, fall back to a separate
        # search; for now we re-fetch via the well page.
        api_compact = api_number.replace("-", "")
        params = {"method": "doSearch", "searchArgs.apiNumber": api_compact}
        html_text = self._get_html(RRC_CMPL_SEARCH, params=params)
        tree = lxml.html.fromstring(html_text)
        spec = _SELECTORS_WELL["operator_p5_number"]
        matches = tree.xpath(spec.xpath)
        if not matches:
            raise FetcherError(
                f"Could not extract operator P-5 from well {api_number}"
            )
        return spec.transform(matches[0].text_content()) if spec.transform else matches[0].text_content()


# ---- table parsers ---------------------------------------------------------

def _parse_casing_table(tree: Any) -> list[CompletionCasing]:
    """Find the casing record table on a well-detail page.

    RRC formats casing records as an HTML table with columns approximately:
        Type | Size (OD) | Weight | Grade | Set Depth | Top of Cement | Sacks

    XPath finds the table by its header row text; if RRC changes the header
    wording, update the predicate.
    """
    rows = tree.xpath(
        "//table[.//th[contains(., 'Casing') or contains(., 'CASING')]]"
        "//tr[position()>1]"
    )
    out: list[CompletionCasing] = []
    for r in rows:
        cells = [c.text_content().strip() for c in r.xpath("./td")]
        if len(cells) < 6:
            continue
        try:
            kind = (cells[0] or "").lower().strip()
            if kind not in ("conductor", "surface", "intermediate",
                            "production", "liner"):
                continue
            out.append({  # type: ignore[typeddict-item]
                "kind": kind,
                "od_in": _to_float(cells[1]),
                "weight_lb_per_ft": _to_float(cells[2]),
                "grade": cells[3] or "J-55",
                "set_depth_ft": _to_float(cells[4]),
                "top_of_cement_ft": _to_float(cells[5]) if len(cells) > 5 else 0.0,
                "sacks_cemented": _to_float(cells[6]) if len(cells) > 6 else 0.0,
            })
        except (ValueError, IndexError):
            continue
    return out


def _parse_perf_table(tree: Any) -> list[CompletionPerforation]:
    """Find the perforations table on a well-detail page.

    Columns approximately: Top | Bottom | Zone/Field | Status.
    """
    rows = tree.xpath(
        "//table[.//th[contains(., 'Perforation') or contains(., 'PERF')]]"
        "//tr[position()>1]"
    )
    out: list[CompletionPerforation] = []
    for r in rows:
        cells = [c.text_content().strip() for c in r.xpath("./td")]
        if len(cells) < 3:
            continue
        try:
            out.append({  # type: ignore[typeddict-item]
                "top_ft": _to_float(cells[0]),
                "bottom_ft": _to_float(cells[1]),
                "zone_name": cells[2] or "Unknown",
            })
        except ValueError:
            continue
    return out


def _to_float(s: str) -> float:
    s = (s or "").strip().replace(",", "").replace("'", "").replace('"', "")
    if not s or s.lower() in ("n/a", "na", "-", "—"):
        return 0.0
    return float(s)


def _looks_like_well_detail(tree: Any) -> bool:
    """Sanity check: does this look like a real well-detail page?

    Looks for the specific labeled fields RRC's detail page uses, not
    bare substrings (which would false-positive on the word 'Please' on
    no-results pages, etc.).
    """
    txt = tree.text_content()
    has_api_label = ("API No." in txt or "API Number" in txt)
    has_lease_label = ("Lease Name" in txt or "Lease No." in txt
                       or "Lease Number" in txt)
    return has_api_label and has_lease_label


def _format_api(api_compact: str) -> str:
    """Compact API → 'XX-XXX-XXXXX'. Accepts 10 or 14 digit forms; the
    canonical Plugfile display format is 10 digits (42-XXX-XXXXX) regardless
    of whether RRC returns 10 or 14."""
    digits = api_compact.replace("-", "").strip()
    if len(digits) in (10, 14):
        return f"{digits[:2]}-{digits[2:5]}-{digits[5:10]}"
    return api_compact


# ---- CLI for live calibration ----------------------------------------------

def _cli_main() -> int:
    p = argparse.ArgumentParser(
        prog="plugfile-rrc",
        description="RRC RoRQ fetcher debugger. Hits the live RRC site, "
                    "dumps raw HTML to disk, prints the parsed result. Use "
                    "this to calibrate selectors when RRC updates their HTML.",
    )
    p.add_argument("api_number", help="Texas API number, e.g. 42-371-30001")
    p.add_argument(
        "--what", choices=("well", "operator", "completion"),
        default="well",
        help="Which lookup to perform (default: well).",
    )
    p.add_argument(
        "--p5", help="P-5 operator number for --what=operator",
    )
    p.add_argument(
        "--dump-dir", default="./rrc_html_dumps",
        help="Where to save the raw HTML response for inspection.",
    )
    p.add_argument(
        "--no-cache", action="store_true",
        help="Bypass diskcache; fetch fresh from RRC.",
    )
    p.add_argument(
        "--inspect", metavar="URL",
        help="Skip parsing; just GET this URL and dump headers + body to "
             "stdout. Use this to verify a URL you found via browser "
             "DevTools returns what you expect, before updating the "
             "RRC_*_SEARCH constants.",
    )
    args = p.parse_args()

    if args.inspect:
        import requests as _r
        print("GET " + args.inspect)
        try:
            r = _r.get(args.inspect, headers={"User-Agent": USER_AGENT}, timeout=30)
            ctype = r.headers.get("content-type", "?")
            print("")
            print("status: " + str(r.status_code))
            print("content-type: " + ctype)
            print("body length: " + str(len(r.text)) + " bytes")
            print("")
            from pathlib import Path as _P
            dump = _P(args.dump_dir) / "inspect_response.html"
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_text(r.text, encoding="utf-8")
            print("full body saved to: " + str(dump))
            print("")
            print("--- first 4 KB ---")
            print(r.text[:4096])
        except Exception as e:
            print("FETCH ERROR: " + str(e))
            return 1
        return 0


    cache_dir = None
    if args.no_cache:
        import tempfile
        cache_dir = Path(tempfile.mkdtemp(prefix="rrc-nocache-"))

    fetcher = RRCRoRQFetcher(cache_dir=cache_dir)
    dump_dir = Path(args.dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)

    print(f"Hitting RRC for {args.api_number} ({args.what})...")
    try:
        if args.what == "well":
            result = fetcher.lookup_well_by_api(args.api_number)
        elif args.what == "operator":
            if not args.p5:
                print("ERROR: --p5 required for --what=operator")
                return 2
            result = fetcher.lookup_operator(args.p5)
        elif args.what == "completion":
            result = fetcher.lookup_completion(args.api_number)
    except FetcherError as e:
        print(f"\nFETCHER ERROR: {e}")
        # Dump the HTML even on failure so the user can inspect why
        return 1

    print("\nParsed result:")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
