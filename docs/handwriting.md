# Optional handwriting context

A profile supplies approved reading notes and a few verified **text** examples to one selected batch. Staff may keep several profiles for different hands or periods associated with a collector. The software never selects a profile by filename or promotes a service reading into a training example. Omitting the profile is the default.

Store staff files beneath ignored `local/profiles/`. This is a template. Fill in the actual scan ID, original hash, region, verified wording, reviewers and approval only after checking source evidence.

```json
{
  "schema_version": 1,
  "profile_id": "staff-hand-a",
  "version": "1",
  "hand_description": "Describe the reviewed hand and period, including limits of attribution.",
  "reviewer": "Profile reviewer",
  "review_status": "approved",
  "notes": ["Replace with a verified observation about recurring letterforms."],
  "examples": [{
    "image_id": "REPLACE_WITH_SOURCE_IMAGE_ID",
    "source_sha256": "REPLACE_WITH_ORIGINAL_64_HEX_DIGEST",
    "region": "Specify the page region and line precisely.",
    "transcription": "Replace with verified source text.",
    "review_status": "verified",
    "reviewer": "Example verifier"
  }]
}
```

The profile limit is five verified examples and 16,000 UTF-8 bytes for the complete encoded profile. A staff-approved notes-only profile may use an empty examples array. The selected file, including its attribution and examples, becomes request context, so include only material intended for that submission.

```powershell
& $py -m fieldnotes dry-run --input $scans --profile local/profiles/hand-a.json
& $py -m fieldnotes transcribe --note $note --profile local/profiles/hand-a.json --env-file .env
```

The application reads the profile once for the batch and records its exact content and hash. An already registered ID and version cannot acquire different contents. Increment the version when editing notes, examples or reviewer information. The resulting request fingerprint changes. Earlier results keep their own frozen context. The dry run checks profile shape and request size without registering a profile or opening the quota file.
