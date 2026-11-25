# Field Notes Viewer for Google Apps Script

The opening page lists collectors and their scan sets. Selecting a set shows up to 40 whole cards at a time in scan order. Search accepts a collection number, a member of a written range or a stable `note_…` ID. The collector selector scopes the search. A card opens with all its pages in order, front above back. Each scan appears beside its transcription on desktop and above it on a phone. Each image can be enlarged. Previous/next note follows the set or search results.

## Try it offline

From the repository root in PowerShell, run:

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py scripts/make_demo.py
node scripts/preview.cjs
```

Open [the synthetic preview](http://127.0.0.1:8783/). Try `0012` across both collectors, then select Carriker and open the two-page card. Search `8420` for an interior member of a written range. The preview uses invented scans. Ctrl+C stops it.

## Prepare and publish private Drive data

1. Use the normal inventory, transcription and review commands. An inventoried card can appear before it has a completed reading. The journal and original JPEGs supply the inputs.
2. Build the reader files locally. With the original scan volume mounted, add `--verify-scans` to check original sizes and SHA-256 values. Offline export validates the saved scan/page relationships, reports unavailable readings and lists inventory scan issues by ID.
3. Choose a **private, locally synced Drive folder** for reader data. A Transcriptions subfolder inside Field Notes works. Use this as the publication destination. The publisher creates and manages its own `Field_notes_index` child. Keep the same local store for later publications.
4. Wait for Drive for desktop to finish syncing. In the Drive web interface, identify the **Transcriptions parent folder ID** and the **scan-root folder ID** containing the collector directories. The viewer addresses index files by exact name inside the index folder. A new Drive file ID for a replaced index.json is fine.

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py -m fieldnotes export --viewer-only
# Example destination. Use your actual existing private folder on the synced drive.
$destination = 'G:\My Drive\Field Notes\Transcriptions'
& $py -m fieldnotes publish --viewer-only --verify-scans --destination $destination
```

Run the same publish command after admitting a new collector or finished set, transcribing cards, or applying reviews. The index discovers collector and set names from the inventory. An unchanged publication leaves the destination files alone. Changed publications install the new objects before replacing the manifest, then retire obsolete owned files. Drive synchronization can briefly expose an incomplete update. Wait for sync and reload, or repeat a failed local publication with the same store. The [staff output guide](../../docs/outputs.md) covers ownership and recovery.

### Optional image mapping

Root-relative scan paths normally suffice. For example, `Carriker/set1/card.jpg` resolves by exact child names from the configured scan root. Duplicate or invisible items produce a message beside the available text. Each ready scan must match its recorded size and original hash before display.

An explicit mapping selects a particular Drive file. Save the mapping under ignored `local/drive-mapping.json`. Replace the placeholders with the actual image ID, Drive file ID and original SHA-256 from the inventory.

```json
{"version":1,"images":{"REPLACE_IMAGE_ID":{"file_id":"REPLACE_DRIVE_FILE_ID","original_sha256":"REPLACE_ORIGINAL_SHA256"}}}
```

Add `--mapping local/drive-mapping.json` to each indexed export or publication that uses it. A failing explicit mapping reports an error for that scan.

## Install the web app

The repository manifest permits anonymous visitors and runs the web app under the deploying account with read-only Drive access. In public mode, every card in the configured `Field_notes_index/index.json` publication is viewable, including cards awaiting transcription. The Drive folders can remain private.

Build the three complete editor files with your scan-root and Transcriptions folder IDs.

```powershell
& $py scripts/build_viewer.py --scan-root <SCAN_FOLDER_ID> --index-parent <TRANSCRIPTIONS_FOLDER_ID>
```

Replace the two placeholders with the actual folder IDs.

1. In Apps Script, enable **Show "appsscript.json" manifest file in editor** under **Project Settings**.
2. Replace **Code.gs**, **Viewer.html**, and **appsscript.json** with the corresponding complete files in `local/apps-script-install/`. The generated Code file includes both server modules and both folder IDs.
3. Save and deploy as a **Web app** with **Execute as me** and access set to **Anyone**. For an existing deployment, choose **Deploy → Manage deployments → Edit → New version → Deploy** to keep its URL.
4. Open the production `/exec` URL in a signed-out window and check a card and its scans.

The indexed reader rechecks its gate at every page and data request. It opens files by exact names or verified image mappings. Opening a card shows all its transcriptions and requests its JPEGs one at a time in scan order. Each image is verified independently. A scan over 12 MiB receives an explicit display-limit message. Browser requests cannot name a Drive file or filesystem path directly.

### Verify a deployment

- Open the home URL in the intended account. Compare the collector and set counts with the local export. Expand a collector and follow a set.
- Inspect a completed front/back card. Compare the original filenames, sequence, visible text and review states with the local reading. Enlarge a scan. Copy its page link, open it in another tab and use Back after visiting a neighboring card.
- Search a known written number and a range member. Try a missing identifier and, when available, a duplicate across collectors. Check that an incomplete card still displays its scan.
- Test a narrow viewport and a fresh signed-in session. If you subsequently choose a restricted multi-user audience, check an intended reader and an account outside that audience. A Drive sync error or revoked permission must leave an explanatory message.
- Use the [index and migration guide](../../docs/viewer-index.md) for the portable URLs and file contract. Google's [web-app deployment guide](https://developers.google.com/apps-script/guides/web) describes deployment identity and editor-only test URLs.

### Updating the public selection

Run the viewer publish command above to include all active cards in the current inventory. To publish a subset, add `--viewer-notes local/approved-note-ids.json` to each publication and put the desired IDs in that JSON array. If you previously passed a selection file to the builder with `--public-notes`, use that file with `--viewer-notes` at publication. Once Drive sync finishes, additions and removals apply to browsing, random picks, bookmarks and scans on the existing web app URL. Apps Script only needs a new deployment for code or configuration changes.

## Existing installations and styling

An existing installation configured only with `EXPORT_FILE_ID` continues to use its v1 working bundle and earlier full-text/species browser. Public v1 installations still honor their original `PUBLIC_NOTE_IDS` setting and show zero cards when it is absent. The 10 MiB whole-export limit still applies there. Set `INDEX_FOLDER_ID` to switch to the indexed reader. Stable note IDs and numeric bookmarks carry across.

The first style block is the verbatim `reference.css`. The card header includes a 44-pixel, icon-only notepad link for opening a random card. The second block adapts the current website's back link, search spacing and button, transcript wrapping and mobile minimum height. It also styles the set list, collector controls, number highlight, scan dialog and the correspondence Apps Script migration notice below the header. Its future-tense text lives in one `aside` in `Viewer.html`. The site stylesheet could be linked via HTTPS. Embedding these rules keeps the Drive backup and offline preview independent of website availability. [HTML Service restrictions](https://developers.google.com/apps-script/guides/html/restrictions)

After editing `client.js`, run `& $py scripts/build_viewer.py` and the [offline checks](../../docs/testing.md).
