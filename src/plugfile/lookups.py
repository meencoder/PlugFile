"""Authoritative-data fetcher abstractions for W-3 prefill.

The W-3 form has fields whose canonical values live in external systems
(RRC RoRQ, RRC operator P-5 database, GAU letter portal, RRC completion
records). The deterministic core never makes network calls — it operates
on data delivered by a `Fetcher` implementation.

This module defines:

  * `Fetcher` — Protocol that any concrete data source must satisfy.
  * `MockFetcher` — Phase 1B implementation seeded from the 5 sample
    wellbore fixtures, extended with realistic operator / GAU / completion
    metadata. Used in tests and the validation runner.
  * `RRCRoRQFetcher` — documented stub for the real adapter, to be
    fleshed out in Phase 2 once we wire up the actual RRC public-data
    endpoints. Today it raises NotImplementedError.

Returning structured TypedDicts (vs. raw dicts) means schema mismatches
between the fetcher and the prefill engine fail at import time, not at
filing time.
"""

from __future__ import annotations

from typing import Protocol, TypedDict


# ---- TypedDict shapes for each lookup --------------------------------------

class WellLookupResult(TypedDict):
    """Returned by `lookup_well_by_api`. Source: RRC RoRQ well-master query."""
    api_number: str
    lease_name: str
    lease_number: str
    well_number: str
    county: str
    rrc_district: str
    field_name: str
    latitude: float
    longitude: float
    footage_ns: str
    footage_ew: str
    section_block_survey: str


class OperatorLookupResult(TypedDict):
    """Returned by `lookup_operator`. Source: RRC P-5 organization DB."""
    operator_name: str
    operator_p5_number: str
    operator_address: str


class GAULookupResult(TypedDict):
    """Returned by `lookup_gau`. Source: RRC Groundwater Advisory Unit letter."""
    buqw_depth_ft: float
    gau_letter_reference: str


class CompletionCasing(TypedDict):
    kind: str
    od_in: float
    weight_lb_per_ft: float
    grade: str
    set_depth_ft: float
    top_of_cement_ft: float
    sacks_cemented: float


class CompletionPerforation(TypedDict):
    top_ft: float
    bottom_ft: float
    zone_name: str


class CompletionRecordResult(TypedDict):
    """Returned by `lookup_completion`. Source: RRC W-1 + W-2 filings."""
    total_depth_ft: float
    spud_date: str
    completion_date: str
    casing_record: list[CompletionCasing]
    perforations: list[CompletionPerforation]


# ---- the protocol -----------------------------------------------------------

class Fetcher(Protocol):
    """Protocol any concrete data source must satisfy. The prefill engine
    is written against this interface, not against any specific backend.
    """

    def lookup_well_by_api(self, api_number: str) -> WellLookupResult: ...
    def lookup_operator(self, p5_number: str) -> OperatorLookupResult: ...
    def lookup_gau(self, api_number: str) -> GAULookupResult: ...
    def lookup_completion(self, api_number: str) -> CompletionRecordResult: ...


# ---- mock fetcher: data ----------------------------------------------------

# Map API number -> well master record (Section I + II)
_WELL_DATA: dict[str, WellLookupResult] = {
    "42-371-30001": {
        "api_number": "42-371-30001",
        "lease_name": "Heritage A",
        "lease_number": "23874",
        "well_number": "1H",
        "county": "Pecos",
        "rrc_district": "08",
        "field_name": "Spraberry (Trend Area)",
        "latitude": 31.0184,
        "longitude": -102.5531,
        "footage_ns": "660 FNL",
        "footage_ew": "1980 FWL",
        "section_block_survey": "Sec 12, Blk 47, T-7-S, T&P RR Co Survey",
    },
    "42-401-12345": {
        "api_number": "42-401-12345",
        "lease_name": "Whitfield",
        "lease_number": "08821",
        "well_number": "3",
        "county": "Rusk",
        "rrc_district": "06",
        "field_name": "East Texas",
        "latitude": 32.0407,
        "longitude": -94.7115,
        "footage_ns": "330 FSL",
        "footage_ew": "330 FEL",
        "section_block_survey": "A-123 W. Penn Survey",
    },
    "42-103-77001": {
        "api_number": "42-103-77001",
        "lease_name": "Old Yellowhouse",
        "lease_number": "44102",
        "well_number": "2",
        "county": "Crane",
        "rrc_district": "7C",
        "field_name": "McCamey, North",
        "latitude": 31.4002,
        "longitude": -102.4490,
        "footage_ns": "1320 FNL",
        "footage_ew": "660 FEL",
        "section_block_survey": "Sec 24, Blk B-1, GC&SF RR Co Survey",
    },
    "42-461-00042": {
        "api_number": "42-461-00042",
        "lease_name": "Hardin Heirs",
        "lease_number": "01277",
        "well_number": "A-1",
        "county": "Throckmorton",
        "rrc_district": "7B",
        "field_name": "Throckmorton, North",
        "latitude": 33.2008,
        "longitude": -99.2127,
        "footage_ns": "990 FNL",
        "footage_ew": "1650 FEL",
        "section_block_survey": "Sec 8, Blk 10, H&TC RR Co Survey",
    },
    "42-329-55555": {
        "api_number": "42-329-55555",
        "lease_name": "Spraberry Ranch",
        "lease_number": "31195",
        "well_number": "7",
        "county": "Midland",
        "rrc_district": "08",
        "field_name": "Spraberry (Trend Area)",
        "latitude": 32.0203,
        "longitude": -102.0144,
        "footage_ns": "660 FSL",
        "footage_ew": "1980 FEL",
        "section_block_survey": "Sec 35, Blk 38, T-2-S, T&P RR Co Survey",
    },
}


# Map P-5 number -> operator record (Section I)
_OPERATOR_DATA: dict[str, OperatorLookupResult] = {
    "112233": {
        "operator_name": "Apex Permian Operating LLC",
        "operator_p5_number": "112233",
        "operator_address": "1500 Energy Plaza, Midland, TX 79701",
    },
    "445566": {
        "operator_name": "Pine Belt Energy Inc.",
        "operator_p5_number": "445566",
        "operator_address": "300 Pine St, Henderson, TX 75652",
    },
    "778899": {
        "operator_name": "Sunset Heritage Wells LLC",
        "operator_p5_number": "778899",
        "operator_address": "PO Box 421, Crane, TX 79731",
    },
    "001234": {
        "operator_name": "Estate of J.M. Hardin (Operator of Record)",
        "operator_p5_number": "001234",
        "operator_address": "112 Main St, Throckmorton, TX 76483",
    },
    "224488": {
        "operator_name": "Stacked Pay Operating LP",
        "operator_p5_number": "224488",
        "operator_address": "5050 Wall St, Midland, TX 79705",
    },
}


# Map API -> P-5 (well-to-operator linkage)
_WELL_TO_OPERATOR: dict[str, str] = {
    "42-371-30001": "112233",
    "42-401-12345": "445566",
    "42-103-77001": "778899",
    "42-461-00042": "001234",
    "42-329-55555": "224488",
}


# Map API -> GAU letter (Section VII)
_GAU_DATA: dict[str, GAULookupResult] = {
    "42-371-30001": {"buqw_depth_ft": 1500.0,
                     "gau_letter_reference": "GAU-2024-03-12-Pecos-21874"},
    "42-401-12345": {"buqw_depth_ft": 800.0,
                     "gau_letter_reference": "GAU-2024-08-04-Rusk-09915"},
    "42-103-77001": {"buqw_depth_ft": 1200.0,
                     "gau_letter_reference": "GAU-2024-05-19-Crane-08812"},
    "42-461-00042": {"buqw_depth_ft": 600.0,
                     "gau_letter_reference": "GAU-2024-09-22-Throck-00301"},
    "42-329-55555": {"buqw_depth_ft": 1200.0,
                     "gau_letter_reference": "GAU-2024-02-28-Midland-44218"},
}


# Map API -> completion record (Sections III, IV, VI)
# Sacks-cemented values are realistic for the casing/cement-column geometry.
_COMPLETION_DATA: dict[str, CompletionRecordResult] = {
    "42-371-30001": {
        "total_depth_ft": 10500.0,
        "spud_date": "2018-03-15",
        "completion_date": "2018-09-22",
        "casing_record": [
            {"kind": "surface", "od_in": 13.375, "weight_lb_per_ft": 54.5,
             "grade": "J-55", "set_depth_ft": 1800.0, "top_of_cement_ft": 0.0,
             "sacks_cemented": 1100.0},
            {"kind": "intermediate", "od_in": 9.625, "weight_lb_per_ft": 40.0,
             "grade": "N-80", "set_depth_ft": 6500.0, "top_of_cement_ft": 0.0,
             "sacks_cemented": 1850.0},
            {"kind": "production", "od_in": 5.5, "weight_lb_per_ft": 17.0,
             "grade": "P-110", "set_depth_ft": 10300.0,
             "top_of_cement_ft": 5000.0, "sacks_cemented": 720.0},
        ],
        "perforations": [
            {"top_ft": 10150.0, "bottom_ft": 10200.0, "zone_name": "Wolfcamp A"},
        ],
    },
    "42-401-12345": {
        "total_depth_ft": 4500.0,
        "spud_date": "2009-06-04",
        "completion_date": "2009-08-19",
        "casing_record": [
            {"kind": "surface", "od_in": 8.625, "weight_lb_per_ft": 24.0,
             "grade": "J-55", "set_depth_ft": 1100.0, "top_of_cement_ft": 0.0,
             "sacks_cemented": 380.0},
            {"kind": "production", "od_in": 4.5, "weight_lb_per_ft": 11.6,
             "grade": "J-55", "set_depth_ft": 4400.0,
             "top_of_cement_ft": 1000.0, "sacks_cemented": 285.0},
        ],
        "perforations": [
            {"top_ft": 4250.0, "bottom_ft": 4280.0, "zone_name": "Travis Peak"},
        ],
    },
    "42-103-77001": {
        "total_depth_ft": 6000.0,
        "spud_date": "1979-02-11",
        "completion_date": "1979-04-30",
        "casing_record": [
            {"kind": "surface", "od_in": 9.625, "weight_lb_per_ft": 36.0,
             "grade": "J-55", "set_depth_ft": 800.0, "top_of_cement_ft": 0.0,
             "sacks_cemented": 215.0},
            {"kind": "production", "od_in": 5.5, "weight_lb_per_ft": 17.0,
             "grade": "J-55", "set_depth_ft": 5900.0,
             "top_of_cement_ft": 2000.0, "sacks_cemented": 410.0},
        ],
        "perforations": [
            {"top_ft": 5800.0, "bottom_ft": 5840.0, "zone_name": "Austin Chalk"},
        ],
    },
    "42-461-00042": {
        "total_depth_ft": 3500.0,
        "spud_date": "1957-11-08",
        "completion_date": "1958-01-22",
        "casing_record": [
            {"kind": "production", "od_in": 7.0, "weight_lb_per_ft": 23.0,
             "grade": "J-55", "set_depth_ft": 3400.0,
             "top_of_cement_ft": 1500.0, "sacks_cemented": 290.0},
        ],
        "perforations": [
            {"top_ft": 3300.0, "bottom_ft": 3320.0, "zone_name": "Strawn"},
        ],
    },
    "42-329-55555": {
        "total_depth_ft": 8000.0,
        "spud_date": "2014-07-30",
        "completion_date": "2014-12-11",
        "casing_record": [
            {"kind": "surface", "od_in": 9.625, "weight_lb_per_ft": 36.0,
             "grade": "J-55", "set_depth_ft": 1500.0, "top_of_cement_ft": 0.0,
             "sacks_cemented": 410.0},
            {"kind": "production", "od_in": 5.5, "weight_lb_per_ft": 17.0,
             "grade": "N-80", "set_depth_ft": 7900.0,
             "top_of_cement_ft": 3000.0, "sacks_cemented": 670.0},
        ],
        "perforations": [
            {"top_ft": 6900.0, "bottom_ft": 6950.0, "zone_name": "Dean"},
            {"top_ft": 7350.0, "bottom_ft": 7400.0, "zone_name": "Upper Spraberry"},
            {"top_ft": 7700.0, "bottom_ft": 7740.0, "zone_name": "Lower Spraberry"},
        ],
    },
}


# ---- mock fetcher: implementation ------------------------------------------

class FetcherError(LookupError):
    """Raised when an authoritative source has no record for the requested key."""


class MockFetcher:
    """In-memory fetcher seeded from the 5 Phase 1A fixtures.

    Implements the `Fetcher` Protocol. Use in tests, demos, and CI. For
    production data you'd swap in `RRCRoRQFetcher` (Phase 2).
    """

    @staticmethod
    def known_api_numbers() -> list[str]:
        return sorted(_WELL_DATA.keys())

    def lookup_well_by_api(self, api_number: str) -> WellLookupResult:
        try:
            return dict(_WELL_DATA[api_number])  # type: ignore[return-value]
        except KeyError:
            raise FetcherError(f"No RRC well record for API {api_number}")

    def lookup_operator(self, p5_number: str) -> OperatorLookupResult:
        try:
            return dict(_OPERATOR_DATA[p5_number])  # type: ignore[return-value]
        except KeyError:
            raise FetcherError(f"No RRC operator record for P-5 {p5_number}")

    def lookup_gau(self, api_number: str) -> GAULookupResult:
        try:
            return dict(_GAU_DATA[api_number])  # type: ignore[return-value]
        except KeyError:
            raise FetcherError(f"No GAU letter on file for API {api_number}")

    def lookup_completion(self, api_number: str) -> CompletionRecordResult:
        try:
            rec = _COMPLETION_DATA[api_number]
        except KeyError:
            raise FetcherError(f"No completion record for API {api_number}")
        # Deep-copy so callers can mutate without poisoning the mock store.
        return {
            "total_depth_ft": rec["total_depth_ft"],
            "spud_date": rec["spud_date"],
            "completion_date": rec["completion_date"],
            "casing_record": [dict(c) for c in rec["casing_record"]],
            "perforations": [dict(p) for p in rec["perforations"]],
        }

    def operator_p5_for_api(self, api_number: str) -> str:
        """Helper: resolve well -> P-5 number. Real RRC RoRQ returns this in
        the well-master record."""
        try:
            return _WELL_TO_OPERATOR[api_number]
        except KeyError:
            raise FetcherError(
                f"No operator-of-record linkage for API {api_number}"
            )


# ---- real-world adapter stub -----------------------------------------------

class RRCRoRQFetcher:
    """Stub for the real Texas Railroad Commission Online Research Queries
    adapter. Not implemented in Phase 1B; documented here so the integration
    path is clear.

    Production wiring (Phase 2) needs:
      * Auth: RoRQ public queries do not require auth, but rate limits apply.
      * Endpoint: https://webapps.rrc.texas.gov/CMPL/  (well master)
                  https://webapps.rrc.texas.gov/PUR/   (P-5 operator)
                  https://www.rrc.texas.gov/groundwater-advisory-unit/
                  (GAU letters — usually individual PDFs, not API)
      * Parser: most RRC public endpoints are HTML/ASPX, not JSON. Real
                adapter wraps `requests` + a parser (lxml/BeautifulSoup),
                mapping fields into our TypedDict shapes.
      * Caching: 24-hour cache layer is reasonable; well-master records
                rarely change once a well is completed.
    """

    def lookup_well_by_api(self, api_number: str) -> WellLookupResult:
        raise NotImplementedError(
            "RRCRoRQFetcher is a Phase-2 stub. Use MockFetcher for "
            "Phase 1B tests; implement HTTP+parser layer in Phase 2."
        )

    def lookup_operator(self, p5_number: str) -> OperatorLookupResult:
        raise NotImplementedError("RRCRoRQFetcher is a Phase-2 stub.")

    def lookup_gau(self, api_number: str) -> GAULookupResult:
        raise NotImplementedError("RRCRoRQFetcher is a Phase-2 stub.")

    def lookup_completion(self, api_number: str) -> CompletionRecordResult:
        raise NotImplementedError("RRCRoRQFetcher is a Phase-2 stub.")
