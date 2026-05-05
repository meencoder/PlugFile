# Phase 1B Validation Report

Output of `scripts/validate_phase1b.py`. Demonstrates:

1. Authoritative-source pre-fill across the 5 fixture APIs.
2. Per-source field-fill coverage.
3. Conflict detection when operator narrative disagrees with
   authoritative sources (warn-and-flag policy).
4. Section VIII (computed plug record) regression-equivalent to
   Phase 1A output.

---

## Summary

| API | Lease / Well | Plugs | Rule path(s) | Missing required |
|-----|--------------|------:|--------------|-----------------:|
| 42-103-77001 | Old Yellowhouse #2 | 4 | general, special_buqw_uncovered | 0 |
| 42-329-55555 | Spraberry Ranch #7 | 8 | general | 0 |
| 42-371-30001 | Heritage A #1H | 7 | general | 0 |
| 42-401-12345 | Whitfield #3 | 6 | general | 0 |
| 42-461-00042 | Hardin Heirs #A-1 | 4 | general, special_buqw_uncovered | 0 |


JSON Schema exported to `schemas/w3.schema.json` (16395 bytes).

### API 42-103-77001 -- Old Yellowhouse #2

- Operator: Sunset Heritage Wells LLC (P-5 778899)
- County / District: Crane / 7C
- Field: McCamey, North
- TD: 6000 ft  |  BUQW: 1200 ft  |  BUQW protected: False
- Plug program rule paths: `['general', 'special_buqw_uncovered']`
- Plug count: **4**

**Field-fill coverage by source-of-truth**

| Source | Filled | Total |
|--------|-------:|------:|
| `computed` | 3 | 3 |
| `gau_letter` | 2 | 2 |
| `operator_certification` | 3 | 4 |
| `operator_input` | 1 | 2 |
| `operator_observed` | 0 | 2 |
| `rrc_completion_record` | 5 | 5 |
| `rrc_operator_db` | 3 | 3 |
| `rrc_well_lookup` | 12 | 12 |

**Conflict-detection demo** (operator passed county='Wrong County'):

- `warn`: `county`: operator=`Wrong County` vs `rrc_well_lookup`=`Crane`

---

### API 42-329-55555 -- Spraberry Ranch #7

- Operator: Stacked Pay Operating LP (P-5 224488)
- County / District: Midland / 08
- Field: Spraberry (Trend Area)
- TD: 8000 ft  |  BUQW: 1200 ft  |  BUQW protected: True
- Plug program rule paths: `['general']`
- Plug count: **8**

**Field-fill coverage by source-of-truth**

| Source | Filled | Total |
|--------|-------:|------:|
| `computed` | 3 | 3 |
| `gau_letter` | 2 | 2 |
| `operator_certification` | 3 | 4 |
| `operator_input` | 1 | 2 |
| `operator_observed` | 0 | 2 |
| `rrc_completion_record` | 5 | 5 |
| `rrc_operator_db` | 3 | 3 |
| `rrc_well_lookup` | 12 | 12 |

**Conflict-detection demo** (operator passed county='Wrong County'):

- `warn`: `county`: operator=`Wrong County` vs `rrc_well_lookup`=`Midland`

---

### API 42-371-30001 -- Heritage A #1H

- Operator: Apex Permian Operating LLC (P-5 112233)
- County / District: Pecos / 08
- Field: Spraberry (Trend Area)
- TD: 10500 ft  |  BUQW: 1500 ft  |  BUQW protected: True
- Plug program rule paths: `['general']`
- Plug count: **7**

**Field-fill coverage by source-of-truth**

| Source | Filled | Total |
|--------|-------:|------:|
| `computed` | 3 | 3 |
| `gau_letter` | 2 | 2 |
| `operator_certification` | 3 | 4 |
| `operator_input` | 1 | 2 |
| `operator_observed` | 0 | 2 |
| `rrc_completion_record` | 5 | 5 |
| `rrc_operator_db` | 3 | 3 |
| `rrc_well_lookup` | 12 | 12 |

**Conflict-detection demo** (operator passed county='Wrong County'):

- `warn`: `county`: operator=`Wrong County` vs `rrc_well_lookup`=`Pecos`

---

### API 42-401-12345 -- Whitfield #3

- Operator: Pine Belt Energy Inc. (P-5 445566)
- County / District: Rusk / 06
- Field: East Texas
- TD: 4500 ft  |  BUQW: 800 ft  |  BUQW protected: True
- Plug program rule paths: `['general']`
- Plug count: **6**

**Field-fill coverage by source-of-truth**

| Source | Filled | Total |
|--------|-------:|------:|
| `computed` | 3 | 3 |
| `gau_letter` | 2 | 2 |
| `operator_certification` | 3 | 4 |
| `operator_input` | 1 | 2 |
| `operator_observed` | 0 | 2 |
| `rrc_completion_record` | 5 | 5 |
| `rrc_operator_db` | 3 | 3 |
| `rrc_well_lookup` | 12 | 12 |

**Conflict-detection demo** (operator passed county='Wrong County'):

- `warn`: `county`: operator=`Wrong County` vs `rrc_well_lookup`=`Rusk`

---

### API 42-461-00042 -- Hardin Heirs #A-1

- Operator: Estate of J.M. Hardin (Operator of Record) (P-5 001234)
- County / District: Throckmorton / 7B
- Field: Throckmorton, North
- TD: 3500 ft  |  BUQW: 600 ft  |  BUQW protected: False
- Plug program rule paths: `['general', 'special_buqw_uncovered']`
- Plug count: **4**

**Field-fill coverage by source-of-truth**

| Source | Filled | Total |
|--------|-------:|------:|
| `computed` | 3 | 3 |
| `gau_letter` | 2 | 2 |
| `operator_certification` | 3 | 4 |
| `operator_input` | 1 | 2 |
| `operator_observed` | 0 | 2 |
| `rrc_completion_record` | 5 | 5 |
| `rrc_operator_db` | 3 | 3 |
| `rrc_well_lookup` | 12 | 12 |

**Conflict-detection demo** (operator passed county='Wrong County'):

- `warn`: `county`: operator=`Wrong County` vs `rrc_well_lookup`=`Throckmorton`

---
