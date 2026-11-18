# Reading files, catalogue and publication

The default source of truth is `local/collection/journal.jsonl` with its sibling `blobs/` directory. Back them up together, along with the field-note quota file if you plan to resume requests. Keep private mappings, staff patches and profiles under `local/`. A journal or technical export may contain exact prompts, private context, raw text and reviewer information.

Run `& $py -m fieldnotes export` to rebuild the current collection under `local/exports`. This reads saved versions and review decisions, including retained records with unavailable scans. It does not need a service key, mounted scan root, or new reading.

| Output | Use |
| --- | --- |
| `readable/note_<id>.txt` | One file for every note, including unavailable or failed records. Whole pages with original path and image ID, catalogue details, summary, notes, translations, states and review reasons. |
| `details/note_<id>.txt` | Staff reading plus selected result, provenance, correction history or available partial response. Follow journal attempt references for original response blobs and other revisions. |
| `combined.txt`, `collectors/collector_<hash>.txt` | Collection and folder readings for active notes, ordered by collection number. The collector filename comes from its folder label. Metadata changes do not rename note files. |
| `records.json` | Versioned inventory, selected canonical/reviewed records and authorities, including unknowns and retired groups. Previous revisions remain in the journal. |
| `catalogue.csv` | One row per note with identity, active flag, folder/display attribution, species and number labels, states, page count, summary and report path. Use related tables for individual readings. |
| `images.csv`, `entries.csv` | Ordered page membership, source properties, image IDs and section labels. Images can also occur in retired group history. |
| `identifiers.csv`, `taxa.csv`, `localities.csv`, `dates.csv`, `observations.csv` | One row per item. Keys are `note_id`, array name and zero-based `item_index`. `entry_id` links the passage, `value` is the source reading, and `details_json` contains type-specific fields. |
| `evidence.csv` | `note_id`, field or array name, item index, image and optional entry ID, quotation or location. `metadata.collector` names a note-wide metadata field. |
| `Field_notes_viewer.json` | Private viewer bundle with relative paths, ordered scans, saved readings, display projections and restricted provenance. Only the viewer's public projection is suitable for an approved public session. |

The UTF-8 CSVs include a byte-order mark and quote multiline fields. Import identifier, namespace, date-as-written and ID columns as **Text**. A spreadsheet may otherwise coerce `0012`, ranges or partial dates. For spreadsheet safety, text beginning with a formula marker or leading control character is prefixed with an apostrophe. Canonical JSON and reading text retain the original characters. Blank CSV cells represent missing values. The comma-separated display label in the main catalogue cannot reconstruct the identifier array.

## Optional managed publication

Ordinary export and transcription write under the local output path. A separate explicit command can copy the active note readers, collector readers, collection reader and viewer JSON into a staff-selected existing destination. Keep the managed destination and local export tree in separate directories. Publication is optional even after a destination has been used. The journal remembers ownership, previous hashes and archives. It never turns on automatic publication.

```powershell
# For a local trial, create a dedicated destination outside the scan tree.
New-Item -ItemType Directory -Force local/publication-trial | Out-Null
& $py -m fieldnotes publish --destination local/publication-trial
# Later, only when the destination and disclosure are authorized:
$destination = 'G:\My Drive\Field Notes'
& $py -m fieldnotes publish --destination $destination
# With verified optional image mappings, add: --mapping local/drive-mapping.json
```

The managed names are `Field_notes/note_<id>.txt`, `Field_notes/collector_<hash>.txt`, `Field_notes_transcriptions.txt` and `Field_notes_viewer.json`. Existing unowned files and externally edited files stop publication. Superseded managed bytes are archived in local store blobs, with the path-to-archive mapping recorded in the pending publication event. Ownership is journalled before writes, each file is replaced atomically, and a completed event records the resulting hashes. After interruption, resolve any external edit and repeat the explicit command with the same store. Back up the store because deleting it also loses ownership evidence.

Managed paths in the scan tree are excluded from later discovery for that store. Scans, unrelated text and other applications' outputs are never adopted. Keep the viewer JSON private even when the web viewer is intended for public use.

Local export refreshes local files. Explicit publication updates the chosen destination. Drive synchronization transfers those saved files under the owner's existing sharing settings. Reloading the viewer reads the current export and checks actual scan bytes. If a note's export changes between loading text and images, reload the note. Updating an Apps Script deployment is needed for script or configuration changes. A data-only update normally needs synchronization and reload. Recheck the configured export file ID if the sync client replaces a Drive item with a new identity.
