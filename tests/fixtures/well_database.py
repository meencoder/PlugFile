"""
Candidate well database for live RRC integration tests.

All county FIPS codes use the standard US Census / API well-numbering scheme
(state FIPS 42 = Texas; county codes 001–507 in alphabetical order, odd numbers only).

Census-verified codes used here:
  003 Andrews    135 Ector       201 Harris      245 Jefferson
  039 Brazoria   183 Gregg       227 Howard      303 Lubbock
  103 Crane      131 Duval       329 Midland     355 Nueces
  371 Pecos      389 Reeves      401 Rusk        415 Scurry
  441 Taylor     461 Upton       469 Victoria    479 Webb
  485 Wichita

Serial-number ranges chosen:
  • 00001–05000  very early wells (1920s–1940s) — in DB but may have sparse data
  • 10000–40000  mid-era wells (1960s–1990s) — richest casing / completion records
  • 50000+        modern wells — complete data but less likely to be P&A candidates yet

Add more wells by querying RRC's Plugging Permit search or OGIS export, then
dropping API numbers here with the county + district you expect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CandidateWell:
    api: str
    expected_county: Optional[str]   # None = skip county validation
    expected_district: Optional[str] # None = skip district validation
    notes: str = ""


# ---------------------------------------------------------------------------
# Master well list — organised by RRC district
# ---------------------------------------------------------------------------

WELL_DATABASE: list[CandidateWell] = [

    # ── District 01  Laredo / South Texas ──────────────────────────────────
    CandidateWell("42-131-20000", "Duval",     "01",  "Eagle Ford / South TX"),
    CandidateWell("42-131-05000", "Duval",     "01",  "Older Duval County well"),
    CandidateWell("42-479-10000", "Webb",      "01",  "Laredo area"),

    # ── District 02  Corpus Christi ─────────────────────────────────────────
    CandidateWell("42-355-20000", "Nueces",    "02",  "Corpus Christi area"),
    CandidateWell("42-355-10000", "Nueces",    "02",  "Earlier Nueces County well"),

    # ── District 03  Victoria / Karnes / Gulf Coast ─────────────────────────
    CandidateWell("42-469-10000", "Victoria",  "03",  "Victoria area"),
    CandidateWell("42-469-05000", "Victoria",  "03",  "Older Victoria County well"),

    # ── District 04  Houston area ───────────────────────────────────────────
    # 42-201-80000 exists in EWA but RRC assigns it to D03 (historical filing).
    CandidateWell("42-201-80000", "Harris",    None,  "Houston area — district per EWA may differ"),
    CandidateWell("42-201-40000", "Harris",    "04",  "Older Harris County well"),
    CandidateWell("42-039-20000", "Brazoria",  "04",  "Gulf Coast / Brazoria County"),

    # ── District 05  Beaumont / Southeast TX ───────────────────────────────
    CandidateWell("42-245-10000", "Jefferson", "05",  "Beaumont / Spindletop area"),
    CandidateWell("42-245-05000", "Jefferson", "05",  "Older Jefferson County well"),

    # ── District 06  Tyler / Kilgore / East Texas ───────────────────────────
    CandidateWell("42-401-20000", "Rusk",      "06",  "East Texas field — Kilgore area"),
    CandidateWell("42-401-12345", "Rusk",      "06",  "Mock-DB anchor well — Rusk County"),
    CandidateWell("42-183-15000", "Gregg",     "06",  "Longview / Gregg County"),
    CandidateWell("42-183-05000", "Gregg",     "06",  "Older Gregg County well"),

    # ── District 07B  Abilene ────────────────────────────────────────────────
    CandidateWell("42-441-10000", "Taylor",    "07B", "Taylor County / Abilene area"),
    CandidateWell("42-441-05000", "Taylor",    "07B", "Older Taylor County well"),

    # ── District 07C  Wichita Falls ─────────────────────────────────────────
    # 42-485-10000 exists in EWA; RRC assigns early Wichita serials to D09.
    CandidateWell("42-485-10000", "Wichita",   None,  "Wichita Falls area — district per EWA may differ"),
    CandidateWell("42-485-05000", "Wichita",   "07C", "Older Wichita County well"),

    # ── District 08  Midland / Permian Basin ────────────────────────────────
    # 42-371-00001 and 42-329-00001 are EWA-confirmed (live-verified 2026-05).
    CandidateWell("42-371-00001", "Pecos",     "08",  "EWA-confirmed -- Pecos county serial 1"),
    CandidateWell("42-329-00001", "Midland",   "08",  "EWA-confirmed -- Midland county serial 1"),
    CandidateWell("42-371-20000", "Pecos",     "08",  "Pecos County — mid-range serial"),
    CandidateWell("42-329-30000", "Midland",   "08",  "Midland County — Spraberry/Wolfcamp"),
    CandidateWell("42-103-40000", "Crane",     "08",  "Crane County — Permian"),
    CandidateWell("42-103-77001", "Crane",     "08",  "Mock-DB anchor — Crane County"),
    CandidateWell("42-135-30000", "Ector",     "08",  "Ector County / Odessa area"),
    CandidateWell("42-003-20000", "Andrews",   "08",  "Andrews County — Permian"),
    CandidateWell("42-389-15000", "Reeves",    "08",  "Reeves County / Delaware Basin"),
    CandidateWell("42-461-10000", "Upton",     "08",  "Upton County — Permian Basin"),

    # ── District 08A  Lubbock / South Plains ───────────────────────────────
    CandidateWell("42-303-20000", "Lubbock",   "08A", "Lubbock County"),
    CandidateWell("42-303-10000", "Lubbock",   "08A", "Older Lubbock County well"),

    # ── District 09  Big Spring ─────────────────────────────────────────────
    CandidateWell("42-227-15000", "Howard",    "09",  "Howard County / Big Spring"),
    CandidateWell("42-415-08000", "Scurry",    "09",  "Scurry County / Snyder area"),
]


# ---------------------------------------------------------------------------
# Convenience lookups
# ---------------------------------------------------------------------------

WELLS_BY_API: dict[str, CandidateWell] = {w.api: w for w in WELL_DATABASE}

WELLS_BY_DISTRICT: dict[str, list[CandidateWell]] = {}
for _w in WELL_DATABASE:
    WELLS_BY_DISTRICT.setdefault(_w.expected_district or "unknown", []).append(_w)

ALL_DISTRICTS: list[str] = sorted(WELLS_BY_DISTRICT.keys())


# ---------------------------------------------------------------------------
# County → district reference  (used for validation cross-checks)
# ---------------------------------------------------------------------------

COUNTY_TO_DISTRICT: dict[str, str] = {
    # D01
    "Duval": "01", "Webb": "01", "Maverick": "01", "Starr": "01",
    "Jim Hogg": "01", "Zapata": "01", "Val Verde": "01",
    # D02
    "Nueces": "02", "San Patricio": "02", "Aransas": "02",
    "Refugio": "02", "Bee": "02", "Live Oak": "02",
    # D03
    "Victoria": "03", "Karnes": "03", "DeWitt": "03",
    "Gonzales": "03", "Jackson": "03", "Lavaca": "03",
    # D04
    "Harris": "04", "Brazoria": "04", "Fort Bend": "04",
    "Galveston": "04", "Chambers": "04", "Wharton": "04",
    # D05
    "Jefferson": "05", "Orange": "05", "Hardin": "05",
    "Jasper": "05", "Tyler": "05", "Sabine": "05",
    # D06
    "Rusk": "06", "Gregg": "06", "Panola": "06",
    "Harrison": "06", "Smith": "06", "Upshur": "06",
    # D07B
    "Taylor": "07B", "Callahan": "07B", "Stephens": "07B",
    "Palo Pinto": "07B", "Eastland": "07B", "Brown": "07B",
    # D07C
    "Wichita": "07C", "Clay": "07C", "Archer": "07C",
    "Young": "07C", "Jack": "07C", "Throckmorton": "07C",
    # D08
    "Pecos": "08", "Midland": "08", "Ector": "08",
    "Andrews": "08", "Crane": "08", "Reeves": "08",
    "Ward": "08", "Winkler": "08", "Loving": "08",
    "Upton": "08", "Reagan": "08", "Glasscock": "08",
    # D08A
    "Lubbock": "08A", "Lynn": "08A", "Hockley": "08A",
    "Gaines": "08A", "Yoakum": "08A", "Terry": "08A",
    # D09
    "Howard": "09", "Scurry": "09", "Mitchell": "09",
    "Nolan": "09", "Fisher": "09", "Borden": "09",
}
