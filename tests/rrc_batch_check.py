#!/usr/bin/env python
"""
Standalone RRC well-database batch checker.

Iterates the well database, hits the live RRC API, and prints a result table.
This is NOT a pytest file — run it directly:

    python tests/rrc_batch_check.py
    python tests/rrc_batch_check.py --district 08
    python tests/rrc_batch_check.py --district 06 --completion
    python tests/rrc_batch_check.py --no-cache --output csv > results.csv
    python tests/rrc_batch_check.py --api 42-371-30001 42-329-30000

Usage notes
-----------
* Rate limit: 1 req/s by default.  For --completion the run takes ~2x as long.
* Results are written to stdout.  Redirect to save: > rrc_results.csv
* Cache lives at ~/.cache/plugfile-rrc (24-hour TTL).  --no-cache bypasses it.
* Wells not found in RRC are listed with status NOT_FOUND — not an error.

Exit codes
----------
  0  All found wells passed validation (county/district match where expected)
  1  One or more found wells failed county/district validation
  2  Network or configuration error
"""

from __future__ import annotations

import io
import sys as _sys

# Force UTF-8 on Windows consoles (avoids cp1252 encode errors for special chars)
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(_sys.stderr, "reconfigure"):
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Optional

# -- make src/ importable when running from repo root -----------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from plugfile.lookups import FetcherError
from plugfile.lookups_rrc import RRCRoRQFetcher

# -- import well database ----------------------------------------------------
sys.path.insert(0, str(_REPO_ROOT / "tests"))
from fixtures.well_database import (
    WELL_DATABASE,
    WELLS_BY_DISTRICT,
    CandidateWell,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

class WellCheckResult:
    def __init__(
        self,
        well: CandidateWell,
        status: str,               # FOUND | NOT_FOUND | ERROR
        county_returned: str = "",
        district_returned: str = "",
        lease_name: str = "",
        operator_name: str = "",
        total_depth_ft: Optional[float] = None,
        fields_populated: int = 0,
        county_match: Optional[bool] = None,
        district_match: Optional[bool] = None,
        error_msg: str = "",
        # completion
        completion_status: str = "",  # OK | MISSING | SKIP | ERROR
        casing_rows: int = 0,
        perf_rows: int = 0,
    ):
        self.well = well
        self.status = status
        self.county_returned = county_returned
        self.district_returned = district_returned
        self.lease_name = lease_name
        self.operator_name = operator_name
        self.total_depth_ft = total_depth_ft
        self.fields_populated = fields_populated
        self.county_match = county_match
        self.district_match = district_match
        self.error_msg = error_msg
        self.completion_status = completion_status
        self.casing_rows = casing_rows
        self.perf_rows = perf_rows

    @property
    def passed(self) -> bool:
        if self.status != "FOUND":
            return True  # not-found / errors are not validation failures
        ok = True
        if self.county_match is False:
            ok = False
        if self.district_match is False:
            ok = False
        return ok

    def to_dict(self) -> dict:
        return {
            "api": self.well.api,
            "expected_district": self.well.expected_district or "",
            "expected_county": self.well.expected_county or "",
            "status": self.status,
            "district_returned": self.district_returned,
            "county_returned": self.county_returned,
            "lease_name": self.lease_name,
            "operator_name": self.operator_name,
            "total_depth_ft": "" if self.total_depth_ft is None else self.total_depth_ft,
            "fields_populated": self.fields_populated,
            "county_match": "" if self.county_match is None else ("PASS" if self.county_match else "FAIL"),
            "district_match": "" if self.district_match is None else ("PASS" if self.district_match else "FAIL"),
            "completion_status": self.completion_status,
            "casing_rows": self.casing_rows,
            "perf_rows": self.perf_rows,
            "notes": self.well.notes,
            "error": self.error_msg,
        }


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------

def check_well(
    well: CandidateWell,
    fetcher: RRCRoRQFetcher,
    include_completion: bool = False,
) -> WellCheckResult:
    # --- well lookup ---
    try:
        wdata = fetcher.lookup_well_by_api(well.api)
    except FetcherError as exc:
        msg = str(exc).lower()
        if "no result" in msg or "not found" in msg or "no well" in msg:
            return WellCheckResult(well=well, status="NOT_FOUND", error_msg=str(exc))
        return WellCheckResult(well=well, status="ERROR", error_msg=str(exc))
    except Exception as exc:  # noqa: BLE001
        return WellCheckResult(well=well, status="ERROR", error_msg=f"Unexpected: {exc}")

    # count populated fields
    fields_populated = sum(
        1 for v in wdata.values()
        if v is not None and v != "" and v != []
    )

    # county / district validation
    county_match: Optional[bool] = None
    district_match: Optional[bool] = None

    if well.expected_county:
        county_match = well.expected_county.lower() in (wdata.get("county") or "").lower()

    if well.expected_district:
        actual_d = (wdata.get("rrc_district") or "").strip().upper()
        district_match = actual_d == well.expected_district.strip().upper()

    result = WellCheckResult(
        well=well,
        status="FOUND",
        county_returned=wdata.get("county") or "",
        district_returned=wdata.get("rrc_district") or "",
        lease_name=wdata.get("lease_name") or "",
        operator_name="",  # resolved below if needed
        total_depth_ft=None,
        fields_populated=fields_populated,
        county_match=county_match,
        district_match=district_match,
    )

    # --- completion (optional) ---
    if include_completion:
        try:
            cdata = fetcher.lookup_completion(well.api)
            result.total_depth_ft = cdata.get("total_depth_ft")
            result.casing_rows = len(cdata.get("casing_record") or [])
            result.perf_rows = len(cdata.get("perforations") or [])
            result.completion_status = "OK"
        except FetcherError:
            result.completion_status = "MISSING"
        except Exception as exc:  # noqa: BLE001
            result.completion_status = f"ERROR: {exc}"

    return result


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

# ANSI colours (stripped in non-TTY environments)
_TTY = sys.stdout.isatty()
_GREEN  = "\033[32m" if _TTY else ""
_RED    = "\033[31m" if _TTY else ""
_YELLOW = "\033[33m" if _TTY else ""
_CYAN   = "\033[36m" if _TTY else ""
_DIM    = "\033[2m"  if _TTY else ""
_RESET  = "\033[0m"  if _TTY else ""


def _status_fmt(status: str) -> str:
    if status == "FOUND":
        return f"{_GREEN}✓ FOUND{_RESET}"
    if status == "NOT_FOUND":
        return f"{_YELLOW}✗ NOT FOUND{_RESET}"
    return f"{_RED}⚠ ERROR{_RESET}"


def _match_fmt(match: Optional[bool]) -> str:
    if match is None:
        return "—"
    return f"{_GREEN}✓{_RESET}" if match else f"{_RED}✗{_RESET}"


def print_table(results: list[WellCheckResult], include_completion: bool) -> None:
    # column widths
    W_API  = 15
    W_DIST = 6
    W_CTY  = 14
    W_DIST_RET = 6
    W_CTY_RET  = 14
    W_LEASE = 24
    W_STATUS = 12

    # header
    sep = "─" * (W_API + W_DIST + W_CTY + W_DIST_RET + W_CTY_RET + W_LEASE + W_STATUS + 20)
    print(f"\n{_CYAN}RRC Live Well Database Check — {date.today()}{_RESET}")
    print(sep)
    hdr = (
        f"{'API':<{W_API}}  {'D.Exp':<{W_DIST}}  {'Co.Exp':<{W_CTY}}"
        f"  {'D.Got':<{W_DIST_RET}}  {'Co.Got':<{W_CTY_RET}}"
        f"  {'Lease':<{W_LEASE}}  {'Status':<{W_STATUS}}"
    )
    if include_completion:
        hdr += "  Cas  Perf  TD"
    print(hdr)
    print(sep)

    for r in results:
        d_match = _match_fmt(r.district_match)
        c_match = _match_fmt(r.county_match)
        if r.status == "FOUND":
            dist_ret = r.district_returned[:W_DIST_RET]
            cty_ret  = r.county_returned[:W_CTY_RET]
        else:
            dist_ret = _DIM + "—" + _RESET
            cty_ret  = _DIM + (r.error_msg[:W_CTY_RET] if r.error_msg else "—") + _RESET

        lease = r.lease_name[:W_LEASE] if r.lease_name else _DIM + "—" + _RESET

        line = (
            f"{r.well.api:<{W_API}}  "
            f"{(r.well.expected_district or '?'):<{W_DIST}}  "
            f"{(r.well.expected_county or '?'):<{W_CTY}}  "
            f"{dist_ret:<{W_DIST_RET + len(d_match) - 1}}  "
            f"{cty_ret:<{W_CTY_RET + len(c_match) - 1}}  "
            f"{lease:<{W_LEASE + 5}}  "
            f"{_status_fmt(r.status)}"
        )

        if include_completion:
            if r.status == "FOUND":
                td_str = f"{r.total_depth_ft:,.0f}'" if r.total_depth_ft else "—"
                line += (
                    f"  {r.casing_rows:>3}  {r.perf_rows:>4}  {td_str}"
                )
            else:
                line += "   —    —    —"

        print(line)

    print(sep)

    # summary
    found   = [r for r in results if r.status == "FOUND"]
    not_found = [r for r in results if r.status == "NOT_FOUND"]
    errors  = [r for r in results if r.status == "ERROR"]
    d_fail  = [r for r in found if r.district_match is False]
    c_fail  = [r for r in found if r.county_match is False]

    print(
        f"\n{_CYAN}Summary:{_RESET}"
        f"  {_GREEN}{len(found)} found{_RESET}"
        f"  {_YELLOW}{len(not_found)} not found{_RESET}"
        f"  {_RED}{len(errors)} errors{_RESET}"
        f"  |  District failures: {len(d_fail)}"
        f"  County failures: {len(c_fail)}"
    )
    if d_fail:
        print(f"  {_RED}District mismatches:{_RESET} " + ", ".join(r.well.api for r in d_fail))
    if c_fail:
        print(f"  {_RED}County mismatches:{_RESET} " + ", ".join(r.well.api for r in c_fail))
    print()


def print_json(results: list[WellCheckResult]) -> None:
    print(json.dumps([r.to_dict() for r in results], indent=2))


def print_csv(results: list[WellCheckResult]) -> None:
    if not results:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(results[0].to_dict().keys()))
    writer.writeheader()
    for r in results:
        writer.writerow(r.to_dict())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-test the RRC fetcher against the well database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--district", "-d",
        metavar="DIST",
        help="Only test wells in this RRC district (e.g. 08, 06, 07C)",
    )
    parser.add_argument(
        "--api",
        metavar="API",
        nargs="+",
        help="Test specific API numbers instead of the full database",
    )
    parser.add_argument(
        "--completion", "-c",
        action="store_true",
        help="Also fetch completion records (casing + perforation counts)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass disk cache (makes fresh HTTP requests each run)",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.0,
        metavar="SECS",
        help="Seconds between RRC requests (default: 1.0)",
    )
    args = parser.parse_args()

    # build well list
    if args.api:
        from fixtures.well_database import WELLS_BY_API
        wells = []
        for api in args.api:
            if api in WELLS_BY_API:
                wells.append(WELLS_BY_API[api])
            else:
                # create ad-hoc entry
                from fixtures.well_database import CandidateWell
                wells.append(CandidateWell(api, None, None, "ad-hoc"))
    elif args.district:
        dist = args.district.upper()
        wells = WELLS_BY_DISTRICT.get(dist, [])
        if not wells:
            print(f"No wells found for district '{dist}'.", file=sys.stderr)
            print(f"Available districts: {sorted(WELLS_BY_DISTRICT)}", file=sys.stderr)
            return 2
    else:
        wells = WELL_DATABASE

    if not wells:
        print("No wells to test.", file=sys.stderr)
        return 2

    # initialise fetcher
    try:
        fetcher = RRCRoRQFetcher(
            rate_limit_s=args.rate_limit,
            cache_dir=None if args.no_cache else None,  # None uses default
        )
        if args.no_cache:
            # clear the cache for this run by disabling it
            fetcher._cache = None  # type: ignore[attr-defined]
    except Exception as exc:
        print(f"Failed to initialise RRCRoRQFetcher: {exc}", file=sys.stderr)
        return 2

    # run checks
    results: list[WellCheckResult] = []
    total = len(wells)

    if args.output == "table":
        print(f"Checking {total} well(s)… (rate limit: {args.rate_limit}s/req)")

    for i, well in enumerate(wells, 1):
        if args.output == "table":
            print(f"  [{i:>2}/{total}] {well.api}  D{well.expected_district or '?'}  {well.notes[:30]}", end="\r", flush=True)

        r = check_well(well, fetcher, include_completion=args.completion)
        results.append(r)

    if args.output == "table":
        print(" " * 80, end="\r")  # clear progress line
        print_table(results, include_completion=args.completion)
    elif args.output == "json":
        print_json(results)
    elif args.output == "csv":
        print_csv(results)

    # exit code
    validation_failures = [r for r in results if not r.passed]
    return 1 if validation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
