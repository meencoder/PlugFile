"""Real Texas RRC public-data fetcher (Phase 2A).

Implements the Fetcher protocol against RRC's public web endpoints. Drop-in
replacement for `MockFetcher`. Production path:

    from plugfile.lookups_rrc import RRCRoRQFetcher
    from plugfile.prefill import prefill_w3
    fetcher = RRCRoRQFetcher()
    form, conflicts = prefill_w3("42-371-30001", fetcher)

Architecture:
  * `requests.Session` with a `_LegacyTLSAdapter` for webapps2.rrc.texas.gov
    (that server uses TLS cipher suites rejected by Python's default SSL)
  * Two-step EWA flow: GET establishes JSESSIONID, POST runs the well search
  * 1 req/sec throttle (RRC is government infra; be polite)
  * `diskcache` 24-hour TTL (well-master records rarely change post-completion)
  * `lxml.html` for parsing the HTML response pages
  * Positional column extraction from EWA search-results table, with a
    label-based fallback for nested-table EWA layouts

EWA endpoint (well lookup):
    https://webapps2.rrc.texas.gov/EWA/wellboreQueryAction.do
    POST params: methodToCall=search, searchArgs.apiNoPrefixArg (3-digit county),
                 searchArgs.apiNoSuffixArg (5-digit serial)
    Result columns: API No. | District | Lease No. | Lease Name | Well No. |
                    Field Name | Operator Name | County | On Schedule | API Depth

CMPL detail endpoint (completion records — still operational):
    https://webapps.rrc.texas.gov/CMPL/publicSearchAction.do

For test environments without internet egress, see `tests/test_lookups_rrc.py`
which uses `responses` to stub the HTTP layer with synthetic-but-shaped HTML.
Run the CLI debugger to recalibrate selectors when RRC updates their HTML:
    python -m plugfile.lookups_rrc 42-371-30001 --no-cache
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import ssl
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

USER_AGENT = "Plugfile-RRC-Fetcher/0.3 (+https://plugfile.com)"
DEFAULT_RATE_LIMIT_S = 1.0
DEFAULT_CACHE_TTL = 86400  # 24 hours
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "plugfile-rrc"

# Active RRC endpoints.
# EWA (Expanded Web Access) — current well-lookup portal.
RRC_EWA_WELLBORE = "https://webapps2.rrc.texas.gov/EWA/wellboreQueryAction.do"
# CMPL public completion-packet search — still operational for casing/perf data.
RRC_CMPL_DETAIL = "https://webapps.rrc.texas.gov/CMPL/publicSearchAction.do"
# GAU letter index — no machine-readable API yet.
RRC_GAU_LIST = "https://www.rrc.texas.gov/oil-and-gas/applications-and-permits/groundwater-advisory-unit/"

# Legacy constants kept so existing test imports don't break; the live code
# no longer uses these URLs (both return HTTP 500/404 as of 2025).
RRC_CMPL_SEARCH = "https://webapps.rrc.texas.gov/CMPL/searchAction.do"   # HTTP 500
RRC_PUR_SEARCH  = "https://webapps.rrc.texas.gov/PUR/publicSearchAction.do"  # 404


# ---- Texas county FIPS → county name lookup --------------------------------
# Used as a reliable fallback when HTML parsing can't extract county from the
# EWA result page.  FIPS source: US Census Bureau (Texas = state 48, odd codes).

_FIPS_TO_COUNTY: dict[str, str] = {
    "001": "Anderson",      "003": "Andrews",       "005": "Angelina",
    "007": "Aransas",       "009": "Archer",        "011": "Armstrong",
    "013": "Atascosa",      "015": "Austin",        "017": "Bailey",
    "019": "Bandera",       "021": "Bastrop",       "023": "Baylor",
    "025": "Bee",           "027": "Bell",          "029": "Bexar",
    "031": "Blanco",        "033": "Borden",        "035": "Bosque",
    "037": "Bowie",         "039": "Brazoria",      "041": "Brazos",
    "043": "Brewster",      "045": "Briscoe",       "047": "Brooks",
    "049": "Brown",         "051": "Burleson",      "053": "Burnet",
    "055": "Caldwell",      "057": "Calhoun",       "059": "Callahan",
    "061": "Cameron",       "063": "Camp",          "065": "Carson",
    "067": "Cass",          "069": "Castro",        "071": "Chambers",
    "073": "Cherokee",      "075": "Childress",     "077": "Clay",
    "079": "Cochran",       "081": "Coke",          "083": "Coleman",
    "085": "Collin",        "087": "Collingsworth", "089": "Colorado",
    "091": "Comal",         "093": "Comanche",      "095": "Concho",
    "097": "Cooke",         "099": "Coryell",       "101": "Cottle",
    "103": "Crane",         "105": "Crockett",      "107": "Crosby",
    "109": "Culberson",     "111": "Dallam",        "113": "Dallas",
    "115": "Dawson",        "117": "Deaf Smith",    "119": "Delta",
    "121": "Denton",        "123": "Dickens",       "125": "Dimmit",
    "127": "Donley",        "129": "Duval",         "131": "Duval",
    "133": "Eastland",      "135": "Ector",         "137": "Edwards",
    "139": "Ellis",         "141": "El Paso",       "143": "Erath",
    "145": "Falls",         "147": "Fannin",        "149": "Fayette",
    "151": "Fisher",        "153": "Floyd",         "155": "Foard",
    "157": "Fort Bend",     "159": "Franklin",      "161": "Freestone",
    "163": "Frio",          "165": "Gaines",        "167": "Galveston",
    "169": "Garza",         "171": "Gillespie",     "173": "Glasscock",
    "175": "Goliad",        "177": "Gonzales",      "179": "Gray",
    "181": "Grayson",       "183": "Gregg",         "185": "Grimes",
    "187": "Guadalupe",     "189": "Hale",          "191": "Hall",
    "193": "Hamilton",      "195": "Hansford",      "197": "Hardeman",
    "199": "Hardin",        "201": "Harris",        "203": "Harrison",
    "205": "Hartley",       "207": "Haskell",       "209": "Hays",
    "211": "Hemphill",      "213": "Henderson",     "215": "Hidalgo",
    "217": "Hill",          "219": "Hockley",       "221": "Hood",
    "223": "Hopkins",       "225": "Houston",       "227": "Howard",
    "229": "Hudspeth",      "231": "Hunt",          "233": "Hutchinson",
    "235": "Irion",         "237": "Jack",          "239": "Jackson",
    "241": "Jasper",        "243": "Jeff Davis",    "245": "Jefferson",
    "247": "Jim Hogg",      "249": "Jim Wells",     "251": "Johnson",
    "253": "Jones",         "255": "Karnes",        "257": "Kaufman",
    "259": "Kendall",       "261": "Kenedy",        "263": "Kent",
    "265": "Kerr",          "267": "Kimble",        "269": "King",
    "271": "Kinney",        "273": "Kleberg",       "275": "Knox",
    "277": "Lamar",         "279": "Lamb",          "281": "Lampasas",
    "283": "La Salle",      "285": "Lavaca",        "287": "Lee",
    "289": "Leon",          "291": "Liberty",       "293": "Limestone",
    "295": "Lipscomb",      "297": "Live Oak",      "299": "Llano",
    "301": "Loving",        "303": "Lubbock",       "305": "Lynn",
    "307": "McCulloch",     "309": "McLennan",      "311": "McMullen",
    "313": "Madison",       "315": "Marion",        "317": "Martin",
    "319": "Mason",         "321": "Matagorda",     "323": "Maverick",
    "325": "Medina",        "327": "Menard",        "329": "Midland",
    "331": "Milam",         "333": "Mills",         "335": "Mitchell",
    "337": "Montague",      "339": "Montgomery",    "341": "Moore",
    "343": "Morris",        "345": "Motley",        "347": "Nacogdoches",
    "349": "Navarro",       "351": "Newton",        "353": "Nolan",
    "355": "Nueces",        "357": "Ochiltree",     "359": "Oldham",
    "361": "Orange",        "363": "Palo Pinto",    "365": "Panola",
    "367": "Parker",        "369": "Parmer",        "371": "Pecos",
    "373": "Polk",          "375": "Potter",        "377": "Presidio",
    "379": "Rains",         "381": "Randall",       "383": "Reagan",
    "385": "Real",          "387": "Red River",     "389": "Reeves",
    "391": "Refugio",       "393": "Roberts",       "395": "Robertson",
    "397": "Rockwall",      "399": "Runnels",       "401": "Rusk",
    "403": "Sabine",        "405": "San Augustine", "407": "San Jacinto",
    "409": "San Patricio",  "411": "San Saba",      "413": "Schleicher",
    "415": "Scurry",        "417": "Shackelford",   "419": "Shelby",
    "421": "Sherman",       "423": "Smith",         "425": "Somervell",
    "427": "Starr",         "429": "Stephens",      "431": "Sterling",
    "433": "Stonewall",     "435": "Sutton",        "437": "Swisher",
    "439": "Tarrant",       "441": "Taylor",        "443": "Terrell",
    "445": "Terry",         "447": "Throckmorton",  "449": "Titus",
    "451": "Tom Green",     "453": "Travis",        "455": "Trinity",
    "457": "Tyler",         "459": "Upshur",        "461": "Upton",
    "463": "Uvalde",        "465": "Val Verde",     "467": "Van Zandt",
    "469": "Victoria",      "471": "Walker",        "473": "Waller",
    "475": "Ward",          "477": "Washington",    "479": "Webb",
    "481": "Wharton",       "483": "Wheeler",       "485": "Wichita",
    "487": "Wilbarger",     "489": "Willacy",       "491": "Williamson",
    "493": "Wilson",        "495": "Winkler",       "497": "Wise",
    "499": "Wood",          "501": "Yoakum",        "503": "Young",
    "505": "Zapata",        "507": "Zavala",
}


# ---- TLS adapter for webapps2.rrc.texas.gov --------------------------------

class _LegacyTLSAdapter(HTTPAdapter):
    """Custom HTTPS adapter that lowers TLS cipher security level.

    webapps2.rrc.texas.gov uses older TLS cipher suites that Python's default
    OpenSSL rejects with SSLV3_ALERT_HANDSHAKE_FAILURE.  Lowering to SECLEVEL=1
    re-enables the legacy ciphers needed to connect.

    Mounted only on https://webapps2.rrc.texas.gov so all other HTTPS traffic
    keeps the normal security settings.
    """

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any):  # type: ignore[override]
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        proxy_kwargs["ssl_context"] = ctx
        return super().proxy_manager_for(proxy, **proxy_kwargs)


# ---- selector spec (used by completion and operator lookups) ---------------

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


# Operator P-5 detail page selectors (kept for when PUR endpoint is restored).
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

# Completion-record selectors.  Casing strings and perforations are tabular —
# parsed as repeated rows, not single cells.  See `_parse_casing_table` and
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

# Well-detail selectors retained for completion HTML that also carries well
# metadata (the CMPL detail page shares both).
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


def _normalize_district(d: str) -> str:
    """Normalize RRC district codes to zero-padded canonical form.

    EWA returns '7B', '8A', '6', '09' etc.  We normalize to '07B', '08A',
    '06', '09' so comparisons against the well database (which uses '07B'
    etc.) work correctly.
    """
    d = d.strip()
    if not d:
        return d
    m = re.match(r"^0*(\d+)([A-Za-z]*)$", d)
    if m:
        return f"{int(m.group(1)):02d}{m.group(2).upper()}"
    return d.upper()


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

    Well lookup uses the EWA (Expanded Web Access) portal via a two-step
    GET → POST flow.  Completion lookup uses the legacy CMPL endpoint which
    still accepts public requests.  Operator lookup (PUR/P-5) is currently
    unavailable as a public endpoint and raises FetcherError.
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
            total=2,
            backoff_factor=1.0,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        # Legacy-TLS adapter for EWA host (older cipher suites required).
        ewa_adapter = _LegacyTLSAdapter(max_retries=retry)
        std_adapter = HTTPAdapter(max_retries=retry)
        # Mount order matters: more specific prefix wins.
        s.mount("https://webapps2.rrc.texas.gov", ewa_adapter)
        s.mount("https://", std_adapter)
        s.mount("http://", std_adapter)
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
        """Generic cached GET/POST helper (used by completion and operator lookups)."""
        cache_key = json.dumps(
            {"u": url, "p": params or {}, "m": method, "d": data or {}},
            sort_keys=True,
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]
        self._throttle()
        full_url = url + ("?" + urllib.parse.urlencode(params) if params else "")
        try:
            if method == "POST":
                resp = self.session.post(url, data=data, params=params,
                                         timeout=self.timeout_s)
            else:
                resp = self.session.get(url, params=params, timeout=self.timeout_s)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise FetcherError(f"RRC HTTP error fetching {full_url}: {e}") from None
        text = resp.text
        self.cache.set(cache_key, text, expire=self.cache_ttl)
        return text

    def _ewa_fetch(self, county_code: str, serial: str) -> str:
        """Two-step EWA wellbore query: GET search form, POST to form action URL.

        The EWA embeds the JSESSIONID in the form action URL (URL rewriting for
        session management).  We must:
          1. GET the wellbore query page (follow redirects) to obtain the form
          2. Extract the form's action URL (which contains ;jsessionid=...)
          3. POST the search to that exact action URL

        The response HTML is cached so repeated lookups don't re-hit RRC.
        county_code: 3-digit Texas county FIPS (e.g. '371')
        serial:      5-digit well serial (e.g. '00001')
        """
        cache_key = f"ewa_v4:{county_code}:{serial}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        self._throttle()
        try:
            # Step 1: GET the search form (follow redirects for any TLS handshake pages).
            r1 = self.session.get(
                RRC_EWA_WELLBORE,
                allow_redirects=True,
                timeout=self.timeout_s,
            )
            r1.raise_for_status()

            # Extract the form's action URL (contains ;jsessionid= path segment).
            form_tree = lxml.html.fromstring(r1.text)
            forms = form_tree.xpath('//form[@method="post"]')
            if forms:
                action = forms[0].get("action", "")
                post_url = urllib.parse.urljoin(
                    f"https://webapps2.rrc.texas.gov/EWA/", action
                )
            else:
                post_url = RRC_EWA_WELLBORE

            # Step 2: POST the well search with API number components.
            # leaseTypeArg="" means all lease types (O=oil, G=gas, ""=all).
            resp = self.session.post(
                post_url,
                timeout=self.timeout_s,
                data={
                    "methodToCall": "search",
                    "searchArgs.apiNoPrefixArg": county_code,
                    "searchArgs.apiNoSuffixArg": serial,
                    "searchArgs.leaseTypeArg": "",
                    "searchArgs.districtCodeArg": "None Selected",
                    "searchArgs.wellTypeArg": "None Selected",
                    "searchArgs.countyCodeArg": "None Selected",
                    "searchArgs.fieldNumbersArg": "",
                    "searchArgs.operatorNumbersArg": "",
                },
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise FetcherError(
                f"RRC EWA HTTP error for county={county_code} serial={serial}: {e}"
            ) from None

        html = resp.text
        self.cache.set(cache_key, html, expire=self.cache_ttl)
        return html

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

    # ---- EWA result parser ----

    def _parse_ewa_well(
        self, html: str, api_number: str, county_code: str,
    ) -> WellLookupResult:
        """Parse the EWA wellbore-query search-results page.

        Real EWA HTML structure (verified against live site):
          Each result occupies one outer <tr> with 10 direct <td> elements:
            0: API No.     (td.text = API; inner sub-table with navigation links)
            1: District    (plain text)
            2: Lease No.   (td.text = lease no.; inner sub-table with links)
            3: Lease Name  (plain text)
            4: Well No.    (plain text)
            5: Field Name  (plain text)
            6: Operator Name (plain text)
            7: County      (plain text)
            8: On Schedule (plain text)
            9: API Depth   (plain text)
          Additionally, inner <tr> elements from nested sub-tables also match
          '//tr[.//a[contains(@href,"leaseDetailAction")]]', giving 4 TR
          ancestors per result in the XPath query.

        Extraction strategy (most→least reliable):
          1. URL params in leaseDetailAction href  → district, lease_no (always)
          2. Walk up from link to the outer TR with ≥ 8 direct TDs
          3. Positional column extraction (columns 3–7)
             For td[0]/td[2] (which contain inner sub-links): use _first_text()
             to get only the leading text node, not the sub-table content
          4. County FIPS lookup from API number (last-resort fallback)
        """
        tree = lxml.html.fromstring(html)

        # No-results check: EWA says "No results found" or "(Ewa_117)" etc.
        page_lower = tree.text_content().lower()
        no_result_phrases = [
            "no result", "no well found", "no records found",
            "ewa_117", "could not find", "no wells were found",
        ]
        if any(p in page_lower for p in no_result_phrases):
            raise FetcherError(f"no result for API {api_number}")

        # Find the leaseDetailAction link (one per search result well).
        links = tree.xpath('//a[contains(@href,"leaseDetailAction")]')
        if not links:
            raise FetcherError(f"no result for API {api_number}")

        link = links[0]
        href = link.get("href", "")

        # --- URL-param extraction (reliable) ---
        def _url_p(name: str) -> str:
            m = re.search(rf"[?&]{re.escape(name)}=([^&\s]+)", href)
            return urllib.parse.unquote_plus(m.group(1)).strip() if m else ""

        district = _normalize_district(_url_p("distCode"))
        lease_no = _url_p("leaseNo")

        # --- Walk up to find the outer data TR (≥ 8 direct TDs) ---
        # The inner TR (containing the API link directly) has only 2 TDs;
        # the outer TR with all 10 columns is a higher ancestor.
        elem: Any = link
        data_tr: Any = None
        while True:
            parent = elem.getparent()
            if parent is None:
                break
            if parent.tag == "tr":
                n = len(parent.xpath("./td"))
                if n >= 8:
                    data_tr = parent
                    break
            elem = parent

        lease_name = well_number = field_name = operator_name = county_html = ""

        if data_tr is not None:
            direct_tds = data_tr.xpath("./td")

            # _first_text: get the leading text node of a TD, ignoring any
            # inner sub-elements (e.g. the navigation sub-table in col 0/2).
            def _first_text(td: Any) -> str:
                for t in td.itertext():
                    t = t.strip()
                    if t:
                        return t
                return ""

            def _full_text(n: int) -> str:
                return direct_tds[n].text_content().strip() if n < len(direct_tds) else ""

            # Columns 3–7 contain only plain text (no inner sub-elements).
            lease_name    = _full_text(3)
            well_number   = _full_text(4)
            field_name    = _full_text(5)
            operator_name = _full_text(6)
            county_html   = _full_text(7).title()

            # If district wasn't in URL params, fall back to column 1.
            if not district:
                district = _normalize_district(_first_text(direct_tds[1]) if direct_tds else "")

            # Lease No. fallback: first text node of td[2] (e.g. "22757" before the sub-link).
            if not lease_no and len(direct_tds) > 2:
                lease_no = _first_text(direct_tds[2])

        # --- County: HTML value or FIPS lookup fallback ---
        county = county_html or _FIPS_TO_COUNTY.get(county_code, "")

        # Canonical API: "42-371-30001" (10-digit display form)
        digits = api_number.replace("-", "").strip()

        return {  # type: ignore[return-value]
            "api_number": _format_api(digits),
            "lease_name": lease_name or f"Lease {lease_no}",  # never empty
            "lease_number": lease_no,
            "well_number": well_number,
            "county": county,
            "rrc_district": district,
            "field_name": field_name,
            "latitude": 0.0,
            "longitude": 0.0,
            "footage_ns": "",
            "footage_ew": "",
            "section_block_survey": "",
        }

    # ---- Fetcher protocol implementations ----

    def lookup_well_by_api(self, api_number: str) -> WellLookupResult:
        """Fetch well metadata from RRC EWA wellbore query.

        Raises FetcherError if the API format is invalid, the well is not
        found in RRC, or a network error occurs.
        """
        digits = api_number.replace("-", "").strip()
        if not digits.startswith("42") or len(digits) not in (10, 14):
            raise FetcherError(
                f"Texas API numbers are 10 or 14 digits (42-XXX-XXXXX); "
                f"got {api_number!r}"
            )
        county_code = digits[2:5]   # "371"
        serial      = digits[5:10]  # "30001"

        html = self._ewa_fetch(county_code, serial)
        return self._parse_ewa_well(html, api_number, county_code)

    def lookup_operator(self, p5_number: str) -> OperatorLookupResult:
        """Fetch operator name and address from RRC P-5 record.

        NOTE: The RRC PUR (public operator registry) endpoint is currently
        unavailable as an unauthenticated public resource.  This method
        raises FetcherError until the endpoint is restored or a replacement
        is identified.  Use RRC's web interface directly for operator lookup:
        https://webapps.rrc.texas.gov/PUR/
        """
        raise FetcherError(
            f"RRC operator lookup (PUR endpoint) is not currently available "
            f"as a public API.  P-5 number: {p5_number!r}. "
            f"Use the RRC website directly: https://webapps.rrc.texas.gov/PUR/"
        )

    def lookup_gau(self, api_number: str) -> GAULookupResult:
        """GAU letter automation is not yet implemented (Phase 2C)."""
        raise FetcherError(
            f"GAU letter lookup for API {api_number} is not yet automated. "
            f"GAU letters are filed as PDFs against specific permits and "
            f"require the operator to provide BUQW depth + letter reference. "
            f"Pass these via operator_overrides in prefill_w3()."
        )

    def lookup_completion(self, api_number: str) -> CompletionRecordResult:
        """Fetch completion record (casing + perforations) from RRC CMPL endpoint."""
        api_compact = api_number.replace("-", "")
        params = {
            "method": "doSearch",
            "searchArgs.apiNumber": api_compact,
            "showCompletion": "true",
        }
        html_text = self._get_html(RRC_CMPL_DETAIL, params=params)
        tree = lxml.html.fromstring(html_text)

        # Guard against a no-results page reaching the selector extractor.
        page_lower = tree.text_content().lower()
        if "no result" in page_lower or "not found" in page_lower:
            raise FetcherError(f"No completion record found for {api_number}")

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
        """Resolve the operator P-5 number for a well.

        Currently unavailable — the RRC CMPL search endpoint that provided
        this data returns HTTP 500.  Raises FetcherError until a replacement
        endpoint is confirmed.
        """
        raise FetcherError(
            f"Operator P-5 resolution is not available via current RRC endpoints. "
            f"API: {api_number}. Check https://webapps.rrc.texas.gov/ for "
            f"manual lookup."
        )


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


def _format_api(api_compact: str) -> str:
    """Compact API → 'XX-XXX-XXXXX'.  Accepts 10 or 14 digit forms."""
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
        "--what", choices=("well", "completion"),
        default="well",
        help="Which lookup to perform (default: well).",
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
             "stdout.  Use this to verify a URL from browser DevTools.",
    )
    args = p.parse_args()

    if args.inspect:
        import requests as _r
        print("GET " + args.inspect)
        try:
            r = _r.get(args.inspect, headers={"User-Agent": USER_AGENT}, timeout=30,
                       verify=False)
            print(f"\nstatus: {r.status_code}")
            print(f"content-type: {r.headers.get('content-type', '?')}")
            print(f"body length: {len(r.text)} bytes\n")
            from pathlib import Path as _P
            dump = _P(args.dump_dir) / "inspect_response.html"
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_text(r.text, encoding="utf-8")
            print(f"full body saved to: {dump}\n--- first 4 KB ---\n{r.text[:4096]}")
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
        else:
            result = fetcher.lookup_completion(args.api_number)
    except FetcherError as e:
        print(f"\nFETCHER ERROR: {e}")
        return 1

    print("\nParsed result:")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
