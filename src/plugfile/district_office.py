"""Auto district-office routing for Texas RRC plugging filings.

A verified W-3 plugging record must be filed with the RRC district office
that covers the well (SWR 14(b)(1): in duplicate, within 30 days). Online
W-3 submissions are also routed to the "appropriate RRC district office"
(training deck p.38). This module maps a well's RRC district code to the
correct district office's address, phone, fax, and email.

Contact data is transcribed verbatim from the RRC "Form W-3A and W-3
Submission and Review" training deck (Borrego/Beckham), slide p.44 —
"District Office Contacts". Offices change; ``RRC_OFFICES_SOURCE`` records
the provenance and callers should verify against rrc.texas.gov before
relying on an address for delivery.

Usage::

    from plugfile.district_office import route_by_api_with_mock

    routing = route_by_api_with_mock("42-371-30001")
    print(routing.office.name, routing.office.phone)   # Midland 432-684-5581
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .lookups import Fetcher, MockFetcher


RRC_OFFICES_SOURCE = (
    "RRC 'Form W-3A and W-3 Submission and Review' training deck "
    "(Borrego/Beckham), slide p.44. Verify against rrc.texas.gov before "
    "delivery."
)


# ---- office records ---------------------------------------------------------

@dataclass(frozen=True)
class DistrictOffice:
    """One RRC oil-&-gas district office and the districts it covers."""
    key: str                     # stable slug, e.g. "midland"
    name: str                    # office city label, e.g. "Midland"
    districts: tuple[str, ...]   # RRC district codes this office serves
    address_line1: str
    city_state_zip: str
    phone: str
    fax: Optional[str]
    email: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "districts": list(self.districts),
            "address_line1": self.address_line1,
            "city_state_zip": self.city_state_zip,
            "phone": self.phone,
            "fax": self.fax,
            "email": self.email,
        }


# Transcribed verbatim from deck p.44.
RRC_DISTRICT_OFFICES: tuple[DistrictOffice, ...] = (
    DistrictOffice(
        "san_antonio", "San Antonio", ("01", "02"),
        "112 E. Pecan Street, Suite 705", "San Antonio, TX 78205",
        "210-227-1313", "210-227-4822", "san_antonio@rrc.texas.gov",
    ),
    DistrictOffice(
        "houston", "Houston", ("03",),
        "1919 N. Loop West, Suite 620", "Houston, TX 77008",
        "713-869-5001", "713-869-9621", "houston@rrc.texas.gov",
    ),
    DistrictOffice(
        "corpus_christi", "Corpus Christi", ("04",),
        "10320 IH-37", "Corpus Christi, TX 78410",
        "361-242-3113", "361-242-9613", "corpus_christi@rrc.texas.gov",
    ),
    DistrictOffice(
        # Deck groups Districts 05 & 06 under the Kilgore office (located in
        # Henderson). 6E is administratively part of the same region.
        "kilgore", "Kilgore", ("05", "06", "6E"),
        "100 Bane Blvd.", "Henderson, TX 75652",
        "903-655-1840", None, "kilgore@rrc.texas.gov",
    ),
    DistrictOffice(
        "abilene", "Abilene", ("7B",),
        "1969 Industrial Blvd.", "Abilene, TX 79602",
        "325-692-0404", "325-692-0273", "abilene@rrc.texas.gov",
    ),
    DistrictOffice(
        "san_angelo", "San Angelo", ("7C",),
        "622 South Oakes, Suite J", "San Angelo, TX 76903",
        "325-657-7450", "325-657-7455", "san_angelo@rrc.texas.gov",
    ),
    DistrictOffice(
        "midland", "Midland", ("08",),
        "10 Desta Dr., Suite 500 E", "Midland, TX 79705",
        "432-684-5581", "432-684-6005", "midland@rrc.texas.gov",
    ),
    DistrictOffice(
        "lubbock", "Lubbock", ("8A",),
        "6302 Iola Avenue, Suite 600", "Lubbock, TX 79424",
        "806-698-6509", "806-698-6532", "DOLubbock8A@rrc.texas.gov",
    ),
    DistrictOffice(
        "wichita_falls", "Wichita Falls", ("09",),
        "5800 Kell Blvd., Suite 300", "Wichita Falls, TX 76310",
        "940-723-2153", "940-723-5088", "wichita_falls@rrc.texas.gov",
    ),
    DistrictOffice(
        "pampa", "Pampa", ("10",),
        "200 West Foster, Room 300", "Pampa, TX 79065",
        "806-665-1653", "806-665-4217", "pampa@rrc.texas.gov",
    ),
)

# district code -> DistrictOffice (built from the records above)
_OFFICE_BY_DISTRICT: dict[str, DistrictOffice] = {
    code: office for office in RRC_DISTRICT_OFFICES for code in office.districts
}


# ---- routing result ---------------------------------------------------------

@dataclass
class DistrictRouting:
    """Where a filing for this well should be delivered / submitted."""
    api_number: Optional[str]
    rrc_district: Optional[str]      # normalized district code
    county: Optional[str]
    matched: bool                    # True when an office was found
    office: Optional[DistrictOffice]
    filing_note: str
    source: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_number": self.api_number,
            "rrc_district": self.rrc_district,
            "county": self.county,
            "matched": self.matched,
            "office": self.office.to_dict() if self.office else None,
            "filing_note": self.filing_note,
            "source": self.source,
            "warnings": self.warnings,
        }


_FILING_NOTE = (
    "File the verified W-3 plugging record with this district office within "
    "30 days of plugging (SWR 14(b)(1) — in duplicate). Online W-3 "
    "submissions are routed here automatically on 'Submit to District'."
)


# ---- normalization ----------------------------------------------------------

def normalize_district_code(code: str | None) -> str | None:
    """Canonicalize an RRC district code.

    Examples::

        "8"   -> "08"      "08" -> "08"      " 8 " -> "08"
        "7c"  -> "7C"      "6e" -> "6E"      "8a"  -> "8A"
        ""/None -> None
    """
    if not code:
        return None
    c = code.strip().upper()
    if not c:
        return None
    # Pure numeric → zero-pad to two digits ("8" -> "08", "10" stays "10").
    if c.isdigit():
        return c.zfill(2)
    # Alphanumeric like "7C", "6E", "8A": uppercase, drop any leading zero on
    # the numeric part ("07B" -> "7B").
    m = re.fullmatch(r"0?(\d+)([A-Z])", c)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return c


# ---- public API -------------------------------------------------------------

def district_office_for(rrc_district: str | None) -> DistrictOffice | None:
    """Return the :class:`DistrictOffice` serving *rrc_district*, or None."""
    code = normalize_district_code(rrc_district)
    if code is None:
        return None
    return _OFFICE_BY_DISTRICT.get(code)


def route_filing(
    *,
    rrc_district: str | None = None,
    county: str | None = None,
    api_number: str | None = None,
) -> DistrictRouting:
    """Resolve the district office for a filing from its district code.

    Pure function — no I/O. Use :func:`route_by_api` to resolve the district
    code from an API number via an RRC lookup first.
    """
    warnings: list[str] = []
    code = normalize_district_code(rrc_district)

    if code is None:
        warnings.append(
            "No RRC district code supplied — cannot route. Look up the well "
            "or enter its district (01-10, 6E, 7B, 7C, 8A)."
        )
        office = None
    else:
        office = _OFFICE_BY_DISTRICT.get(code)
        if office is None:
            warnings.append(
                f"District {code!r} did not match any known RRC district "
                "office. Verify the code against rrc.texas.gov."
            )

    return DistrictRouting(
        api_number=api_number,
        rrc_district=code,
        county=county,
        matched=office is not None,
        office=office,
        filing_note=_FILING_NOTE if office else "",
        source=RRC_OFFICES_SOURCE,
        warnings=warnings,
    )


def route_by_api(api_number: str, fetcher: Fetcher) -> DistrictRouting:
    """Look up the well, then route to its district office.

    Resolves ``rrc_district`` and ``county`` from the RRC well lookup and
    hands them to :func:`route_filing`.
    """
    warnings: list[str] = []
    rrc_district = county = None
    try:
        well = fetcher.lookup_well_by_api(api_number)
        # WellLookupResult is a TypedDict (dict at runtime).
        rrc_district = well.get("rrc_district") if isinstance(well, dict) else getattr(well, "rrc_district", None)
        county = well.get("county") if isinstance(well, dict) else getattr(well, "county", None)
    except Exception as exc:
        warnings.append(f"Well lookup failed: {exc}. Enter the district manually.")

    routing = route_filing(
        rrc_district=rrc_district, county=county, api_number=api_number
    )
    # Prepend any lookup warning.
    routing.warnings = warnings + routing.warnings
    return routing


def route_by_api_with_mock(api_number: str) -> DistrictRouting:
    """Shortcut for tests / demos using the in-memory MockFetcher."""
    return route_by_api(api_number, MockFetcher())
