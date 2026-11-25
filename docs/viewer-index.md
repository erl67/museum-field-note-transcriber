# Reader index and website migration

## What identifies a card

A stable `note_id` identifies a whole physical card or explicitly ordered group. Each scan has an `image_id`, a one-based order and its original size and SHA-256. The association between a transcription page and its scan is the image ID. The scan filename supplies physical ordering within a set. Numbers come from the saved or corrected `identifiers` fields, and may be missing, duplicated, suffixed, padded or written as a range. Folder attribution and review status remain separate from the historical text.

## Portable reader archive, version 2

`fieldnotes export --viewer-only` builds `Field_notes_index/index.json` plus immutable JSON objects. All files use UTF-8. A reference is the lowercase SHA-256 of the referenced file's exact bytes. It resolves to `<reference>.json` in the same directory on either host. Keep related files private until a specific snapshot has been reviewed for public display.

| Resource | Contents | When read |
| --- | --- | --- |
| `index.json` | Kind, schema version, counts, page size, collectors, their sets, set-directory references, ID-directory and identifier-directory references, and a digest of sorted active IDs joined with LF | Each request starts from the current manifest |
| Set directory | Ordered array of references to set pages | Opening a set or calculating neighbors |
| Set page | Up to 40 card summaries with stable ID, collector folder, all set memberships, numbers as written, species, reading state and page count | One page at a time |
| ID directory and buckets | First two hex digits after `note_` select a bucket. Each entry contains a note-object reference and zero-based positions within its sets | Resolving a bookmark or an image request |
| Number directory and buckets | Exact-label buckets and candidate buckets for decimal ranges. Each carries compact summary rows. The resolver confirms the full label or range and scopes results to the selected collector | Searching an identifier |
| Note | Catalogue fields, page text, annotations, translations, evidence, summary, review states and ordered original-scan manifest. May include private transport mappings | Opening one card and verifying its selected scan |
| Original JPEG | Exact source bytes, located by relative path or optional mapped Drive ID | Opening a card loads each scan in order. Enlargement reuses the displayed image. |

The home response contains set names and counts. The index contains no embedded JPEGs, generation prompts, raw failed responses or technical logs. The journal and staff exports retain the complete history. The local export can retain older immutable objects. Use the managed publisher or the exact file dictionary returned by `viewer_files` to stage only resources reachable in the selected build.

### Order, search and updates

- Sets follow the first scan's natural collector/folder/filename order. Each set lists whole cards. A card with pages filed in multiple sets is visible from each such set, and keeps its original page order. Collector and archive totals count the card once.
- The header's notepad opens a uniformly random published card. The server draws a position using set counts, reads the corresponding browse page and opens that card in one browser request. Only the first set membership counts for cards filed across sets. The JPGs load separately.
- Exact search trims outer whitespace and folds ASCII case. Leading zeros and punctuation remain significant. Range and compound-number lookups use the existing field-note rules, including abbreviated endpoints and padded ranges. The reader returns every match and paginates the result. A stable archival ID can also be entered in the search field.
- A note's content hash binds each scan request to the reading the visitor opened. A changed card prompts a reload. An unchanged card can remain open through an unrelated update. Readers reject missing, duplicate or mismatched index resources. Small immutable objects can use Apps Script's per-user cache after an access check.
- Publication reuses the existing ownership journal, archive-before-replacement checks and atomic local writes. The manifest is written last. Drive for desktop transfers each file independently. A partially synced publication can require a reload once synchronization finishes.
- To add another collector or set, admit its scans to inventory, apply readings or reviews when available, and publish again. No change to UI code or collector configuration is needed.

## Bookmarks

Append these parameters to the Apps Script deployment URL. The planned website base is `/birds/field-notes/`. The same query string identifies the same reading on either host.

| View | Query |
| --- | --- |
| Collector | `?collector=Carriker` |
| Set, second list page | `?collector=Carriker&set=Carriker%2Fset1&p=2` |
| Number across collectors | `?number=8420` |
| Number in one collector | `?number=8420&collector=Carriker` |
| Random whole card, then a bookmark to the chosen card | `?note=random` |
| Whole card, scrolled to the second scan | `?note=<stable-note-id>&page=2` |

The reader accepts existing numeric shortcuts and `q` / `query` aliases for the identifier field. Copied note links omit search context. Links inside a set or result list carry the browse context so previous/next and the return link lead to the matching rows. Browser Back works with ordinary page URLs. Existing website rules for correspondence aliases and bare egg numbers should continue to resolve to their current readers.

## Integrate the website publisher in Phase 2

The website checkout already has `publish_webpage.py prepare --field-notes`. Its `field_notes_collection.py` reads the v1 working export and uses `reader_files.stage_verified_jpegs` to stage original bytes under `scans/field-notes/`. Its local `scan-manifest.json` maps stable note and image IDs to ordered paths. The current field-notes action is limited to preparation. Egg and correspondence publication have their own working routes and transfer lists.

1. Extend that existing prepare branch to consume a reviewed v2 archive from this repository. Stage its reachable manifest and immutable JSON under `birds/field-notes/data/`. Use the same selected IDs, scan order, image IDs and original hashes for the JPEG staging step. Prepare a public export without private Drive mappings, and compare the staged JPEG manifest with the selected v2 notes before transfer.
2. Bring the reader HTML and renderer to `birds/field-notes/`. Link `../assets/birds.css`, retain the documented field-specific controls, and use the existing header and footer links. Replace Apps Script template parameters with `URLSearchParams`. Replace the Drive object loader with same-origin JSON fetches, and image RPCs with URLs from the verified website scan manifest. The manifest, hashes, routing tables, pagination, note/page keys and display fields are portable. The Drive gate, owner/visitor settings, CacheService and access budgets belong to the Apps Script adapter.
3. Extend the publisher's existing field-notes selection with preview, dry-run and transfer phases. Transfer selected JPEGs, immutable JSON and reader assets first, then replace the entry manifest. Validate a duplicate number, an incomplete card, a multi-page bookmark and a previously shared link before adding the website homepage link.
4. After the website reader is live and verified, update the Apps Script notice to link to its actual URL. Keep the Apps Script deployment and its private publication destination available as the backup.

The website checkout serves as a read-only reference for this phase. Its current correspondence HTML, reader JavaScript, shared `dist/assets/birds.css`, egg reader, deployment redirects and publisher informed the Phase 1 implementation.
