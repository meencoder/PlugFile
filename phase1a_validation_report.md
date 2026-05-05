# Phase 1A Validation Report

Output of `scripts/validate_phase1a.py`. Every cement volume below 
comes from `wellplug.cement_volume` (deterministic, unit-tested) 
and every plug placement from `wellplug.tac_3_14.compute_plug_program`.

Five representative Texas wellbore geometries were exercised; one 
triggers the `general` rule path, one triggers the BUQW-uncovered 
`special_buqw_uncovered` path, and the remaining three exercise 
edge cases inside the general path.

## Summary

| Fixture | Plugs | Rule path(s) | Total sacks |
|---------|------:|--------------|------------:|
| permian_deep_gas | 7 | general | 75.0 |
| east_texas_shallow_oil | 6 | general | 41.2 |
| buqw_uncovered_legacy | 4 | general, special_buqw_uncovered | 184.6 |
| no_surface_casing_legacy | 4 | general, special_buqw_uncovered | 183.1 |
| multi_zone_producer | 8 | general | 98.4 |

---

### permian_deep_gas

- **API**: 42-371-30001  |  **Operator**: Apex Permian Operating LLC
- **Lease/Well**: Heritage A #1H, Pecos County
- **TD**: 10500 ft  |  **BUQW**: 1500 ft (GAU letter dated 2024-03-12)
- **Surface casing**: 13.375" set @ 1800 ft (ToC 0)
- **Notes**: Modern Permian deep gas; surface casing protects BUQW (general rule).


**Rule path(s) taken**: `general`

| # | Top (ft) | Bottom (ft) | Bore | Dia (in) | Excess | ft^3 | bbl | sacks | Cite | Path |
|---|---------:|------------:|------|---------:|-------:|-----:|----:|------:|------|------|
| 1 | 0 | 50 | inside_casing | 4.892 | 0% | 6.53 | 1.16 | 6.2 | TAC §3.14(d)(6) | general |
| 2 | 1450 | 1550 | inside_casing | 4.892 | 0% | 13.05 | 2.32 | 12.3 | TAC §3.14(d)(2) [general] | general |
| 3 | 1750 | 1850 | inside_casing | 4.892 | 0% | 13.05 | 2.32 | 12.3 | TAC §3.14(d)(1) | general |
| 4 | 6450 | 6550 | inside_casing | 4.892 | 0% | 13.05 | 2.32 | 12.3 | TAC §3.14(d)(1) | general |
| 5 | 10100 | 10250 | inside_casing | 4.892 | 0% | 19.58 | 3.49 | 18.5 | TAC §3.14(d)(3) | general |
| 6 | 10250 | 10300 | inside_casing | 4.892 | 0% | 6.53 | 1.16 | 6.2 | TAC §3.14(d)(1) | general |
| 7 | 10300 | 10350 | open_hole | 4.750 | 25% | 7.69 | 1.37 | 7.3 | TAC §3.14(d)(1) | general |

**Totals**: 79.48 ft^3  |  14.16 bbl  |  75.0 sacks  (7 plugs)

---

### east_texas_shallow_oil

- **API**: 42-401-12345  |  **Operator**: Pine Belt Energy Inc.
- **Lease/Well**: Whitfield #3, Rusk County
- **TD**: 4500 ft  |  **BUQW**: 800 ft (GAU letter dated 2024-08-04)
- **Surface casing**: 8.625" set @ 1100 ft (ToC 0)
- **Notes**: Typical East Texas shallow oil; clean general-rule case.


**Rule path(s) taken**: `general`

| # | Top (ft) | Bottom (ft) | Bore | Dia (in) | Excess | ft^3 | bbl | sacks | Cite | Path |
|---|---------:|------------:|------|---------:|-------:|-----:|----:|------:|------|------|
| 1 | 0 | 50 | inside_casing | 4.052 | 0% | 4.48 | 0.80 | 4.2 | TAC §3.14(d)(6) | general |
| 2 | 750 | 850 | inside_casing | 4.052 | 0% | 8.96 | 1.59 | 8.4 | TAC §3.14(d)(2) [general] | general |
| 3 | 1050 | 1150 | inside_casing | 4.052 | 0% | 8.96 | 1.59 | 8.4 | TAC §3.14(d)(1) | general |
| 4 | 4200 | 4330 | inside_casing | 4.052 | 0% | 11.64 | 2.07 | 11.0 | TAC §3.14(d)(3) | general |
| 5 | 4350 | 4400 | inside_casing | 4.052 | 0% | 4.48 | 0.80 | 4.2 | TAC §3.14(d)(1) | general |
| 6 | 4400 | 4450 | open_hole | 3.875 | 25% | 5.12 | 0.91 | 4.8 | TAC §3.14(d)(1) | general |

**Totals**: 43.63 ft^3  |  7.77 bbl  |  41.2 sacks  (6 plugs)

---

### buqw_uncovered_legacy

- **API**: 42-103-77001  |  **Operator**: Sunset Heritage Wells LLC
- **Lease/Well**: Old Yellowhouse #2, Crane County
- **TD**: 6000 ft  |  **BUQW**: 1200 ft (GAU letter dated 2024-05-19)
- **Surface casing**: 9.625" set @ 800 ft (ToC 0)
- **Notes**: Legacy permitted well: surface casing only to 800 ft, BUQW at 1200 ft. Special-case continuous-column rule must trigger.


**Rule path(s) taken**: `general, special_buqw_uncovered`

| # | Top (ft) | Bottom (ft) | Bore | Dia (in) | Excess | ft^3 | bbl | sacks | Cite | Path |
|---|---------:|------------:|------|---------:|-------:|-----:|----:|------:|------|------|
| 1 | 0 | 1250 | inside_casing | 4.892 | 0% | 163.16 | 29.06 | 153.9 | TAC §3.14 [special case: BUQW not covered by surface casing] | special_buqw_uncovered |
| 2 | 5750 | 5890 | inside_casing | 4.892 | 0% | 18.27 | 3.25 | 17.2 | TAC §3.14(d)(3) | general |
| 3 | 5850 | 5900 | inside_casing | 4.892 | 0% | 6.53 | 1.16 | 6.2 | TAC §3.14(d)(1) | general |
| 4 | 5900 | 5950 | open_hole | 4.750 | 25% | 7.69 | 1.37 | 7.3 | TAC §3.14(d)(1) | general |

**Totals**: 195.65 ft^3  |  34.85 bbl  |  184.6 sacks  (4 plugs)

---

### no_surface_casing_legacy

- **API**: 42-461-00042  |  **Operator**: Estate of J.M. Hardin (Operator of Record)
- **Lease/Well**: Hardin Heirs #A-1, Throckmorton County
- **TD**: 3500 ft  |  **BUQW**: 600 ft (GAU letter dated 2024-09-22)
- **Surface casing**: NONE
- **Notes**: 1950s-vintage well with no surface casing string and production cement starting at 1500 ft. BUQW at 600 ft is unprotected. Special case must trigger.


**Rule path(s) taken**: `general, special_buqw_uncovered`

| # | Top (ft) | Bottom (ft) | Bore | Dia (in) | Excess | ft^3 | bbl | sacks | Cite | Path |
|---|---------:|------------:|------|---------:|-------:|-----:|----:|------:|------|------|
| 1 | 0 | 650 | inside_casing | 6.366 | 0% | 143.67 | 25.59 | 135.5 | TAC §3.14 [special case: BUQW not covered by surface casing] | special_buqw_uncovered |
| 2 | 3250 | 3370 | inside_casing | 6.366 | 0% | 26.52 | 4.72 | 25.0 | TAC §3.14(d)(3) | general |
| 3 | 3350 | 3400 | inside_casing | 6.366 | 0% | 11.05 | 1.97 | 10.4 | TAC §3.14(d)(1) | general |
| 4 | 3400 | 3450 | open_hole | 6.125 | 25% | 12.79 | 2.28 | 12.1 | TAC §3.14(d)(1) | general |

**Totals**: 194.04 ft^3  |  34.56 bbl  |  183.1 sacks  (4 plugs)

---

### multi_zone_producer

- **API**: 42-329-55555  |  **Operator**: Stacked Pay Operating LP
- **Lease/Well**: Spraberry Ranch #7, Midland County
- **TD**: 8000 ft  |  **BUQW**: 1200 ft (GAU letter dated 2024-02-28)
- **Surface casing**: 9.625" set @ 1500 ft (ToC 0)
- **Notes**: Modern stacked-pay producer; three zones, one already abandoned.


**Rule path(s) taken**: `general`

| # | Top (ft) | Bottom (ft) | Bore | Dia (in) | Excess | ft^3 | bbl | sacks | Cite | Path |
|---|---------:|------------:|------|---------:|-------:|-----:|----:|------:|------|------|
| 1 | 0 | 50 | inside_casing | 4.892 | 0% | 6.53 | 1.16 | 6.2 | TAC §3.14(d)(6) | general |
| 2 | 1150 | 1250 | inside_casing | 4.892 | 0% | 13.05 | 2.32 | 12.3 | TAC §3.14(d)(2) [general] | general |
| 3 | 1450 | 1550 | inside_casing | 4.892 | 0% | 13.05 | 2.32 | 12.3 | TAC §3.14(d)(1) | general |
| 4 | 6850 | 7000 | inside_casing | 4.892 | 0% | 19.58 | 3.49 | 18.5 | TAC §3.14(d)(3) | general |
| 5 | 7300 | 7450 | inside_casing | 4.892 | 0% | 19.58 | 3.49 | 18.5 | TAC §3.14(d)(3) | general |
| 6 | 7650 | 7790 | inside_casing | 4.892 | 0% | 18.27 | 3.25 | 17.2 | TAC §3.14(d)(3) | general |
| 7 | 7850 | 7900 | inside_casing | 4.892 | 0% | 6.53 | 1.16 | 6.2 | TAC §3.14(d)(1) | general |
| 8 | 7900 | 7950 | open_hole | 4.750 | 25% | 7.69 | 1.37 | 7.3 | TAC §3.14(d)(1) | general |

**Totals**: 104.28 ft^3  |  18.57 bbl  |  98.4 sacks  (8 plugs)

---
