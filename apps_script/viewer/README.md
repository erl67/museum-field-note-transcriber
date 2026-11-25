# Field Notes Viewer for Google Apps Script

The opening page lists collectors and their scan sets. Selecting a set shows up to 40 whole cards at a time in scan order. Search accepts a collection number, a member of a written range or a stable `note_…` ID. The collector selector scopes the search. A card opens with all its pages in order, front above back. Each scan appears beside its transcription on desktop and above it on a phone. Each image can be enlarged. Page headings on multi-page cards link to that page within the whole card. Previous/next note follows the set or search results.

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

For manual copy-and-paste, prepare a private installation from the repository root. Supply the folder IDs from the two Drive links.

```powershell
& $py scripts/build_viewer.py --scan-root <SCAN_FOLDER_ID> --index-parent <TRANSCRIPTIONS_FOLDER_ID>
```

Replace both placeholders before running the command. The three files in `local/apps-script-install/` are ready for the Apps Script editor. **Code.gs** includes both server modules and the configured folder IDs. Copy its contents into **Code**, copy **Viewer.html** into **Viewer**, and copy **appsscript.json** into the manifest. Continue at step 3 below. This version resolves the named index folder under Transcriptions on each request. The signed-in visitor's access to that folder supplies the gate.

For an installation directly from the tracked sources:

1. Open a standalone Apps Script project. Add script files **Code** and **Index** from `Code.gs` and `Index.gs`. Add an HTML file named **Viewer** from `Viewer.html`. Enable **Show "appsscript.json" manifest file in editor** in Project Settings and use the supplied `appsscript.json`. These four files are the installation. The HTML embeds its client and CSS.
2. In the project's private copy of **Code**, set `SETTINGS.INDEX_PARENT_FOLDER_ID` to the Transcriptions folder and `SCAN_ROOT_FOLDER_ID` to the original scan root. Alternatively, set `INDEX_FOLDER_ID` to the generated folder itself. A separate `ACCESS_FILE_ID` is optional for indexed deployments. If used, choose a stable file visible to the intended readers. Leave `EXPORT_FILE_ID` blank and `PUBLIC_MODE` false for this installation. Each reader needs permission to the gate, index folder and original scans.
3. Save. Use **Deploy → Test deployments → Web app** for an editor test. Authorize read-only Drive access in the intended account. Open the test URL. For the private installed version, use **Deploy → New deployment → Web app**, execute as the **user accessing the web app** and choose **only myself**. The checked-in manifest uses this private configuration.
4. Copy the assigned `/exec` URL. After changing code, use **Deploy → Manage deployments → Edit**, select a new version and update the same deployment to preserve bookmarks. Data-only updates use the publisher and keep the same web app URL.

The indexed reader rechecks its gate at every page and data request. It opens files by exact names or verified image mappings. Opening a card shows all its transcriptions and requests its JPEGs one at a time in scan order. Each image is verified independently. A scan over 12 MiB receives an explicit display-limit message. Browser requests cannot name a Drive file or filesystem path directly.

### Verify a deployment

- Open the home URL in the intended account. Compare the collector and set counts with the local export. Expand a collector and follow a set.
- Inspect a completed front/back card. Compare the original filenames, sequence, visible text and review states with the local reading. Enlarge a scan. Copy its page link, open it in another tab and use Back after visiting a neighboring card.
- Search a known written number and a range member. Try a missing identifier and, when available, a duplicate across collectors. Check that an incomplete card still displays its scan.
- Test a narrow viewport and a fresh signed-in session. If you subsequently choose a restricted multi-user audience, check an intended reader and an account outside that audience. A Drive sync error or revoked permission must leave an explanatory message.
- Use the [index and migration guide](../../docs/viewer-index.md) for the portable URLs and file contract. Google's [web-app deployment guide](https://developers.google.com/apps-script/guides/web) describes deployment identity and editor-only test URLs.

### Optional public installation

The private installation is sufficient for development. For a separate public release, review the actual notes, scans, metadata, paths, translations and annotations for disclosure. Build a dedicated private destination with `--viewer-notes local/approved-note-ids.json`. That file is a JSON array of unique active note IDs. Use the identical list for `PUBLIC_NOTE_IDS` in the private script configuration and enable `PUBLIC_MODE`. The manifest membership must match, and direct note/image lookup also enforces the allowlist. An empty list and an empty index display no cards. Re-review changed readings before republishing.

Choose the owner execution identity and intended audience explicitly for such a deployment. Visitors can see the selected reading and verified image bytes using the owner's permissions. Keep the index folder and scan collection private. Public responses omit Drive file IDs, Drive links and private processing history. Existing public request and image budgets apply to the indexed endpoints as well.

## Existing installations and styling

An existing installation configured only with `EXPORT_FILE_ID` continues to use its v1 working bundle and earlier full-text/species browser. The 10 MiB whole-export limit still applies there. Set `INDEX_FOLDER_ID` to switch to the indexed reader. Stable note IDs and numeric bookmarks carry across.

The first style block is the verbatim `reference.css`. The second block adapts the current website's back link, search spacing and button, transcript wrapping and mobile minimum height. It also styles the set list, collector controls, number highlight, scan dialog and the correspondence Apps Script migration notice below the header. Its future-tense text lives in one `aside` in `Viewer.html`. The site stylesheet could be linked via HTTPS. Embedding these rules keeps the Drive backup and offline preview independent of website availability. [HTML Service restrictions](https://developers.google.com/apps-script/guides/html/restrictions)

After editing `client.js`, run `& $py scripts/build_viewer.py` and the [offline checks](../../docs/testing.md).
