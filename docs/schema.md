# Record schema, version 1

The inventory, accepted document, journal and viewer export are distinct structures. The executable document contract lives in [schema.py](../fieldnotes/schema.py). The prompt uses the same skeleton as the validator. All text is UTF-8. JSON null means unknown or absent. Empty arrays mean there are no supplied items of that type.

| Layer | Stored fields and identity |
| --- | --- |
| Inventory | `collection_id`, bound `input_root`, `images`, `notes`, `overrides`, directory-level `issues`. An image has `img_` plus 32 hex digits, original filename, exact relative path, folder, collector folder, SHA-256, bytes, original pixel dimensions, status and warnings. |
| Archival note | `note_` plus 32 hex digits, ordered `image_ids`, `group_key`, active/retired flag, filename/folder hints, separate discovery and grouping status. UUIDs are allocated at discovery and retained in the store. Numbers, taxa and reviewer spellings never form the ID. |
| Result | A `rev_` ID, note ID, request fingerprint, timestamp with zone, attempt IDs, requested and returned model information, raw text, parsed document where available, errors and review reasons. The selected revision survives a restart or cache reuse. |
| Current record | The selected result plus applicable human corrections, their history, stale reviews, source/review hashes, execution, metadata review, transcription review and derived catalogue. |
| Journal | One JSON object per UTF-8 line. Each has `schema_version`, `application: "fieldnotes"`, `event_id`, `at`, `kind` and `data`. Inventory snapshots, attempts, revisions, selections, profiles, authorities, human reviews and publication ownership append to the same journal. Raw responses and submitted JPEG bytes are separate content-addressed blobs. |

## Transcription document

The top level contains `schema_version`, `pages`, `metadata`, `entries`, five repeated field arrays, `summary`, `notes` and `translations`.

- **Pages** have `image_id`, `status`, complete `text`, and `annotations` containing `kind` and `text`. Page IDs must exactly match the ordered input manifest. The manifest supplies the original path and filename for headings. Annotation kinds are marginal, later, signature, pagination, mark or unknown.
- **Metadata** has collector as written, language, document type and physical hand in `collector`, `language`, `document_type`, `physical_hand`. Each is a field object. Folder attribution remains in inventory hints.
- **Entries** have a local `entry_id`, `image_id`, a brief passage label and evidence. Entries divide one page into meaningful sections. Page text is stored once.
- **Field objects** have `value` (as written), `normalized` (search form), `certainty` (explicit, inferred, uncertain, unknown), and `evidence`. A populated value should have evidence containing an image ID and a short verbatim `quote` or precise `location`. An optional `entry_id` locates the passage. Dangling references fail validation. Missing evidence or a nonverbatim quotation calls for review. A service response cannot assign approved authority IDs.
- **Repeated fields** add `entry_id`, or null for note-wide context. Their type-specific fields are listed below.

| Array | Fields and interpretation |
| --- | --- |
| `identifiers` | `number_type` collection/specimen/unknown, `namespace` (supported collector context or null). Every value is a string. Preserve `0012`, `12a`, ranges, prefixes, alternatives and uncertainty. Counts, dates and elevations belong in other fields. |
| `taxa` | `name_type` scientific/vernacular/unknown, `rank` species/subspecies/genus/unknown, `role` principal/incidental/comparison, boolean `source_uncertain`, optional shared `alternative_group`. Keep each alternative, the writer's spelling, and any later reviewed identity. |
| `localities` | One place reading per occurrence, attached to its own entry/evidence. |
| `dates` | As-written reading, `precision` and `event`. Event can describe collection, observation, breeding, annotation or unknown. Precision supports day, month, month_only, year, range, partial, ambiguous and unknown. |
| `observations` | `kind` describes habitat, elevation, sex/age, breeding, measurement, behavior or other material. Preserve values, original units and symbols. |

Usable search dates take the forms `YYYY-MM-DD`, `YYYY-MM`, `YYYY`, `--MM` or `endpoint/endpoint`. A four-digit year must occur in the written date before it can supply a normalized year. Month/day precision requires recognizable components and a valid calendar date. Named months and unambiguous numeric forms are supported. Unrecognized or ambiguous date forms stay searchable as written. Rejected normalization proposals remain in the canonical document and review history. March alone cannot supply a year or a collection date.

The summary is an interpretive string. Notes are a separate array of strings. Each optional translation specifies its image ID, language and text. Neither translation nor summary substitutes for page text.

## Catalogue and review

Discovery (`ready`/`unavailable`) and grouping (`provisional`, `reviewed`, `needs_review`, `retired`) are independent of execution. Execution includes unprocessed, blocked, complete, failed, paused, interrupted and stale. Metadata review and transcription review each start unreviewed and can move independently to in_progress or approved.

Default titles use principal taxon readings and all as-written numbers. Missing values display “Unknown species” or “Number not recorded.” Clean ASCII digits sort numerically first, then numeric values with letter suffixes, then other strings and ranges in natural order, with missing values last. Display strings retain zeros and case. Multi-number notes sort by their lowest key, full sorted number list, then stable ID. Species sorting uses the display name and number order. No order here represents collection chronology.

Species groups initially match case-folded source names with whitespace normalized and rank retained. Explicit approved aliases can join names of the same rank. Alternative identifications remain flagged. Group counts count distinct notes in each group, and the overall count counts each note once. A comparison taxon can be searchable without becoming the title. Rebuilding this projection needs only the local journal.
