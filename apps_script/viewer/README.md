# Field Notes viewer prototype

This directory preserves the earlier Apps Script prototype and its offline tests. The planned public reader will be part of the birds website alongside the egg-slip and correspondence readers. The Drive configuration and deployment details below describe the prototype. See the [website reader decision](../../docs/PROJECT_HANDOFF.md#november-20-website-reader-decision).

The viewer reads one saved export and loads each JPEG on demand from Google Drive. Its search, species groups, reader pages and scan enlargement use saved data. No service key is needed. The checked-in installation is restricted to the configuring user, has blank IDs, and has no deployment URL.

## Try it locally

From the repository root, run these in PowerShell.

```powershell
& .\.venv\Scripts\python.exe scripts/make_demo.py
node scripts/preview.cjs
```

Open [the local preview](http://127.0.0.1:8783/). It serves the actual template and server functions against a simulated Drive containing only the invented fixture. Try searching `12a`, opening the two-page note, enlarging either scan, and returning to species browsing. Ctrl+C stops the preview.

## Historical prototype configuration

1. Prepare the local bundle with `& $py -m fieldnotes export`. The file is `local/exports/Field_notes_viewer.json`. Keep this file private. It can include full prompts, review reasons and partial service text.
2. Place the approved export in a controlled Drive location using the documented publication operation or an authorized file transfer. Identify its actual Drive **file ID**. Identify a staff access-gate file and, for path-based scan lookup, the actual **folder ID** for the Field Notes root containing the collector folders. Use the relevant Drive item's URL to obtain its ID.
3. Create a standalone Apps Script project. Copy this directory's `Code.gs` and `Viewer.html` into files named **Code** and **Viewer** of the corresponding types. Enable the manifest in project settings and copy `appsscript.json`. These are the three installation files. The HTML already embeds the client and styles.
4. In your private project set `SETTINGS.ACCESS_FILE_ID`, `EXPORT_FILE_ID`, and optionally `SCAN_ROOT_FOLDER_ID`. Leave `PUBLIC_MODE: false`. The manifest requests only `drive.readonly` and specifies `USER_ACCESSING` and `MYSELF`. Authorize read access for the intended account. Configure any future restricted multi-user deployment to execute as the accessing user with the intended audience. Each visitor then needs access to the gate, the export and the scans they read.
5. When deployment is authorized, test a known note, an inaccessible scan, and a second account with the expected permissions. Do not infer access from the owner's session. Use the URL assigned to this deployment. Never reuse another collection's deployment URL.

The server rechecks the gate for the page and each restricted RPC. `listFolders` returns lightweight rows without scan bytes or page text. `loadNote` accepts the stable note ID and browse context. `loadImage` accepts only a note ID, an image ID belonging to that note and an export token. The token binds an image request to the bytes of the export that supplied its text.

## Find a catalogue number

Type the digits into Search or use `?number=8420` or `?8420` on the viewer URL. This looks up saved identifiers, including the endpoints and interior of an inclusive range. The results show all matching cards and their as-written numbers. Opening a card highlights the literal number or its written range in the transcription, on the evidence page when identified. The general `?q=` and `?query=` searches also include matches elsewhere in the saved text.

## Resolve a scan

The preferred setup uses one Field Notes root folder ID. For a path such as `Carriker/set1/valley.jpg` the server walks exact child names from that root, one folder at a time. A duplicate folder or filename stops lookup. A missing or invisible child can have the same Drive response. The viewer reports that uncertainty and keeps the transcription visible.

Explicit mappings take precedence for selected images. For each mapped image use its real Drive file ID and the **original** SHA-256 from `images.csv`. This template intentionally contains placeholders. Save the filled file under ignored `local/drive-mapping.json`.

```json
{
  "version": 1,
  "images": {
    "REPLACE_WITH_IMAGE_ID": {
      "file_id": "REPLACE_WITH_ACTUAL_DRIVE_FILE_ID",
      "original_sha256": "REPLACE_WITH_ORIGINAL_SHA256"
    }
  }
}
```

```powershell
& $py -m fieldnotes export --mapping local/drive-mapping.json
```

Supply the same `--mapping` on each export or publication that should use it. An explicit mapping that fails never falls back to a similarly named file. Missing mapping, missing or inaccessible scan, ambiguous path, stale export, changed bytes and absence of transcription have distinct messages. Folder names and source text render as literal text. Original size and SHA-256 must match before image bytes reach the browser.

Export size is limited to 10 MiB. A JPEG is limited to 12 MiB and a note to 24 MiB of scanned files for browser loading. Every page is positioned before scans load, and requests for images run sequentially. The desktop panels show the full image at its own aspect ratio. The reference mobile breakpoint stacks the scan above its text. “Enlarge scan” opens the verified image at natural dimensions in a scrollable dialog.

## Prototype public access model

An owner-executed public deployment uses the owner's Drive permissions. It can disclose private scans and text to visitors who have no Drive access. Before choosing it, prepare a separate approved private export snapshot, review the actual pages, annotations, summaries, editorial notes, filenames, evidence and translations, and choose the note IDs suitable for disclosure. Later changes to approved IDs' contents also need review.

Only after that decision, configure `PUBLIC_MODE: true`, the dedicated export file ID and explicit `PUBLIC_NOTE_IDS` in the private Apps Script project. Choose owner execution and the intended public audience during deployment. An empty public list exposes zero notes. Retired and unlisted IDs remain inaccessible, including requests for their images. The server constructs the public response from an explicit nested field list. It omits private reviews, raw failures, prompts, provenance, technical search fields, Drive IDs and direct Drive links. Public scan bytes are available for listed notes. The export file itself must stay private.

The public gate uses a shared short-lived request budget of 120 RPC/page requests and 60 image requests per minute. Busy locks or unavailable cache fail closed. This limits load and does not identify visitors or guarantee a provider quota. Neither deployment mode writes to Drive or changes sharing.

## Template maintenance

`reference.css` is the exact first style block of the correspondence template, including whitespace after LF normalization. The embedded first style block must match it byte for byte. The second block styles the browse selectors, scan enlargement and the catalogue-number highlight. Transcription panels grow with their text. When a page, annotation or translation contains a line of 72 characters or more, all desktop pages in that note use the reference's 47/53 scan-to-text split. Shorter lines use equal columns. The footer points to the [field-note repository](https://github.com/erl67/museum-field-note-transcriber).

The template orders collector folders by latest finished processing activity when available and alphabetically on ties. Carriker opens by name regardless of that order. The scan-set selector appears for nested folders. Search, collector, set, group, sort and mode follow a reader link and its previous/next navigation. Pages with a recorded side show **Front** or **Back**. In a public deployment, **Copy note link** copies this deployment's `?note=note_…` bookmark, with a selectable URL if clipboard access fails. Rebuild the embedded script after editing `client.js` with `& $py scripts/build_viewer.py`. See [offline tests](../../docs/testing.md).
