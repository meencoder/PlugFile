# Phase 1C Validation Report

Output of `scripts/validate_phase1c.py`. Demonstrates the surface-
restoration narrative drafter (`wellplug.narrative`) against 8 
golden voice transcripts representing real-style operator dictation.

Each transcript is exercised through:
1. Deterministic regex/keyword slot extraction.
2. Template-based narrative drafting.
3. ExtractionWarning emission for missing required slots.

One transcript is also run through full Phase 1B prefill so the
Section IX narrative populates a complete W-3 form end-to-end.

---
## Summary

| Transcript | API | Filled slots | Warnings |
|------------|-----|-------------:|---------:|
| `permian_modern_full` | `42-371-30001` | 11 | 0 |
| `east_texas_legacy_partial` | `42-401-12345` | 10 | 1 |
| `urban_paved` | `n/a` | 4 | 2 |
| `multi_well_lease` | `42-329-55555` | 11 | 0 |
| `dry_hole_minimal` | `n/a` | 7 | 1 |
| `tank_battery_scope` | `n/a` | 11 | 0 |
| `sensitive_surface` | `n/a` | 10 | 0 |
| `estate_legacy_well` | `42-461-00042` | 11 | 0 |


### permian_modern_full

- API: `42-371-30001`
- Filled slots (11): `access_road_status`, `cap_dimensions`, `cap_type`, `casing_cut_depth_ft`, `cellar_fill_material`, `cellar_filled`, `date_of_work`, `equipment_removed`, `grading_action`, `surface_owner_consent`, `vegetation_action`
- Equipment removed: tubing string, wellhead

**Transcript** (operator dictation):

> Alright, this is the Heritage A number 1H, API 42-371-30001. We finished plugging operations and then on May 4th 2026 we cut the surface casing down about 3 feet below ground level, then we welded a 24 inch by 24 inch by 1/4 inch steel plate on top to cap the wellbore. We backfilled the cellar with native soil. Wellhead and tubing string were removed earlier in the week. Location was re-graded and the disturbed area was re-seeded with native grass. Access road was retained per the surface owner. Surface owner consent on file.

**Drafted Section IX narrative**:

> API 42-371-30001. Surface casing was cut off at 3 feet below ground level and a 24 inch by 24 inch by 1/4 inch steel plate was welded to the cut casing stub to seal the wellbore. The cellar was backfilled with native soil. Tubing string and Wellhead were removed from the location. The location was restored: the location was level; the surface was re seeded. Access road: retained per surface owner. Surface owner consent on file. Work was completed on 2026-05-04.

---

### east_texas_legacy_partial

- API: `42-401-12345`
- Filled slots (10): `cap_dimensions`, `cap_type`, `casing_cut_depth_ft`, `cellar_fill_material`, `cellar_filled`, `date_of_work`, `equipment_removed`, `fencing_status`, `grading_action`, `surface_owner_consent`
- Equipment removed: flowlines, tank battery, wellhead
- Warnings:
  - `warn` `vegetation_action`: Slot not found in transcript; the drafter will use a placeholder. Operator must supply this before filing.

**Transcript** (operator dictation):

> OK so this is the Whitfield #3 in Rusk County. Plugged it on April 22nd 2026. Cut the casing off at 3 feet, welded on a 1/4 inch steel cap. Filled the cellar with caliche we had on site. Wellhead came off, but per the surface owner we left the tank battery and the flowlines in place because they're using them on the next well. Location was leveled. Surface owner declined any vegetation work. Fence was repaired where the rig tore it up. Surface owner permission on file for leaving equipment.

**Drafted Section IX narrative**:

> API 42-401-12345. Surface casing was cut off at 3 feet below ground level and a 1/4 inch steel plate was welded to the cut casing stub to seal the wellbore. The cellar was backfilled with caliche. Flowlines, Tank battery, and Wellhead were removed from the location. The location was restored: the location was leveled. Fencing: repaired. Surface owner declined. Work was completed on 2026-04-22.

---

### urban_paved

- API: `n/a`
- Filled slots (4): `cap_type`, `casing_cut_depth_ft`, `date_of_work`, `grading_action`
- Warnings:
  - `warn` `cellar_filled`: Slot not found in transcript; the drafter will use a placeholder. Operator must supply this before filing.
  - `warn` `vegetation_action`: Slot not found in transcript; the drafter will use a placeholder. Operator must supply this before filing.

**Transcript** (operator dictation):

> We've got the orphan well downtown. Cut the casing 4 feet below the existing concrete pavement. Set a concrete cap on top. Did not fill any cellar - this thing's been paved over for decades. No equipment on the lot. No vegetation done because it's all asphalt. Restored grade to match the adjacent pavement. Date of work was 2026-03-18.

**Drafted Section IX narrative**:

> Surface casing was cut off at 4 feet below ground level and concrete plate was welded to the cut casing stub to seal the wellbore. The location was restored: the location was restored grade. Work was completed on 2026-03-18.

---

### multi_well_lease

- API: `42-329-55555`
- Filled slots (11): `access_road_status`, `cap_dimensions`, `cap_type`, `casing_cut_depth_ft`, `cellar_fill_material`, `cellar_filled`, `date_of_work`, `equipment_removed`, `grading_action`, `surface_owner_consent`, `vegetation_action`
- Equipment removed: pumping unit, rod string, tank battery, tubing string, wellhead

**Transcript** (operator dictation):

> Spraberry Ranch #7. The other wells on this lease are still producing so we kept the access road and the tank battery in place - they're shared. On 2026-05-01 we cut the production casing 3 feet below grade and welded a 24 by 24 by quarter inch steel plate. Cellar filled with caliche. Pulled the wellhead, tubing string, and rod string. Pumping unit was removed and hauled off to the yard. Re-seeded with native grass. Re-graded the disturbed pad. Access road was retained. Surface owner approval received.

**Drafted Section IX narrative**:

> API 42-329-55555. Surface casing was cut off at 3 feet below ground level and a 24 by 24 by quarter inch steel plate was welded to the cut casing stub to seal the wellbore. The cellar was backfilled with caliche. Pumping unit, Rod string, Tank battery, Tubing string, and Wellhead were removed from the location. The location was restored: the location was re graded; the surface was re seeded. Access road: retained per surface owner. Surface owner approval received. Work was completed on 2026-05-01.

---

### dry_hole_minimal

- API: `n/a`
- Filled slots (7): `access_road_status`, `cap_type`, `casing_cut_depth_ft`, `date_of_work`, `fencing_status`, `grading_action`, `vegetation_action`
- Warnings:
  - `warn` `cellar_filled`: Slot not found in transcript; the drafter will use a placeholder. Operator must supply this before filing.

**Transcript** (operator dictation):

> Dry hole, P&A'd same day as TD reached on 2026-02-09. Never produced. Cut the casing 3 feet below ground, welded on a steel plate cap. No cellar - this was a single string completion. Re-graded the pad. Re-seeded the disturbed area with the wildflower mix per the surface owner request. Access road removed. Fence was removed.

**Drafted Section IX narrative**:

> Surface casing was cut off at 3 feet below ground level and steel plate was welded to the cut casing stub to seal the wellbore. The location was restored: the location was re graded; the surface was re seeded. Access road: removed. Fencing: removed. Work was completed on 2026-02-09.

---

### tank_battery_scope

- API: `n/a`
- Filled slots (11): `access_road_status`, `cap_dimensions`, `cap_type`, `casing_cut_depth_ft`, `cellar_fill_material`, `cellar_filled`, `date_of_work`, `equipment_removed`, `fencing_status`, `grading_action`, `vegetation_action`
- Equipment removed: flowlines, heater treater, pumping unit, rod string, separator, tank battery, tubing string, wellhead

**Transcript** (operator dictation):

> Big project on this one. We removed the wellhead, the tubing string, the rod string, the pumping unit, the separator, the heater treater, the entire tank battery, and all the flowlines. Hauled it all off. Cut the casing 3 feet below ground, welded on a 1/4 inch steel plate. Filled the cellar with native soil. Re-graded the pad. Re-seeded with native grass. Access road was removed. Fence retained per surface owner. Date 2026-04-15.

**Drafted Section IX narrative**:

> Surface casing was cut off at 3 feet below ground level and a 1/4 inch steel plate was welded to the cut casing stub to seal the wellbore. The cellar was backfilled with native soil. Flowlines, Heater treater, Pumping unit, Rod string, Separator, Tank battery, Tubing string, and Wellhead were removed from the location. The location was restored: the location was re graded; the surface was re seeded. Access road: removed. Fencing: retained. Work was completed on 2026-04-15.

---

### sensitive_surface

- API: `n/a`
- Filled slots (10): `access_road_status`, `cap_type`, `casing_cut_depth_ft`, `cellar_filled`, `date_of_work`, `fencing_status`, `grading_action`, `sensitive_surface_notes`, `surface_owner_consent`, `vegetation_action`

**Transcript** (operator dictation):

> This well is adjacent to a wetlands area so we coordinated with Texas Parks and Wildlife. Did the work on 2026-04-30. Cut casing 3 feet below grade, welded a steel plate cap on top. No cellar fill needed - it had already been graded out. Re-seeded with the approved native riparian seed mix. Access road removed. Fence retained. Surface owner consent granted with environmental conditions documented separately.

**Drafted Section IX narrative**:

> Surface casing was cut off at 3 feet below ground level and steel plate was welded to the cut casing stub to seal the wellbore. The cellar was backfilled with native soil. The location was restored: the location was graded; the surface was re seeded. Access road: removed. Fencing: retained. Note: location includes wetlands — work performed under applicable regulatory restrictions. Surface owner consent granted. Work was completed on 2026-04-30.

---

### estate_legacy_well

- API: `42-461-00042`
- Filled slots (11): `access_road_status`, `cap_dimensions`, `cap_type`, `casing_cut_depth_ft`, `cellar_fill_material`, `cellar_filled`, `date_of_work`, `equipment_removed`, `fencing_status`, `grading_action`, `vegetation_action`
- Equipment removed: tank battery, wellhead

**Transcript** (operator dictation):

> Hardin Heirs A-1 in Throckmorton. This is one of the orphan wells we picked up. Plugged on 2026-03-25. Cut surface casing 3 feet below ground level. Welded a 24 by 24 by quarter inch steel plate. Cellar was filled with native soil. Wellhead removed. No tank battery - it was scrapped years ago. Re-graded what we could. Re-seeded with native grass. Access road was abandoned, the surface owner moved away. Fence was removed - what little was left of it.

**Drafted Section IX narrative**:

> API 42-461-00042. Surface casing was cut off at 3 feet below ground level and a 24 by 24 by quarter inch steel plate was welded to the cut casing stub to seal the wellbore. The cellar was backfilled with native soil. Tank battery and Wellhead were removed from the location. The location was restored: the location was level; the surface was re seeded. Access road: was abandoned. Fencing: removed. Work was completed on 2026-03-25.

---

## End-to-end pipeline demo

For API `42-371-30001` (a Phase 1B fixture), the full pipeline runs:

  `prefill_w3_with_mock(api)` -> populates Sections I-VIII -> `transcript_to_narrative(...)` -> populates Section IX

- Lease/Well: **Heritage A #1H**
- Plugs computed: **7**
- Missing required after pipeline: `(none)`

**Section IX narrative**:

> API 42-371-30001, the Heritage A #1H, in Pecos County, Texas. Surface casing was cut off at 3 feet below ground level and a 24 inch by 24 inch by 1/4 inch steel plate was welded to the cut casing stub to seal the wellbore. The cellar was backfilled with native soil. Tubing string and Wellhead were removed from the location. The location was restored: the location was level; the surface was re seeded. Access road: retained per surface owner. Surface owner consent on file. Work was completed on 2026-05-04.
