"""Synthetic GAU letter text fixtures.

These reproduce the structure and phrasing of real RRC Groundwater Advisory
Unit letters without containing actual operator data.  The RRC GAU unit issues
letters in two forms:

  GAU-1  Standard advisory — one BUQW depth, general §3.14 plugging rules.
  GAU-2  Special-case advisory — BUQW depth plus additional requirements
         (e.g. surface casing does not cover BUQW, bridge plug required).

Each fixture is a plain string representing the text layer of the PDF
(what pypdf.PdfReader.pages[n].extract_text() would return).
"""

# ---------------------------------------------------------------------------
# GAU-1 standard advisory — Heritage A Well No. 1H, Pecos County
# ---------------------------------------------------------------------------
GAU1_STANDARD = """\
RAILROAD COMMISSION OF TEXAS
Oil and Gas Division — Groundwater Advisory Unit

                        GROUNDWATER ADVISORY UNIT LETTER

Date:    March 12, 2024
Reference: GAU-2024-03-12-Pecos-21874

Operator:   Apex Permian Operating LLC
P-5 Number: P-12345
API Number: 42-371-30001
Lease Name: Heritage A
Well Number: 1H
County:     Pecos County
District:   08

Dear Operator:

The Groundwater Advisory Unit has reviewed records on file for the above-referenced well
in accordance with 16 Texas Administrative Code (TAC) §3.14.

Based on data obtained from public records, geologic surveys, and water well data on
file with the Texas Department of Licensing and Regulation and other state agencies,
the base of usable quality water (BUQW) for this well has been determined to be at
1,500 feet below the surface.

Pursuant to TAC §3.14(c), the operator is required to ensure that all usable quality
groundwater is protected during well plugging operations.  The applicable general
plugging requirements are set forth in TAC §3.14(c)(1)–(4).

Surface Casing Status:
A review of completion records indicates that surface casing for this well is set to
a depth sufficient to protect the BUQW.  The general plugging requirements of
TAC §3.14(c) apply.

This letter should be retained with the well file and referenced on Form W-3
(Plugging Record) at the time of plugging.

If you have questions, contact the Groundwater Advisory Unit at (512) 463-6770.

Sincerely,

Groundwater Advisory Unit
Oil and Gas Division
Railroad Commission of Texas
P.O. Box 12967, Austin, TX 78711-2967
"""


# ---------------------------------------------------------------------------
# GAU-2 special-case advisory — Rusk County, surface casing does not cover BUQW
# ---------------------------------------------------------------------------
GAU2_UNCOVERED = """\
RAILROAD COMMISSION OF TEXAS
Oil and Gas Division — Groundwater Advisory Unit

                        GROUNDWATER ADVISORY UNIT LETTER

Date:    August 4, 2024
Reference: GAU-2024-08-04-Rusk-09915

Operator:   East Texas Energy Partners LP
P-5 Number: P-67890
API Number: 42-401-12345
Lease Name: Cartwright B
Well Number: 3
County:     Rusk County
District:   06

Dear Operator:

The Groundwater Advisory Unit has reviewed records on file for the above-referenced well
in accordance with 16 Texas Administrative Code (TAC) §3.14.

The base of usable quality water (BUQW) for this well has been determined to be at
800 feet below the surface.

SPECIAL CASE — SURFACE CASING DOES NOT COVER BUQW:

A review of completion records indicates that the surface casing for this well does not
cover the base of usable quality water.  The surface casing record on file shows the
casing shoe set at approximately 620 feet, which is shallower than the BUQW depth of
800 feet.  Accordingly, the special plugging requirements of TAC §3.14(d) apply.

Special Plugging Requirements:
1. A cement bridge plug or a mechanical bridge plug followed by cement must be set
   at or immediately below the BUQW depth (800 feet) during well plugging operations.
2. Cement must be placed from the top of the bridge plug to a point not less than
   50 feet above the top of the shallowest hydrocarbon-bearing zone below the BUQW.
3. The operator must comply with all other applicable requirements of TAC §3.14(d).

This letter constitutes notice of special plugging requirements and must be referenced
on Form W-3 at the time of plugging.  Failure to comply may result in enforcement action.

Sincerely,

Groundwater Advisory Unit
Oil and Gas Division
Railroad Commission of Texas
"""


# ---------------------------------------------------------------------------
# GAU-1 with comma-formatted depth — Crane County
# ---------------------------------------------------------------------------
GAU1_COMMA_DEPTH = """\
RAILROAD COMMISSION OF TEXAS
Groundwater Advisory Unit

Reference: GAU-2024-05-19-Crane-08812

Date: May 19, 2024

Operator: Lone Star Basin Resources Inc.
API: 42-103-77001
County: Crane County

This letter advises that the base of usable quality water for the
above-referenced well has been determined to be at 1,200 feet below
the surface.

The general plugging requirements of TAC §3.14(c) apply.
Surface casing covers the BUQW; no special case requirements.

Reference this letter on Form W-3 at time of plugging.

Groundwater Advisory Unit — Railroad Commission of Texas
"""


# ---------------------------------------------------------------------------
# GAU-1 with alternate phrasing ("BUQW depth:")
# ---------------------------------------------------------------------------
GAU1_EXPLICIT_FIELD = """\
RAILROAD COMMISSION OF TEXAS
Groundwater Advisory Unit

Letter No.: GAU-2024-09-22-Throck-00301
Date: September 22, 2024

Well: Throckmorton County — API 42-461-00042
Operator: Lone Peak Royalties LLC

BUQW Depth: 600 feet

The above BUQW depth was determined from public groundwater records and geologic
surveys.  The general plugging requirements of 16 TAC §3.14(c) apply.
Surface casing adequately covers the zone of usable quality water.

Groundwater Advisory Unit — Oil and Gas Division
"""


# ---------------------------------------------------------------------------
# GAU-2 with TAC §3.14(d) explicit citation — Midland County
# ---------------------------------------------------------------------------
GAU2_TAC_CITATION = """\
RAILROAD COMMISSION OF TEXAS
Oil and Gas Division — Groundwater Advisory Unit

Reference: GAU-2024-02-28-Midland-44218
Date: February 28, 2024

Operator: Permian Sundown LLC
API Number: 42-329-55555
County: Midland County

BUQW depth for this well: 1,200 feet.

The surface casing for this well does not extend to the base of usable quality
water.  TAC §3.14(d) special-case plugging requirements apply.

A cement bridge plug must be set at 1,200 feet prior to plugging operations
proceeding above that depth.

Groundwater Advisory Unit
Railroad Commission of Texas
"""


# ---------------------------------------------------------------------------
# Edge case: scanned letter — very little text extracted
# ---------------------------------------------------------------------------
GAU_SCAN_STUB = """\
RAILROAD COMMISSION OF TEXAS
[Image — OCR required]
"""


# ---------------------------------------------------------------------------
# Edge case: depth out of expected range (likely parse error)
# ---------------------------------------------------------------------------
GAU_WEIRD_DEPTH = """\
RAILROAD COMMISSION OF TEXAS
Groundwater Advisory Unit

Reference: GAU-2025-01-01-Test-99999
Date: January 1, 2025

Operator: Test Operator LLC
API: 42-000-00001
County: Travis County

The base of usable quality water has been determined to be at 15 feet below
the surface.  General plugging requirements apply.
"""


# ---------------------------------------------------------------------------
# Real RRC Form GW-2 "Groundwater Protection Determination" format
# (as issued by the GAU since at least 2014 — structured form, not a prose letter)
# This format differs from the synthetic letters above in three key ways:
#   1. Reference is "GAU Number: NNNNNN" (bare 6-digit integer)
#   2. Date is "DD Month YYYY" (day-first, e.g. "25 September 2018")
#   3. County is "County: POLK" (label before value)
#   4. BUQW phrasing: "estimated to occur at a depth of NNNN feet below the land surface"
# ---------------------------------------------------------------------------
GAU_GW2_FORMAT = """\
GROUNDWATER PROTECTION DETERMINATION                      Form GW-2
Groundwater Advisory Unit

Date Issued:  25 September 2018       GAU Number:  208803

Attention:    DAVIS SOUTHERN          API Number:
              1221 MCKINNEY STE 3100  County:      POLK
              HOUSTON, TX 77010       Lease Name:  BSM Wildman
Operator No.: 206081                  Lease Number:
                                      Well Number: 1
                                      Total Vertical Depth: 6000
                                      Latitude: 30.565281
                                      Longitude: -94.660533
                                      Datum: NAD27

Purpose:      New Production Well
Location:     Survey-THOMAS, M.; Abstract-75

To protect usable-quality groundwater at this location, the Groundwater
Advisory Unit of the Railroad Commission of Texas recommends:

The base of usable-quality water that must be protected is estimated to
occur at a depth of 1550 feet below the land surface.  Moreover, the
interval from the land surface to a depth of 450 feet and the fresh water
contained in the Jasper from a depth of 800 feet to 1150 feet must be
isolated from water in overlying and underlying beds.

This recommendation is applicable to all wells within a radius of 600 feet
of this location.

Groundwater Advisory Unit, Oil and Gas Division
Form GW-2 Rev. 02/2014  P.O. Box 12967 Austin, Texas 78771-2967  512-463-2741
"""


# ---------------------------------------------------------------------------
# Convenience mapping: api_number -> letter text
# ---------------------------------------------------------------------------
LETTER_BY_API: dict[str, str] = {
    "42-371-30001": GAU1_STANDARD,
    "42-401-12345": GAU2_UNCOVERED,
    "42-103-77001": GAU1_COMMA_DEPTH,
    "42-461-00042": GAU1_EXPLICIT_FIELD,
    "42-329-55555": GAU2_TAC_CITATION,
    # Real Form GW-2 format (Polk County / BSM Wildman; no API# in letter)
    "00-397-00001": GAU_GW2_FORMAT,
}

EXPECTED_BUQW_BY_API: dict[str, float] = {
    "42-371-30001": 1500.0,
    "42-401-12345": 800.0,
    "42-103-77001": 1200.0,
    "42-461-00042": 600.0,
    "42-329-55555": 1200.0,
    "00-397-00001": 1550.0,
}

EXPECTED_REF_BY_API: dict[str, str] = {
    "42-371-30001": "GAU-2024-03-12-Pecos-21874",
    "42-401-12345": "GAU-2024-08-04-Rusk-09915",
    "42-103-77001": "GAU-2024-05-19-Crane-08812",
    "42-461-00042": "GAU-2024-09-22-Throck-00301",
    "42-329-55555": "GAU-2024-02-28-Midland-44218",
    "00-397-00001": "GAU-208803",
}
