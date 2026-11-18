# Museum field notes

Staff can inventory scanned cards, transcribe selected notes, correct readings, and browse a collection by collector, species or collection number. Start with the JPEGs in the collector folders. An existing spreadsheet is optional.

Each scan starts as one provisional note. A note keeps one permanent link even when its species or numbers change. One page can describe several specimens at different places. Each number and locality can point to its own passage in the complete page transcription. Missing species and undated notes stay in the catalogue.

## Start in PowerShell

Use Python 3.12 or newer. The tested environment used Python 3.14.2 and Node 24.22.1. Node is needed for viewer tests and the synthetic preview. Run commands from this checkout. PowerShell 7 is recommended for Unicode text through pipelines.

```powershell
Set-Location 'C:\Users\x5769\Documents\GitHub\museum-field-note-transcriber'
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
$py = '.\.venv\Scripts\python.exe'
& $py -m pip install -r requirements.txt
$env:PYTHONUTF8 = '1'
$scans = 'G:\My Drive\Field Notes'
& $py -m fieldnotes dry-run --input $scans
& $py -m fieldnotes inventory --input $scans
& $py -m fieldnotes show --collector Carriker
```

The dry run reads the files, builds complete requests in memory, and prints readiness. It needs no key and creates no journal, lock, quota reservation or report. Inventory saves stable IDs, relative paths, original hashes, dimensions, and issues under `local/collection`. It also writes one readable report per note and a spreadsheet catalogue under `local/exports`. Both operations open originals for reading only. Rerun inventory to discover additions. To retain the identity of an externally moved scan, reconcile its path **before** inventorying its new location. See [grouping and path changes](docs/review.md).

## Find and read a note

```powershell
& $py -m fieldnotes show --mode species --sort species
& $py -m fieldnotes show --mode species --collector Carriker --query 'March'
& $py -m fieldnotes show --query '0012'
$listing = & $py -m fieldnotes show --collector Carriker | ConvertFrom-Json
$note = $listing.records[0].note_id
& $py -m fieldnotes show --note $note
& $py -m fieldnotes export
```

Choose the intended row before using its ID for transcription. The examples use the first listed note for inspection. The collection number and species appear after a reading supplies them. Folder names are provisional collector attribution. Search covers every number, source name, approved alias, locality, date text, and saved transcription. Number order has no chronological meaning. The same number can occur in different collector folders.

Open `local/exports/catalogue.csv` to browse all records. Import identifiers as **Text** to retain leading zeros. Open `local/exports/readable/<note_id>.txt` for a page-by-page reading, or `details/<note_id>.txt` for the evidence and provenance. Rebuild the reports and viewer JSON with `export`, even when the scan drive is disconnected. See [outputs and publication](docs/outputs.md).

## Transcribe when authorized

An authorized transcription sends the selected images, prompt, folder/filename hints, approved name context and any selected handwriting profile to Gemini. These requests can incur charges. Set up a private key and check the account's shared allocation first. The defaults use `gemini-3.5-flash-lite`, temperature `1.0`, high thinking, one request per minute, and a local daily allocation of 25 attempts. See [configuration and credentials](docs/configuration.md).

```powershell
New-Item -ItemType Directory -Force local | Out-Null
if (-not (Test-Path 'local/config.json')) { Copy-Item docs/config.example.json local/config.json }
# If using a key file, copy the empty example once, then edit .env privately.
if (-not (Test-Path '.env')) { Copy-Item .env.example .env }
# Choose one command for the intended scope.
& $py -m fieldnotes --config local/config.json transcribe --note $note --env-file .env
& $py -m fieldnotes --config local/config.json transcribe --pending --collector Carriker --env-file .env
& $py -m fieldnotes --config local/config.json transcribe --collector Carriker --env-file .env
& $py -m fieldnotes --config local/config.json transcribe --number '0012' --collector Carriker --env-file .env
& $py -m fieldnotes --config local/config.json transcribe --all --env-file .env
& $py -m fieldnotes --config local/config.json transcribe --note $note --fresh --env-file .env
& $py -m fieldnotes usage --run latest
& $py -m fieldnotes usage
```

Use **`--pending` to continue** after a pause. It skips current complete records of any age. A regular selection can reuse a complete exact request for 48 hours. An older regular selection or an explicit `--fresh` can spend again. A failed export can be rebuilt with `export` after the result has been saved. An unknown interrupted service outcome needs inspection before an explicit retry. See [reading and rerunning](docs/transcription.md).

## Correct and share readings

The saved service result, human corrections, and review decisions have separate histories. Completing a reading leaves metadata and transcription unreviewed. A correction updates titles and browse groups when reports are regenerated. Staff can approve a number while leaving the page text under review.

```powershell
& $py -m fieldnotes review-template --note $note | Set-Content local/review.json -Encoding utf8
# Edit local/review.json against the scans before applying it.
& $py -m fieldnotes review --file local/review.json
& $py -m fieldnotes alias --file local/alias.json
& $py -m fieldnotes group --file local/grouping.json
& $py -m fieldnotes reconcile-paths --file local/paths.json
& $py -m fieldnotes export
```

These are independent operations, each using a staff-prepared file. The review guide gives working file shapes, replacement rules and examples. [Human review, aliases and grouping](docs/review.md) · [Transcription record schema](docs/schema.md) · [Handwriting profiles](docs/handwriting.md)

The read-only Apps Script viewer ships with blank Drive settings. Staff can try its collector and species views using invented cards on this computer.

```powershell
& $py scripts/make_demo.py
node scripts/preview.cjs
```

Open [the local synthetic preview](http://127.0.0.1:8783/) while the command is running. Press Ctrl+C to stop it. Installing a Drive viewer or publishing reader files is a separate, explicit operation. [Viewer installation and access](apps_script/viewer/README.md) · [Managed publication](docs/outputs.md)

For maintainers, see [offline tests and visual checks](docs/testing.md) and [project handoff, origins and collection inspection](docs/PROJECT_HANDOFF.md).
