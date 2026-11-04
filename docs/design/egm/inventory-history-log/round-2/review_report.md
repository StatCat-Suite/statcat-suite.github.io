# EGM review report, round 2: Inventory change lists and history segments

**Target:** `docs/design/inventory-history-log.md`, revision 2, lines 1-516. The draft is uncommitted, on hub branch `docs/design-inventory-history-log` at `17d6e5d`.
**Date:** 2026-11-03
**Mode:** REVIEW, consolidated, round 2. Round 1's reports are in the parent folder; its consolidated report is `../review_report.md`.

## What was read

The design cites sdmxlib `b6c79892`, statcatlib `95fd7ad` and sdmxlib-rest `f1582e4`. The reviewers had no shell, so none could confirm that the checkouts are at those commits. Every `file:line` below refers to the working trees at `/Users/gabrielgellner/dev/{sdmxlib,statcatlib,sdmxlib-rest}`. Before the design cites any of them, check each against `git -C ../<repo> show origin/main:<path>`. No reviewer found code that contradicts the design's "Based on" line.

The reviewers had no web access. Every W3C PROV, DCAT, PREMIS, RFC and Turtle point rests on the reviewer's own knowledge; the "Verify before citing" list below names them.

The owner's decisions were taken as settled: change lists in the root, append-only segments under `history/<restore_epoch>/`, PROV-O data normative and mapping informative, expiry in the release job, and `catalog.json` 2.0 opt-in. No finding reopens them.

## Reviewer reports

| Lens | Report |
| --- | --- |
| Design, storage and safety (`egm-design`, instance A) | `design_storage_report.md` |
| Design, PROV-O (`egm-design`, instance B) | `prov_o_report.md` |
| Zoom-out (`egm-zoom-out`) | `zoom_out_report.md` |

## Summary

After deduplication the round has 6 Blocker, 13 Major and 14 Nit findings. The storage reviewer counted 3 Blockers, the PROV-O reviewer 3, and the zoom-out reviewer none. Where reviewers disagreed on severity, this report takes the higher one and says so.

Revision 2 closes round-1 blockers B1, B5 and B6. B2, B3 and B7 are partly closed, and B4 is still open (blocker 6). Blockers 4 and 5 are new defects that revision 2 introduced. Blockers 1 to 3 are gaps in format 1.1.

Those three blockers sit in Inventory format 1.1, which stage 1 ships: the chain's base version, `from_seq`, and the seal's time. They must be settled before StatCat-Suite/sdmxlib#361 merges, because the change list becomes a normative record from the first 1.1 root.

## Round-1 blocker status

| Round-1 blocker | Status | Remaining defect |
| --- | --- | --- |
| B1 orphan record race | Closed | The root is the record, so no record can disagree with its root. The chain's base version is still ambiguous (blocker 1). |
| B2 restore reuses `seq` | Partly closed | Segment names cannot collide across epochs. `HISTORY` carries no epoch, one run can span epochs, cross-epoch segment order is undefined, a restore drops unexpired lost versions' change lists, and a restore that keeps the epoch still reuses `(epoch, seq)` (Major 1). |
| B3 reader stops at gaps | Partly closed | The new reader is specified. Old readers ignore `catalog.json` (blocker 5), and the floor rule misses a held root below the floor, an absent `HISTORY`, and the epoch (Major 2). |
| B4 expiry races writers on leaves | Open | The "writer's lock" does not exist, and step 6's recreate misses a root written after its re-read (blocker 6). |
| B5 escape route | Closed | Section "The §6.6 escape route" and H9. |
| B6 untestable normative mapping | Closed | H8 makes the mapping informative. Its example now fails to parse (Major 11). |
| B7 no migration | Partly closed | Opt-in and `since_seq` exist. The crash rule deletes roots below `since_seq` (blocker 4), and `since_seq` is ill-defined when an old writer wrote a 1.0 root after it (Nit 9). |

## Prioritized findings (Blocker, then Major, then Nit)

### Blockers

#### 1. The root chain and the change list are defined against `previous_inventory`, which a correction makes non-linear - Severity: Blocker

* **Reviewer Lens:** design (PROV-O) B1, design (storage) M4 (rated Major there)
* **Affected Scope:** lines 29-30, 100-101, 128-132, 242, 297
* **Discrepancy Description:** Line 100 hashes root `previous_inventory`, and line 101 diffs the change list against it. Lines 131-132 diff against the base version, which is the head `seq - 1` (spec §6.6 line 486). A `correct` version sets `previous_inventory` to `built_from`, an older version (sdmxlib `_rules.py:481, 495-496, 511`; `_format.py:138-140`). With version 41 built from 39:
  - nothing links to root 40, so deleting or editing it goes undetected, against Goal 2;
  - the change list reports `from` states as of 39, so a PROV export invalidates some state entities twice and never ends others;
  - "live at T" (line 242) replays wrong answers.

  No statcatlib writer passes `built_from` today, but format 1.1 fixes the rule for every later writer.
* **Rationale & Recommendation:** Line 100: "SHA-256 of the stored bytes of root `seq - 1`, the head the create-if-absent won against (after a restore, the root the restore built from)." Line 101: "one item per product whose leaf hash differs from root `seq - 1`'s." Apply the monotone `created_at` rule (line 128) against root `seq - 1` as well, across epochs. Keep `previous_inventory` as "built from", which `prov:wasRevisionOf` follows. Add a conformance case: a correction built from an older version, checked for its change list and its chain.

#### 2. A writer cannot compute `from_seq` under the design's own rule - Severity: Blocker

* **Reviewer Lens:** design (PROV-O) B2, M1, M7; zoom-out M2 (rated Major there)
* **Affected Scope:** lines 117, 131-132, 159-160, 284, 300, 496
* **Discrepancy Description:** `from_seq` is "the `seq` of the version that put the entry into `from`". Line 132 says the writer reads only its base version. The base leaf carries `state` and `state_changed_at` and no seq (`_format.py:194-220`; spec §6.3 lines 370-380). `state_changed_at` cannot be matched to a root's `created_at`, because the two come from separate clock reads (statcatlib `admin.py:325` against `store/inventory.py:422`). An entry whose state was entered below `since_seq` has no change list at all, and line 117 permits `from_seq: null` only with `from: null`. Two more defects follow:
  - `from_seq` names no epoch, so a state entered in epoch E and ended in E+1 resolves to a state that was never generated.
  - When an entry changes and keeps its state, "the version that put the entry into `from`" can be read as the first entry into that state, which double-ends one PROV state entity.

  `from_seq` serves only the informative state-entity IRI (lines 284, 300).
* **Rationale & Recommendation:** The reviewers disagree on the fix, and the owner picks one before sdmxlib#361 merges:
  - **(a) Drop `from_seq`** (zoom-out). The stage-3 exporter numbers state intervals by replaying change lists from `since_seq`, which are kept for good. This adds nothing to format 1.1.
  - **(b) Add `LeafEntry.state_seq` and `state_epoch`** (PROV-O). The writer sets them whenever it writes a state, and `from_seq` and `from_epoch` copy the base entry's values. An entry carried from a 1.0 leaf gets `from` non-null with `from_seq: null`, meaning "entered at or before `since_seq`".

  This report recommends (a): it keeps the writer reading one version, adds no leaf field, and moves a stage-3 identifier out of stage 1. Under either choice, define the predecessor as "the most recent change item for this edition", and correct lines 131-132.

#### 3. The mapping's "generated once, by its seal" needs a fact the Inventory never records - Severity: Blocker

* **Reviewer Lens:** design (PROV-O) B3
* **Affected Scope:** lines 73-75 (Goal 4), 264, 299
* **Discrepancy Description:** An edition's seal time and producer are manifest fields (spec §4.2 line 141). `LeafEntry` copies neither (§6.3 lines 368-380). On a server the seal runs on a build node, and the Inventory later records a fold of `pending/` (§11.2 lines 735-736), whose `event.kind` the spec does not name. GC deletes retired editions' manifests (§11.3, §11.4), so an exporter that later reads the manifest loses the fact. Goal 4 says the record carries every fact an export needs, and this row needs one it lacks.
* **Rationale & Recommendation:** Pick one:
  - **(a)** Line 299: "a `prov:Entity` that `prov:specializationOf` its product and `prov:wasRevisionOf` its `previous`. The Inventory export asserts no generation for it and never invalidates it." Define `stc:Seal` as "the version that records a sealed edition". No format change.
  - **(b)** Add `sealed_at` and `sealed_by` to each change item whose `from` is null.

  This report recommends (a), since the owner wants the mapping corrected against a real consumer before it gains fields (H8).

#### 4. The crash-recovery rule deletes roots that no segment records - Severity: Blocker (new in revision 2)

* **Reviewer Lens:** design (storage) N1
* **Affected Scope:** lines 41-42, 159-160, 200-204, 210, 218-220
* **Discrepancy Description:** Line 220 says the next run deletes roots below the floor, and lines 41-42 say only checkpoints exist there. Three kinds of non-checkpoint root can sit below the floor with no segment line:
  - every root older than `since_seq`, which lines 159-160 say is never expired;
  - a root skipped by the age test, because `created_at` is monotone only within an epoch, so step 1's candidate set can have a hole;
  - a root re-created at an expired `seq` by a writer with a stale base (Major 9).

  Deleting any of them removes a version with no record, against Goal 2 and H2.
* **Rationale & Recommendation:** Line 220: "The next run deletes a root only when the SHA-256 of its stored bytes equals the `root_sha256` of its line in a segment reachable from `HISTORY`. Any other root below the floor is reported and kept." Apply the same check in step 5. Make step 1 choose a contiguous prefix by `seq`. Redefine the floor in Terms: "the highest expired `seq`. Every root above it exists. Below it are checkpoints and the roots older than `history.since_seq`."

#### 5. `catalog.json` 2.0 locks out old writers and leaves old readers reading - Severity: Blocker (new in revision 2)

* **Reviewer Lens:** design (storage) N2; zoom-out M1 (rated Major there)
* **Affected Scope:** lines 154-158, 224-235, 389, 417-422, 489, Question 1
* **Discrepancy Description:** Line 156 says "neither an old reader nor an old writer can open an expiring catalog". The writer half holds: `try_commit` decodes `catalog.json` on every commit (statcatlib `store/inventory.py:317, 426`), and `decode_catalog` refuses another major (sdmxlib `_format.py:268-290`). The reader half is false. `_Chain.refresh` reads only `CURRENT` and roots (`_reader.py:119-155`), and sdmxlib-rest's `src/` never reads `catalog.json`. An old pod with `CURRENT` missing probes from 1, reads checkpoint 1, finds root 2 expired and serves version 1. An old pod whose `CURRENT` names a bad root walks back to a month-old checkpoint. That is round-1 B3 for every pod not yet upgraded, guarded only by the deployment order at line 235.
* **Rationale & Recommendation:** Correct line 156 and risk row 389 to say the 2.0 document locks out writers. Then close the reader gap. The reviewers offered two routes:
  - **(a) Ship the reader change in stage 1** (zoom-out). When `CURRENT` is missing, the reader fetches `inventory/HISTORY`, and a 404 means floor 0. This changes nothing on a catalog that never expires, so it can deploy before any opt-in, which the plan already requires of format changes (`sharded-bundle-catalog-plan.md:153`). Make sdmxlib-rest's pin a checked precondition of the first expiry.
  - **(b) Give opted-in roots a new Inventory major** (storage), so old pods fail closed (`_format.py:274-276`). This is a hard cutover for every pod on every new root.

  This report recommends (a) with the checked precondition, and keeping (b) as the fallback if the precondition cannot be checked.

#### 6. Expiry's leaf deletion is safe only under a lock that does not exist - Severity: Blocker (round-1 B4, still open)

* **Reviewer Lens:** design (storage) B4r; zoom-out M4 (rated Major there)
* **Affected Scope:** lines 195-198, 211-214, 388, 453, 461-476, 490, Question 2
* **Discrepancy Description:**
  - No lock appears in statcatlib's `src/`. Writers serialise by create-exclusive alone (`store/EGM.md:353-365`), and local writers race by design (`tests/test_concurrent_seal.py`). "`prune` holds the writer's lock" does nothing unless `InventoryWriter.commit` takes it too, and the statcatlib Handoff does not list a lock.
  - Step 6's recreate misses a race. A writer that finds a leaf present skips writing it (`store/inventory.py:339-344`), then writes its root (`:432`). If expiry deletes the leaf and re-reads the head before that root exists, the new head names a missing leaf, and every read of the product fails (`_reader.py:181-184`).
  - Expiry holds deleted bytes only in memory, so a crash in step 6 cannot recreate them.
  - On a server, the single writer depends on scheduling. `concurrencyPolicy: Forbid` covers only CronJob-created jobs; a manual job or an operator's `CatalogAdmin` call with the release job's identity runs beside it (Kubernetes semantics, unchecked in code).
* **Rationale & Recommendation:** Both reviewers agree that the recreate step is insufficient and that a lock must be added. They differ on the rest:
  - **Exclusion** (zoom-out). Writers and `prune` take one catalog lock locally; on a server, the design states that the release job runs one instance at a time with expiry inside that run. Step 6 becomes "Delete leaves that no retained root names", and the recreate is dropped.
  - **Grace period** (storage). Step 6 deletes a leaf only if no root read after step 5 names it and its `Last-Modified` is older than G (default 24 h), as `prune` already does for `data/` (`admin.py:715-719`). Keep the recreate as a backstop for reused leaves. An expiry-only lock (a file lock locally, a blob lease on `HISTORY` on blob storage) serialises runs.

  This report recommends exclusion as the rule, because a reused leaf is old by any timestamp, so a grace period cannot protect it. Add a blob lease on `HISTORY` as the server's expiry lock, so a stray second run fails. In both routes, write the planned deletions into the segment header before step 5, add the lock to the statcatlib Handoff, and add a conformance case where a seal races `prune`.

### Major: storage and safety

#### 1. Restore epochs are not carried through `HISTORY`, segments and IRIs - Severity: Major

* **Reviewer Lens:** design (storage) M1, design (PROV-O) M1 and M2, zoom-out m6
* **Affected Scope:** lines 39-40, 172-191, 226-229, 276-288, 390
* **Discrepancy Description:**
  - `HISTORY` has no epoch and is forward-only, so a restore below the floor cannot reset it.
  - One run's segment can span two epochs, but its header names one.
  - Segment order across epochs is undefined once old-epoch segments are appended after a restore.
  - A restore deletes the change lists of lost versions that expiry had not reached (`restore_to`).
  - With `CURRENT` missing, today's reader assumes epoch 0 (`_reader.py:128, 146`).
  - The conformance suite models a restore that keeps the epoch (`conformance.py:110-112`), which reuses `(epoch, seq)` in segment names and IRIs. Line 186's claim holds only for restores that bump the epoch.
  - `CatalogAdmin.export` keeps `catalog_id` (§6.1 line 333), and line 277's configurable base gives one thing two IRIs.
* **Rationale & Recommendation:**
  - Add `restore_epoch` to `HISTORY`, forward-only within an epoch.
  - Write one segment per epoch a run expires from.
  - Use one global segment chain (`previous_segment` is `HISTORY.newest_segment` at write time).
  - Require every restore to bump the epoch, and to write the roots it discards into an old-epoch segment first.
  - Take the epoch from `catalog.json` or `HISTORY` when `CURRENT` is missing.
  - State whether an export keeps its source's `catalog_id`.
  - Fix the IRI base.

#### 2. The reader's floor rule misses three cases - Severity: Major

* **Reviewer Lens:** design (storage) M6
* **Affected Scope:** lines 41-42, 226-229
* **Discrepancy Description:** §6.6 step 4 already uses "floor" for the `seq` a reader holds (`_reader.py:129`). A pod holding a root at or below `HISTORY.floor` probes from an expired `seq` and stays stale. A 2.x catalog whose `CURRENT` and `HISTORY` are both missing makes the reader probe from 1. The design does not say when the reader reads `HISTORY`.
* **Rationale & Recommendation:** Rename the field `expired_through`. The reader reads `HISTORY` only when `CURRENT` is missing or bad, walks back to and probes from `max(held seq, expired_through)`, drops a held root at or below it, and fails closed when nothing is found. Opt-in writes `HISTORY` with `expired_through: 0`.

#### 3. Segment naming and recovery from a crash between steps 3 and 4 - Severity: Major

* **Reviewer Lens:** design (storage) M2
* **Affected Scope:** lines 172, 185, 208-209, 218-219
* **Discrepancy Description:** "The next run finds the same segment" works only if it picks the same `<first>-<last>`. A different range leaves a permanent orphan, and the same range collides with different header bytes, so expiry stalls. Locally `HISTORY` has no conditional replace (`CURRENT` uses read, compare, rename at `store/inventory.py:346-363`).
* **Rationale & Recommendation:** Name segments `history/<epoch>/<first:012d>-<last:012d>-<uuid7>.jsonl`. Expiry LISTs `history/<epoch>/` and adopts or reports a segment `HISTORY` does not name. `verify-catalog` reports unlinked and overlapping segments. Define the line bytes. Take the expiry lock around steps 3 to 5.

#### 4. Segment lines are bound only by the segment chain - Severity: Major

* **Reviewer Lens:** design (storage) M3
* **Affected Scope:** lines 68-69, 180-185, 230-233, 243, 391, 457
* **Discrepancy Description:** A line drops `products` and `retired`, so `root_sha256` cannot be recomputed from it. After the root is deleted, only `previous_segment_sha256` and `HISTORY.newest_segment_sha256` detect an edit. The release job's identity can overwrite blobs it can write, so "never rewritten" is a code rule, and the identity keeps the permission.
* **Rationale & Recommendation:** Goal 2 becomes "from one trusted root hash and one trusted segment hash". The release job publishes the pair. Step 3 checks each line's `root_sha256` before step 5. Recommend object lock on `history/` for servers, and say in the risk table what happens without it.

#### 5. Clocks: expiry's "now", forward skew and the checkpoint test - Severity: Major

* **Reviewer Lens:** design (storage) M5, design (PROV-O) Minor 4
* **Affected Scope:** lines 33-35, 128-130, 200-204, 330
* **Discrepancy Description:** Step 1 does not name the clock it compares against. A writer clock running behind ages the previous root early. A clock months ahead pins `created_at` there through the +1 ms rule, so no monthly checkpoint appears until real time catches up. The checkpoint test needs root N-1's `created_at`, which may be in a segment.
* **Rationale & Recommendation:** Take expiry and server writer time from the storage `Date` header under §6.4's skew bound. A writer refuses a base more than a bound (for example 5 minutes) ahead of its clock. State the checkpoint rule exactly: N is a checkpoint when N = 1, N = `since_seq`, the epoch differs from N-1's, or the UTC month of `created_at[N]` is later than N-1's. `verify-catalog` recomputes it.

#### 6. Backup copy order - Severity: Major

* **Reviewer Lens:** design (storage) M7
* **Affected Scope:** lines 249-250, 441
* **Discrepancy Description:** A backup that copies `history/` before roots while expiry runs captures neither the deleted roots nor their segment lines.
* **Rationale & Recommendation:** §10.3 order: `data/`, edition directories, leaves, roots, `inventory/HISTORY`, `history/`, then `CURRENT`. A restore never deletes or overwrites under `history/`.

#### 7. W's bounds and the GC walk - Severity: Major

* **Reviewer Lens:** design (storage) M8
* **Affected Scope:** lines 202-204, 442-443
* **Discrepancy Description:** "W ≥ backup retention" adds nothing, since §11.6 already orders backup retention at or below the GC window (spec line 768). "W ≥ GC window" needs one clock and a margin. Round-1 Major 2 asked that GC fail closed on a missing root, and the Handoff omits it. The pod bound at line 204 holds trivially; the pod-staleness alert (spec line 774) gives the useful bound.
* **Rationale & Recommendation:** §11.6: W ≥ `data/` GC window + 1 day, in storage time; the staleness alert fires below W; GC stops at `expired_through` and fails closed on a missing root above it.

#### 8. "Rebuild from change lists" is an unstaged capability - Severity: Major

* **Reviewer Lens:** zoom-out M6
* **Affected Scope:** lines 244, 438
* **Discrepancy Description:** The Handoff asks for a §6.7 amendment that no Goal and no stage covers. `rebuild-inventory` is unbuilt Phase 9 work. A replay of `retired` also diverges once tombstones age out (Nit 11).
* **Rationale & Recommendation:** Keep line 244 as a statement of what the data allows, and drop §6.7 from the sdmxlib Handoff.

#### 9. Expiry reopens create-if-absent for expired names - Severity: Major

* **Reviewer Lens:** design (storage) M9
* **Affected Scope:** lines 141-147, 185, 210
* **Discrepancy Description:** After root N is deleted, a writer whose base is N-1 (a laptop resumed after a long sleep, or a direct `try_commit` call) creates N again (`store/inventory.py:432`), forking below the floor.
* **Rationale & Recommendation:** "A 1.1 writer on a 2.x catalog refuses a base at or below `HISTORY.expired_through`." Blocker 4's delete check keeps such a root.

### Major: format and scope

#### 10. `entry` as the full `LeafEntry` carries `artefacts` and `structure_source`, so the size figures are low - Severity: Major

* **Reviewer Lens:** zoom-out M3
* **Affected Scope:** lines 119, 134-136, 393
* **Discrepancy Description:** `LeafEntry`'s optional `structure_source` and `artefacts` (§6.3 lines 379-380; `_format.py:219-220`) dominate a structure product's entry. The 450-byte and 3.2 MB figures assume both are absent. No Goal needs them, since `manifest_sha256` pins them.
* **Rationale & Recommendation:** Define `entry` as the `LeafEntry` without those two fields, or keep them and state the worst-case size. Optionally drop `to` where `entry` is present.

#### 11. The PROV-O section is stage-3 material, and its linked example does not parse - Severity: Major

* **Reviewer Lens:** zoom-out M5, design (PROV-O) M8 and Minor 2
* **Affected Scope:** lines 254-321, 406, 412-413, 458; round-1 `prov_o_report.md` lines 96-154
* **Discrepancy Description:**
  - The section runs 68 lines of informative vocabulary, IRIs and a PREMIS crosswalk that stage 3 will redo, and it lists `stc:Search`, a kind that does not exist (`_format.py:41-43`).
  - The linked Turtle example uses unescaped `/` and U+2026 in prefixed names, which Turtle 1.1 rejects.
  - The example has drifted from revision 2: it adds `prov:used`, sets `stc:kind` on a known kind, generates a leaf, and gives `stc:rootSha256` as a literal.
  - The sdmxlib acceptance list (line 458) includes this example.
* **Rationale & Recommendation:** Keep H7 and a field-to-PROV-term table, which is what Goal 4 needs now. Move the term list, IRI table and example to the stage-3 design, or fix the example and carry it in the spec PR, tested with rdflib. Drop `stc:Search` and the PREMIS crosswalk, or fix the crosswalk (Nit 14). Move the hub namespace reservation to stage 3.

#### 12. The mapping's agent, leaf and membership rules break PROV constraints or drift with expiry - Severity: Major

* **Reviewer Lens:** design (PROV-O) M3, M4, M5, M6
* **Affected Scope:** lines 286, 296-300
* **Discrepancy Description:**
  - The unqualified `prov:actedOnBehalfOf` from a shared PyPI producer IRI accumulates delegations across all actors, and nothing records which delegation held in which activity.
  - A content-addressed `ni:` leaf can be put back by a correction or restore. It then gets a second generation and a revision cycle.
  - "Each leaf it changed (every leaf when exported from a retained root)" gives one version two graphs depending on expiry.
  - The table never says a state entity is `prov:specializationOf` its edition, which H7 rests on.
* **Rationale & Recommendation:** If the section stays (Major 11):
  - Use `prov:qualifiedDelegation` with `prov:hadActivity`.
  - Model a leaf-in-version entity that specializes the `ni:` bytes, or assert no generation or revision on `ni:` entities.
  - Emit `stc:changedMember` deterministically, and derive full membership by replay as an option.
  - Add the `prov:specializationOf` link to row 300.

#### 13. The staging puts the reader change too late and ties stage 1 to Phase 5 - Severity: Major

* **Reviewer Lens:** zoom-out M1 and m7
* **Affected Scope:** lines 415-426
* **Discrepancy Description:** Stage 1 needs only an sdmxlib release and statcatlib's local writer, while the release job is Phase 5 (`sharded-bundle-catalog-plan.md:57, 175`). The reader's `HISTORY` fallback changes nothing on a catalog that never expires, so it can ship first (blocker 5).
* **Rationale & Recommendation:** Stage 1: format 1.1, the writer rules and the reader's `HISTORY` fallback, with the next sdmxlib and statcatlib releases and sdmxlib-rest's pin. Stage 2: opt-in and expiry, local first, server with the Phase 5 release job. Stage 3: export.

### Nits

1. **Line 300 reads backwards** (PROV-O Minor 1). `prov:wasInvalidatedBy` runs from entity to activity; rewrite the row with the state entity as subject.
2. **`reinstate` has no event kind and no statcatlib caller** (PROV-O Minor 2; `_rules.py:425-461`), yet lines 124 and 306 rely on it. Name the kind it records, and the kind of a server fold of `pending/`. Give the kind-to-class rule.
3. **`retired` as a state** (lines 118, 270, 305) contradicts spec §6.4 line 424, "Retirement is a tombstone, never a state." Amend the spec sentence in sdmxlib#361.
4. **Times** (PROV-O Minor 5). State that state entities take `created_at`, never `state_changed_at`, and that activities carry no start or end time.
5. **IRI minting details** (PROV-O Minor 6, lines 281-288). Lowercase `urn:uuid`, unpadded base64url for `ni:`, uppercase percent-encoding, a rule for producer version `"unknown"` (`store/inventory.py:210`). The local actor `<os user>@<hostname>` (`store/inventory.py:214-220`) puts personal data in IRIs; note it under Embargo and access.
6. **`describe` and `embargo-change` versions have empty change lists** (`admin.py:483, 514`). Map `embargo` and the `describe` extension digest, and define which bytes the "`extensions` digests" (line 182) hash.
7. **"Never invalidated"** (line 299). GC and `expunge` delete an edition's bytes without an Inventory version (§11.3 lines 750-752). Phrase it as an export rule. Add an informative `stc:Expiry` row for the segment header's `expired_at` and `actor`.
8. **H7 and line 380 wording** (PROV-O Minors 10, 11). Name PROV-CONSTRAINTS' unique-generation and unique-invalidation. Reword line 380 to "An entity's attributes describe its fixed aspects (PROV-DM §5.1.1)".
9. **`since_seq` definition** (storage Minor 5). Define it as the lowest `seq` from which every root is 1.1, refuse opt-in otherwise, and amend §6.1 line 328, which allows a `catalog.json` rewrite only to bump the epoch.
10. **Expiry step 2 cost and step 7 order** (storage Minors 1, 2, 4). Step 2 reads every retained root each run; verify only the candidates and the two boundary links, and leave the full walk to `verify-catalog`. Log the plan before deleting, include `leaves` in the header, and cap segment size (a first expiry over a year is about 330 MB).
11. **Checkpoints are audit-only, and tombstone ageing is unrecorded** (storage Minors 3, 6). An old checkpoint's leaves can name manifests GC deleted; label checkpoints audit-only. Tombstones that leave `retired` produce no change item.
12. **Simplifications** (zoom-out m1-m5). The version-1 checkpoint is `since_seq` or the first of epoch 0, so the rule has two kinds plus `since_seq`. State that `floor` equals the newest segment's `last`. `catalog_id` in each root has no consumer; keep it in the segment header only. `verify-catalog`'s check 3 is check 1 over the union of roots and lines. Line 94 says "optional" for fields line 99 calls required.
13. **The embargo filter** (PROV-O Minor 15, line 251). A live-only export drops the embargoed state's invalidation; say so, so the embargoed state's IRI does not leak.
14. **DCAT join and PREMIS** (PROV-O Minors 12-14). No repository mints `<base>product/<product_id>` as a `dcat:Dataset` IRI; add the rule and reserve `/id/`. The PREMIS crosswalk lacks the mandatory `eventIdentifier` and `linkingObjectRole`. Declare `stc:reason` an `owl:AnnotationProperty` and give the vocabulary an `owl:versionIRI`.

## Recommended answers to the Questions for review

1. **`catalog.json` 2.0 or a root major?** Keep `catalog.json` 2.0 as the opt-in and the writer lock-out. It does not reach readers (blocker 5). Ship the reader's `HISTORY` fallback in stage 1 and make sdmxlib-rest's pin a checked precondition of the first expiry. A root major is the fallback if that check cannot be built. The storage and zoom-out reviewers each offered one of these two routes.
2. **Is H5 enough, or does step 6 need a grace period?** H5 alone is not enough: locally no lock exists, and on a server the single writer depends on scheduling. The reviewers split on the fix (blocker 6). This report recommends writer exclusion (a lock both `commit` and `prune` take locally, and a blob lease on `HISTORY` for server expiry), because a grace period cannot protect a reused leaf.
3. **Does K = 10 fit a 5 s poll?** Yes. The storage and zoom-out reviewers agree that the poll bounds W and leaves K unconstrained. K = 10 keeps one to three days for the fallback walk. Close the question, and add that the pod-staleness alert fires well inside W.

## Recommended edits

1. Base `previous_root_sha256`, `changes` and the `created_at` rule on root `seq - 1`; keep `previous_inventory` as "built from" (blocker 1).
2. Drop `from_seq`, or add `state_seq` and `state_epoch` to `LeafEntry`; owner's choice before sdmxlib#361 merges (blocker 2).
3. Rewrite line 299 so the Inventory export asserts no generation for an edition (blocker 3).
4. Delete a root only after matching its bytes to a linked segment line; choose candidates as a contiguous prefix; redefine the floor (blocker 4).
5. Correct the lock-out claim; move the reader's `HISTORY` fallback and sdmxlib-rest's pin into stage 1; gate the first expiry on the pin (blocker 5, Major 13).
6. Add a catalog writer lock to statcatlib's Handoff, drop or demote step 6's recreate, and write planned deletions before step 5 (blocker 6).
7. Add `restore_epoch` to `HISTORY`, one segment per epoch, one global segment chain, and require every restore to bump the epoch (Major 1).
8. Rename the floor `expired_through` and specify when the reader reads `HISTORY` (Major 2).
9. Add a unique suffix to segment names, and fix the backup order and W's bounds in §10.3 and §11.6 (Majors 3, 6, 7).
10. Trim `entry`, cut the PREMIS crosswalk and `stc:Search`, move the IRI table and the example to stage 3 or fix the example, and drop §6.7 from the Handoff (Majors 8, 10, 11).

## Verify before citing

- PROV-CONSTRAINTS: the names and numbers of unique-generation and unique-invalidation (about Constraints 24-25), generation-precedes-invalidation, the specialization ordering constraints, whether derivation-generation-generation-ordering is strict, whether constraints apply per bundle, and whether time values take part in validity.
- PROV-O: the domain of `prov:hadRole`; whether §3.3 recommends the unqualified triple beside the qualified one; `prov:qualifiedDelegation` and `prov:hadActivity` on `prov:Delegation`.
- PROV-DM §5.1.1: the "fixed aspects" wording behind line 380.
- DCAT 3: whether `dcat:previousVersion` is a sub-property of `prov:wasRevisionOf`, and `dcat:hasVersion` of `prov:hadRevision`. Revision 2 no longer cites this; check whether the spec does.
- PREMIS 3.0 Data Dictionary: `eventIdentifier` (mandatory), `eventType`, `eventDateTime`, `eventDetailInformation/eventDetail`, `linkingAgentIdentifier/linkingAgentRole`, `linkingObjectIdentifier/linkingObjectRole`; whether the LoC eventType vocabulary has release or rollback terms; whether PREMIS-OWL aligns `premis:Event` with `prov:Activity`.
- OWL 2 DL status of `rdfs:subPropertyOf rdfs:comment`.
- RFC 6920 §3: `ni:///sha-256;<val>` with an empty authority and unpadded base64url.
- RFC 9562: lowercase `urn:uuid`.
- Turtle 1.1: `PN_LOCAL` requires `\/` for a slash and excludes U+2026. Test with rdflib.
- Kubernetes: whether `concurrencyPolicy: Forbid` covers manually created jobs.
