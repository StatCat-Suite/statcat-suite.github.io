# Zoom-out review, round 2: Inventory history log, revision 2

**Target:** `docs/design/inventory-history-log.md` (revision 2, lines 1-516)
**Lens:** `egm-zoom-out` (Simplicity and Scope), against `zoom-out-standard.md`
**Verdict:** revise. No Blockers. The design meets the settled decisions, but six mechanisms or claims can be cut, fixed or deferred. Two of them are stage-1 format commitments that should be settled before sdmxlib#361 merges: `from_seq`, and the size of `entry`.

## What was read

- Persona and standard: the egm plugin's `agents/zoom_out.md` and `resources/document_standards/zoom-out-standard.md`.
- Style rules: the hub `CLAUDE.md`, the "Writing style" section.
- Round 1: `../zoom_out_report.md` and `../review_report.md`.
- sdmxlib: `src/sdmxlib/inventory/EGM.md`, `_reader.py` (lines 60-199), `_format.py` (lines 1-300), `conformance.py` (searched), and `docs/design/sharded-bundle-catalog.md` (§6.1, §6.3 lines 370-381, §6.6 line 499, §10.1 lines 695-705, §11.6 lines 766-770). Also `docs/design/sharded-bundle-catalog-plan.md` line 153.
- statcatlib: `src/statcatlib/store/inventory.py` (lines 300-491), `src/statcatlib/admin.py` (searched; `prune` at line 520, `dry_run` at line 548), and all of `src/statcatlib` searched for locks.
- sdmxlib-rest: `src/` searched for any read of `catalog.json`.

The reviewer could not run git, so it read the working trees, not the cited commits (sdmxlib `b6c79892`, statcatlib `95fd7ad`, sdmxlib-rest `f1582e4`). Nothing it read contradicts the design's "Based on" line. `INVENTORY_FORMAT` and `CATALOG_FORMAT` are `"1.0"` (`_format.py:23,26`), and `EventKind` has nine kinds (`_format.py:41-43`). The file:line citations below refer to the working trees.

## Major

### M1. The catalog.json 2.0 lock-out does not reach the serving reader, so the reader change belongs in stage 1 (lines 154-158, 224-235, 389, 417-422)

Line 156 says "neither an old reader nor an old writer can open an expiring catalog", and risk row 389 says "older readers refuse 2.x catalogs". Neither holds for the reader pods use:

- `_Chain.refresh` (`_reader.py:119-155`) reads `CURRENT` and roots and never reads `catalog.json`.
- sdmxlib-rest's `src/` never reads `catalog.json` (no match for `decode_catalog`, `catalog.json` or `CATALOG_NAME`).

The lock-out does reach writers. `InventoryWriter.try_commit` decodes `catalog.json` on every commit (`inventory.py:426`, through `catalog_document()` at line 317), and `decode_catalog` refuses another major version (`_format.py:274-276, 284-290`). So catalog.json 2.0 stops old statcatlib writers from writing roots without `changes`, which is the job it needs to do.

An old pod reader goes wrong in one case only. With `CURRENT` missing, it starts at seq 0, reads checkpoint 1, gets a 404 at seq 2 and returns version 1 (`_reader.py:128-148`). Expiry is the only thing that makes this possible.

The reader also does not need to know the catalog version. The rule can be: when `CURRENT` is missing, fetch `inventory/HISTORY`; a 404 means floor 0. That rule changes nothing on a catalog that never expires, so it can ship before any catalog opts in. The plan already sets this order: "A format change ... ships in an sdmxlib release first, and every reader deploys it before statcatlib writes it" (`sharded-bundle-catalog-plan.md:153`).

**Edit:**

- Line 156: "sdmxlib writers before this release refuse a 2.x catalog document (§6.1), so no old writer can write to an expiring catalog." Say that the serving reader never reads `catalog.json`.
- Line 228: "With `CURRENT` missing, the reader reads `inventory/HISTORY` if it exists and probes forward from `floor + 1`."
- Move the reader change and sdmxlib-rest's pin from stage 2 into stage 1 (lines 417-422). Make that pin a precondition of the first opt-in.
- Rewrite risk row 389 to match.

### M2. `from_seq` contradicts the writer rule and commits a stage-3 identifier in stage 1 (lines 117, 131-132, 284, 300, 496)

Lines 131-132 say the writer "computes the change list against its base version ... It reads no other version". But `from_seq` is "the `seq` of the version that put the entry into `from`". The base leaf has no such field: `LeafEntry` carries `state_changed_at` and no seq (`_format.py:194-220`; spec §6.3 lines 370-380). An entry can sit in one state for hundreds of versions. To fill `from_seq`, the writer must search older roots, which may already be expired, or the leaf format must gain a field.

`from_seq` exists only to build the informative state-entity IRI (lines 284, 300). The owner deferred that mapping to stage 3 (H8). An exporter can derive the same seq by replaying change lists from `since_seq`, because every change list since `since_seq` is kept for good and roots below it never expire (lines 159-160). Either way the field is a stage-1 format commitment, made for a stage-3 consumer, with no way for the writer to compute it.

**Edit:** drop `from_seq` from the entry item (line 117) and from the Review-response row for Major 12 (line 496). Say in the PROV section that the exporter numbers state intervals by replay, or by the `state_changed_at` the `from` entry carries. Stage 3 picks one. If the owner wants the field anyway, the leaf entry must gain a `state_seq`, and the design must say so. Lines 131-132 are false as written in either case.

### M3. `entry` as the "full `LeafEntry`" includes `artefacts` and `structure_source`, so the size figures are low (lines 119, 134-136, 393)

Spec §6.3 (lines 379-380; `_format.py:219-220`) gives `LeafEntry` two optional fields: `structure_source` (with a fingerprint map) and `artefacts` (`{urn: {fingerprint, partial_of}}`). For a structure product, or a data product with many partials, those dominate the entry. The figure of 450 bytes per change (line 134) and the 3.2 MB full republish both assume they are absent.

Neither field serves Goals 1-4. "Live at T", PROV revision and rebuild need `previous`, `schema_version`, `manifest_sha256`, `state_changed_at` and `release_at`. `manifest_sha256` pins the rest. `to` also repeats `entry.state` everywhere except `retired`.

**Edit:** define `entry` as the `LeafEntry` without `artefacts` and `structure_source`, and say that `manifest_sha256` pins them. Alternatively, keep them and give the worst-case size for a structure product. Optionally drop `to` when `entry` is present and keep it only for `retired`.

### M4. Expiry's leaf safety has two half-mechanisms; pick exclusion and drop the recreate (lines 195-198, 211-214, 388; Question 2)

The design relies on "the writer's lock" locally (line 198) and adds a read-before-delete-and-recreate step (lines 211-214) as a backstop. Neither holds up:

- **No lock exists.** No lock appears anywhere in statcatlib's `src/`. `InventoryWriter.commit` and `try_commit` (`inventory.py:381-490`) race by design through `create_exclusive`. The lock would be new work, and the statcatlib Handoff (lines 461-476) doesn't list it.
- **The recreate step misses the case it exists for.** A writer that finds a leaf already present skips writing it (`_write_leaf`, `inventory.py:339-344`). If expiry then deletes that leaf, re-reads the head before the writer's root exists, and finishes, the writer's root names a missing leaf. The reader fails every read of that product (`_reader.py:181-184`).

So if exclusion holds, step 6's recreate does nothing, and if it fails, the recreate doesn't close the gap.

**Edit:**

- Step 6 becomes "Delete leaves that no retained root names."
- Drop "reads each one's bytes" and the recreate (lines 211-214).
- State one rule. Expiry runs under the catalog's writer exclusion. On a server, that is the release job run itself: one instance at a time, with expiry in the same process after the release step. Locally, it is a lock file that both `InventoryWriter.commit` and `prune` take.
- Add the lock to the statcatlib Handoff, with a conformance case (a seal racing `prune`).
- Update risk row 388 and the acceptance item at line 453.

### M5. The PROV-O section is stage-3 material at stage-1 length (lines 254-321, 406, 412-413, 458)

The section is 68 lines. It holds the namespace, ten event classes, the state individuals, roles, properties, an IRI table with eight rows, a mapping table and a PREMIS crosswalk. All of it is informative by owner decision (H8), and stage 3 makes it normative "with IRI rules" (line 257). Goal 4 needs one thing now: the record carries every fact an export needs. A short table showing which field feeds which PROV term covers that.

The detail also draws review effort onto material that will be redone. Line 267 lists `stc:Search`, a kind with no source: `EventKind` has nine kinds and no `search` (`_format.py:41-43`), and round 1 raised the same point (finding 22). The PREMIS crosswalk (lines 314-321) serves no Goal; Goals 1-5 name only PROV-O.

**Edit:**

- Keep H7 and the mapping table, trimmed to field and PROV term.
- Move the `stc:` term list and the IRI table to `prov_o_report.md`, or to the stage-3 design, and link to it.
- Delete the PREMIS crosswalk.
- Remove "the informative Turtle example" from sdmxlib's acceptance (line 458), since it already lives in `prov_o_report.md`.
- Move the hub's namespace reservation (lines 412-413) and sdmxlib's vocabulary ownership (line 406) to stage 3.

### M6. "Rebuild from change lists" is a new capability with no Goal and no stage (lines 244, 438)

The table row at line 244 and the Handoff item "§6.7 (rebuild from change lists)" (line 438) add a change to the specification's repair path. No Goal (lines 64-77) asks for it, and the Staging section (lines 415-426) never mentions it. `rebuild-inventory` is unbuilt Phase 9 work (round 1, finding 22).

**Edit:** keep the row as a statement of what the data allows, and drop §6.7 from the sdmxlib Handoff. A later rebuild design can cite this one.

## Minor

### m1. Three checkpoint kinds reduce to two (lines 33-35, 159-160, 330)

Version 1 is the first version of `restore_epoch` 0. For a new catalog it is also `since_seq`, which line 159 already makes a checkpoint. The per-epoch rule earns its place: a change-list replay never has to cross a restore. The monthly rule is in Goal 3.

**Edit:** "Checkpoints are the first version of each `restore_epoch`, the first version of each UTC month by `created_at`, and `since_seq`." Apply the same change to H4 and the Terms entry.

### m2. Keep `inventory/HISTORY`, and say why in one sentence (lines 171, 188-191)

The reviewer weighed three alternatives:

- **Floor in `catalog.json`.** This would rewrite the identity document on every expiry run. Today that document is rewritten only to bump `restore_epoch` (spec line 328).
- **Floor from segment headers.** Segment names (`<first>-<last>`) cannot be probed without a LIST.
- **No floor, so a missing `CURRENT` is an error.** This is simpler for pods, but the writer's own `full()` (`inventory.py:323-330`) uses the same reader and needs to recover.

One object at a fixed path is the simplest no-LIST entry point. Under the candidate rule and monotone `created_at`, `floor` equals the newest segment's `last`, so the field is a cached value. That is acceptable, but say it, so `verify-catalog` can check it.

**Edit:** add "`floor` is the newest segment's `last`" at line 188.

### m3. `catalog_id` in every root has no consumer (lines 99, 183, 398)

A root lives inside its catalog, and `catalog.json` holds the id. The segment header (line 176) names the catalog for a segment, and an exporter reads `catalog.json`. The field adds a required 1.1 field and a consistency rule, for nothing a reader uses.

**Edit:** drop it from the root and the segment line, and keep it in the segment header. Update the Review-response row for Major 12 (line 496).

### m4. `verify-catalog` has three checks, not four (lines 230-233)

Check 3 (a segment's `root_sha256` against a retained root) applies only in the state a crash between steps 3 and 5 leaves behind. It is the chain check (check 1) applied where a seq appears both as a root and as a segment line.

**Edit:** "the root chain over the union of retained roots and segment lines, where a `seq` present in both must agree; every retained root's leaves; the segment links."

### m5. "Three optional root fields" against "required in 1.1" (lines 94-101)

**Edit:** "adds three root fields. A 1.1 writer always writes them; a 1.0 reader ignores them (§6.3 versioning)."

### m6. Epoch-keyed segments cover only epoch-bumping restores (lines 186-187, 390)

The conformance protocol has `restore_to`, which loses versions "keeping the epoch" (`conformance.py:110-111`), and `restore_with_new_epoch` (lines 114-115). The claim at lines 186-187 holds only for the second. This finding does not reopen the epoch layout. The claim needs a condition attached.

**Edit:** "A restore that reuses a `seq` bumps `restore_epoch` (§6.1), so it cannot touch the history of the lost versions." Alternatively, state what a storage-level restore that keeps the epoch does to `history/`. It comes back from the same backup (§10.3).

### m7. Stage 1 is not Phase 5 work (lines 407-409, 426)

Stage 1 needs only an sdmxlib release and statcatlib's local writer. The release job is Phase 5 (`sharded-bundle-catalog-plan.md:57, 175`). Local expiry through `prune` doesn't need the release job either.

**Edit:** "Stage 1 ships with the next sdmxlib and statcatlib releases. Stage 2's local expiry ships when it is ready, and server expiry ships with the Phase 5 release job. Stage 3 comes later."

### Weighed and kept

- **The dry run** (lines 215-216). It reuses `prune(dry_run=True)` (`admin.py:520, 548`), so keep it at one sentence.
- **Both K and W.** They guard different things. K keeps the reader's fallback when `CURRENT` and the head go bad after a quiet spell, since without K the age rule alone can leave only the head. W covers GC, backups and pod polling.
- **§6.6 escape route** (lines 337-361). Its length fits a Blocker resolution, and it needs no change.

## Recommended answers to the Questions for review

**Q1. Is `catalog.json` 2.0 the right lock-out, or should expiry gate on a root format major instead?**
Keep `catalog.json` 2.0, and describe it as a writer lock-out. A root major would make every old pod refuse every new root (`_format.py:274-276`) for a change those pods can mostly read. That is a hard cutover across sdmxlib-rest for one failure case. Old writers are the real risk, because they would write roots without `changes`, and statcatlib's writer reads `catalog.json` on every commit (`inventory.py:426`). Old readers fail only when `CURRENT` is missing. Ship the reader's `HISTORY` fallback in stage 1, and have sdmxlib-rest pin it before any catalog opts in (M1).

**Q2. Is the single-writer argument for expiry (H5) enough on a server, or does step 6 need a grace period as well?**
It is enough, and no grace period is needed, provided the design states that the release job runs one instance at a time and that expiry runs inside that run. A grace period fits poorly with content-addressed leaves: a reused leaf is old by any timestamp, so age says nothing about whether a writer is about to name it. Exclusion covers that case. Locally, add a lock that both commit and `prune` take, since none exists today. Drop step 6's recreate, which does nothing under exclusion and doesn't close the gap without it (M4).

**Q3. Does K = 10 by default fit a 5 s pod poll interval?**
Yes, because the poll interval bounds W, and K is independent of it (line 204). A pod reads `CURRENT` on every refresh and probes forward from it (`_reader.py:126-148`), so it never needs an expired root as long as W is longer than the poll interval plus fetch time. Against a W of days, 5 s doesn't matter. K exists for the fallback when `CURRENT` and the head go bad, and 10 versions is about one to three days at 3 to 10 versions a day. Keep K = 10 and K ≥ 2, and reword the question or close it.

## Mechanisms traced to Goals

| Mechanism | Goal | Keep? |
| --- | --- | --- |
| `changes`, `previous_root_sha256` | 1, 2 | yes |
| `entry` (trimmed, M3) | 1, 4 | yes |
| `from_seq` | 4, stage 3 only | cut (M2) |
| `catalog_id` in the root | none | cut (m3) |
| Monthly and per-epoch checkpoints | 3 | yes; version 1 merged (m1) |
| `HISTORY` | 3 (reader after expiry) | yes (m2) |
| Segment header and links | 2, 5 | yes |
| Step 6 read-and-recreate | none once exclusion holds | cut (M4) |
| `verify-catalog` check 3 | 2, duplicates check 1 | merge (m4) |
| `stc:` term list, IRI table | stage 3 | defer (M5) |
| PREMIS crosswalk | none | cut (M5) |
| §6.7 rebuild from change lists | none | defer (M6) |

## Cut, defer, merge

- **Cut:** `from_seq` (line 117); `catalog_id` in roots and segment lines (lines 99, 183); step 6's read-before-delete and recreate (lines 211-214); the PREMIS crosswalk (lines 314-321); `stc:Search` (line 267).
- **Trim:** `entry` drops `artefacts` and `structure_source` (line 119).
- **Defer to stage 3:** the `stc:` term list, the IRI table, the Turtle acceptance item, the hub namespace reservation (lines 261-288, 412-413, 458).
- **Defer to a later design:** §6.7 rebuild from change lists (line 438).
- **Merge:** the version-1 checkpoint into the per-epoch rule (lines 33-35, 330); `verify-catalog` check 3 into check 1 (lines 230-233).
- **Move into stage 1:** the reader's `HISTORY` fallback and sdmxlib-rest's pin (lines 224-235, 420-422), and the statement that stage 1 does not wait for Phase 5 (line 426).
- **Add:** the local writer lock to the statcatlib Handoff (lines 461-476).
