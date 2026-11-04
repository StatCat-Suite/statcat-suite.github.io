# Storage and safety review, round 2: Inventory change lists and history segments

**Target:** `docs/design/inventory-history-log.md`, revision 2 (516 lines). Line numbers below refer to this file.
**Lens:** `egm-design`, storage and safety. Mode REVIEW, round 2.
**Result:** 3 Blocker, 9 Major, 6 Minor. Of round 1's seven blockers, B1, B5 and B6 are closed, and B2, B3, B4 and B7 are partly closed. Revision 2 introduces two new blockers (N1 and N2). The third blocker is the part of B4 that is still open.

## What was read

The reviewer had no shell, so it could not run `git rev-parse`. Every `file:line` below is from the working tree at the path shown. The design cites the commits listed here. The reviewer could not confirm that each checkout is at its cited commit, and round 1 found sdmxlib and statcatlib on feature branches. Nothing read contradicts the design's description of the code: Inventory format 1.0, the reader in `_reader.py`, and the writer in `store/inventory.py`.

- **Hub:** the target; `CLAUDE.md`; round-1 `review_report.md` and `design_storage_report.md`; the egm persona `agents/design_critic.md`.
- **sdmxlib** (cited `b6c79892`):
  - `docs/design/sharded-bundle-catalog.md` §6.1-6.7 (lines 320-515), §10.1-10.3 (691-718), §11.4 and §11.6 (754-772);
  - `src/sdmxlib/inventory/EGM.md`, `_reader.py`, `_format.py`, `_rules.py:471-530`, `conformance.py`;
  - `tests/support/inventory_backends.py:154-169`.
- **statcatlib** (cited `95fd7ad`): `src/statcatlib/store/EGM.md`; `src/statcatlib/store/inventory.py:1-30, 315-484`; `src/statcatlib/admin.py:515-764` (`prune`); `src/statcatlib/diagnostics.py:303-353`; `tests/test_inventory_conformance.py:120-160`.
- **sdmxlib-rest** (cited `f1582e4`): a search of `src/` and `tests/`. `src/` names neither `catalog.json` nor `decode_catalog`. `tests/test_inventory_describe.py:19-27, 92` reads through `LiveInventory`.
- **Not read, so these claims are unverified:** the server GC job (§11.4 describes it, and the reviewer found no implementation) and the release job (Phase 5, unbuilt).

## Round-1 blocker status

| Round-1 blocker | Review response (lines 487-493) | Status | Reason |
| --- | --- | --- | --- |
| B1 orphan record race | H1: the root is the record | **Closed** | No second compare-and-swap object exists. The change list lives in the root, which is the commit point (lines 141-147). One problem remains: the chain follows `previous_inventory`, which can skip a version (M4). |
| B2 restore reuses `seq` | Epoch-keyed segments, `previous_root_sha256`, epoch in IRIs | **Partly closed** | Segment names cannot collide across epochs. Five things are still open: `HISTORY` has no epoch and is forward-only, so a restore cannot reset it; one run's segment can span two epochs; segment order across epochs is undefined; a restore discards the change lists of lost versions that were never expired; and the reader takes the wrong epoch when `CURRENT` is missing (M1). |
| B3 reader stops at gaps | Floor in `HISTORY`, reader change, `catalog.json` 2.0 | **Partly closed** | The new reader is specified. `catalog.json` 2.0 does not lock out old Inventory readers, because the reader never reads `catalog.json` (N2). The floor rule also misses three cases: a held `seq` below the floor, an absent `HISTORY`, and the epoch (M6). |
| B4 expiry races writers on leaves | Single writer on the server, the lock locally, step 6 re-read | **Partly closed** | "The writer's lock" does not exist in statcatlib, and the design never says that writers take it. Step 6's re-read misses a root written after the re-read. On a server, the single writer is a scheduling convention (B4r). |
| B5 escape route | H9 and §6.6 amendment | **Closed** | The review is done and recorded (lines 337-361). This is outside the lens, apart from the trigger list. |
| B6 untestable normative mapping | H8 informative | **Closed** | This is outside the lens. The data is normative now. |
| B7 no migration | H6 opt-in, `since_seq` | **Partly closed** | Opt-in and `since_seq` exist. The Terms definition of the floor (lines 41-42) and the crash rule (line 220) contradict "roots below `since_seq` are never expired" (lines 159-160) (N1). `since_seq` is ill-defined when an old writer wrote 1.0 roots after the first 1.1 root (Minor 5). |

## Blockers

### N1 (new). The crash-recovery rule deletes roots that no segment records (lines 41-42, 159-160, 218-220)

Line 220 says that after a crash past step 4 "the next run deletes" the roots below the floor. Lines 41-42 say "only checkpoints exist below it". Both statements are wrong for three kinds of root:

- **Roots older than `since_seq`.** They sit below the floor once the first expiry has run. They are not checkpoints, and lines 159-160 say they "are never expired". Read literally, line 220 deletes every 1.0 root of an opted-in catalog the first time a run follows a crash, with no segment line for any of them.
- **Roots left by an out-of-order age test.** `created_at` is monotone only within an epoch (line 128). A restore root can therefore carry an earlier `created_at` than its predecessor. The age rule in step 1 then picks a candidate set with a hole in it, which leaves a retained non-checkpoint root below the highest expired `seq`.
- **A root written at an expired `seq` by a writer whose base is stale.** Expiry frees names that create-if-absent then lets a writer reuse (M9).

A root deleted under line 220 with no segment line is a version removed with no record. That breaks Goal 2 and H2.

**Recommended edits:**

- Replace line 220: "A crash after step 4 leaves roots that a linked segment records. The next run deletes a root only when the SHA-256 of its stored bytes equals the `root_sha256` of its line in a segment reachable from `HISTORY`. Any other root below the floor is reported and kept."
- Apply the same condition to step 5: "Delete each candidate root after checking its bytes against its segment line."
- Fix the Terms entry for the floor: "Floor: the highest expired `seq`. Every root above it exists. Below it are checkpoints and the roots older than `history.since_seq`."
- Make step 1 pick a contiguous prefix by `seq`: "Candidates are the roots from the floor + 1 upward, stopping at the first root that is not a checkpoint and fails the age or K rule."

### N2 (new). `catalog.json` 2.0 does not lock out old Inventory readers (lines 154-158, 389, 489, Question 1)

Line 155 says "sdmxlib readers before this release refuse a 2.x catalog document (§6.1), so neither an old reader nor an old writer can open an expiring catalog." The writer half holds. statcatlib's `try_commit` calls `catalog_document()` (`store/inventory.py:426`), and `decode_catalog` refuses another major version (`sdmxlib/inventory/_format.py:268-290`). The leaves are already written by line 415 when that refusal fires.

The reader half is false. `_Chain.refresh` reads only `CURRENT` and roots (`_reader.py:119-155`), and nothing in `sdmxlib/inventory` outside `_format.py` calls `decode_catalog`. sdmxlib-rest reads through `LiveInventory` and never opens `catalog.json`. A pod on an old pin behaves like this on an expiring catalog:

- **`CURRENT` missing, fresh pod:** it probes from `seq` 1 (`_reader.py:128-148`), reads checkpoint 1, finds the next root expired, and serves version 1.
- **`CURRENT` naming a root whose hash mismatches:** it walks back past the gap to the newest checkpoint below it (`_reader.py:131-136`, `while found is None and seq > floor` with floor 0), then probes one step forward and stops.

This is round-1 B3 for every pod not yet upgraded, and line 235 guards it only by a deployment procedure.

**Recommended edits (the opt-in itself stays):**

- Correct lines 155-158 and risk row 389 to say that `catalog.json` 2.0 locks out writers, and that old readers keep reading.
- Then pick one of these:
  - **(a)** The roots of an opted-in catalog carry an Inventory major version that old readers refuse: `decode_root` refuses another major (`_format.py:274-276`). An old pod then fails closed with "no valid Inventory version" and never serves a stale checkpoint. This is Question 1's alternative, added to the `catalog.json` gate, and the reviewer recommends it.
  - **(b)** Make the pin a checked precondition. The release job refuses its first expiry until the catalog's reader deployments report the new sdmxlib version, and the design names where that report lives.

### B4r (round-1 B4, still open locally). The local lock does not exist, and step 6 does not cover the race (lines 196-198, 211-214, 388, 490)

- **No lock exists.** Nothing in `src/statcatlib` uses `flock`, `fcntl` or a lock file. The only matches are a `threading.Lock` in `store.py` and unrelated text. The writer serialises by create-exclusive alone (`store/EGM.md:353-365`), and local writers race by design (`tests/test_concurrent_seal.py`, per `store/EGM.md:409`). "Prune holds the writer's lock" serialises nothing unless every `InventoryWriter.try_commit` takes the same lock, and the design does not say that it does.
- **Step 6 misses some roots.** A writer creates a new leaf at `store/inventory.py:415` and the root at `:432`. If expiry deletes the leaf in between and re-reads the head before `:432`, nothing recreates the leaf, and the new head names a missing leaf. Every read of that product then fails (`_reader.py:181-184`).
- **A crash in step 6 loses data.** Expiry holds the bytes of the deleted leaves only in memory, so after a crash it cannot recreate them.
- **The server's single writer is a convention.** Expiry is safe there only while no other process writes with the release job's identity. `concurrencyPolicy: Forbid` (§11.2 item 4, spec line 738) governs only the jobs that the CronJob controller creates. A manually created job, or an operator's `CatalogAdmin` call with the release job's identity, runs beside it. (This rests on Kubernetes semantics, which the reviewer did not check in code.)

**Recommended edits:**

- Add a grace period to step 6 (see the answer to Question 2). It closes the race on both the server and locally without a lock.
- Add a catalog lock that expiry and `prune` take. This is a file lock under the catalog directory locally, and a blob lease on `inventory/HISTORY` on blob storage. It serialises one expiry run against another, which the `HISTORY` write needs (M2).
- Log ahead: write the planned leaf and root deletions before step 5, as part of the segment header or a deletion log, so that a crash in step 5 or 6 can resume.

## Major

### M1. Restore epochs are not carried through `HISTORY`, segments and the reader (lines 39-40, 100, 128, 172-191, 226-229, 390)

**What the spec and code do today.** `restore_epoch` is an integer in `catalog.json`, starting at 0. A whole-catalog restore or failover bumps it (spec lines 334, 718). Every root and `CURRENT` record it (spec lines 336, 347). A reader resets its `seq` floor when it changes (spec line 493; `_reader.py:128-129, 146, 152`).

The conformance restore loses the roots after S, bumps the epoch, and writes a `restore` root S+1 built from root S. `seq` continues from S+1 (`tests/support/inventory_backends.py:154-169`; statcatlib `tests/test_inventory_conformance.py:136-149`). No statcatlib command performs a restore. §10.3 says "a restored Inventory version is never made current".

**Gaps in the design:**

1. **`HISTORY` has no epoch, and it is forward-only (line 189).** An operator who restores to a root S below the floor (an older consistent root) needs the floor moved back to S. The forward-only rule forbids that. A reader with `CURRENT` missing then probes from the old floor + 1, finds nothing, and the catalog cannot be read.
   *Edit:* `HISTORY` is `{restore_epoch, floor, newest_segment, newest_segment_sha256}`. It is forward-only within an epoch, and a restore writes it with the new epoch and floor = the restored head.
2. **One segment per run (line 172) can mix epochs.** A run can expire old-epoch roots and new-epoch roots together, but a header carries a single `restore_epoch`.
   *Edit:* "A run writes one segment per epoch it expires from. A segment holds roots of one `restore_epoch` and sits under that epoch's directory, even when it is written in a later epoch."
3. **Segment order across epochs is ambiguous.** After a restore, later runs still append epoch e-1 segments, which contradicts the "first segment of an epoch links to the previous epoch's last" rule (lines 177-179).
   *Edit:* use one global chain. `previous_segment` is `HISTORY.newest_segment` at the time of writing, whatever its epoch.
4. **A restore loses most of the record of the versions it discards.** The lost versions that expiry had not reached are deleted with their change lists (`restore_to` unlinks them). Only the expired lost versions survive in segments, so line 186 ("cannot touch the history of the lost versions") holds only for the oldest ones.
   *Edit:* an in-place restore first writes the roots it discards into a segment of the old epoch. A restore never deletes or overwrites under `history/`. Say this in §10.3.
5. **The reader takes the wrong epoch when `CURRENT` is missing.** With no `CURRENT` and no held root, `epoch` is 0 (`_reader.py:128`), and later roots of epoch 1 are skipped (`_reader.py:146`). The reader then returns the last epoch-0 root. This defect already exists in today's reader, and the new path at line 228 inherits it.
   *Edit:* "With `CURRENT` missing, the reader takes the epoch from `catalog.json`, which it reads anyway to know the catalog is 2.x, or from `HISTORY`."
6. **`previous_root_sha256` after a restore** (line 100) matches the code: root S+1 hashes root S, which is in the old epoch. The cross-epoch link then verifies only while root S or its segment line exists. Say that root S's line goes under `history/<e-1>/` (item 2).

### M2. Segment naming and the crash between steps 3 and 4 (lines 172, 185, 208-209, 218-219)

Line 219 says "The next run finds the same segment". A reader cannot do that without a LIST. Expiry can only if the next run picks exactly the same `<first>-<last>`. When it picks different candidates (newer roots aged in, or K or W changed), it writes an overlapping segment, and the orphan stays forever because nothing under `history/` is ever deleted.

When it picks the same range, create-if-absent fails. The header bytes differ (`expired_at`, `actor`), so the run must compare lines. If the orphan's lines do not match, the run can never write that name again, and expiry stalls with no way out.

The `HISTORY` write is conditional on blob storage. Locally there is no conditional replace: `CURRENT` uses read, compare, rename (`store/inventory.py:346-363`). Two local runs could move `HISTORY` backwards and fork the segment chain.

**Recommended edits:**

- Name a segment `history/<epoch>/<first:012d>-<last:012d>-<uuid7>.jsonl`, with the 12-digit padding `root_path` uses (`_format.py:250`).
- Say that expiry LISTs `history/<epoch>/` (it LISTs `inventory/leaves/` already for step 6). It verifies a segment that `HISTORY` does not name and either adopts it by setting `HISTORY` to it or reports it as an orphan. `verify-catalog` reports unlinked and overlapping segments.
- Define the line bytes: compact msgspec JSON, in the root's field order, with one `\n`.
- Locally, take the expiry lock (B4r) around steps 3 to 5.

### M3. After expiry, segment line content is bound to nothing (lines 68-69, 180-184, 230-233, 391, 457)

A segment line drops `products` and `retired`, so `root_sha256` cannot be recomputed from the line. Once the root is deleted, an edit to a line's `changes` or `event` leaves every root-chain link intact. Only the segment hash chain detects it: `previous_segment_sha256` and `HISTORY.newest_segment_sha256`.

The release job's identity can write `HISTORY` and, on Azure, overwrite any blob it can write. RBAC write includes overwrite (round-1 M3), so "segments are never rewritten" (lines 185, 391) is a rule the code follows, and the identity still holds the permission to break it.

Goal 2 ("from any one trusted root hash forward") and acceptance line 457 ("an edited segment line ... detected") therefore hold only with an anchor outside the catalog that covers the segment chain.

**Recommended edits:**

- Goal 2: "from one trusted root hash and one trusted segment hash".
- The hash the release job publishes outside the catalog (line 243) is the pair (newest root SHA-256, newest segment SHA-256).
- Step 3: expiry writes each line from the root's decoded bytes and checks `root_sha256` before step 5 (N1).
- Make object lock on `history/` the recommended server configuration. State in the risk table that the release job's identity can overwrite `history/` without it.

### M4. The chain follows `previous_inventory`, which can skip versions (lines 29-30, 100-101, 128-132)

Line 100 defines `previous_root_sha256` as the hash of root `previous_inventory`. sdmxlib lets a correction build from an older version (`_rules.py:481, 495-496, 511`; `_format.py:138-140`: "a correction builds from an older, known-good one"). With 41 built from 39, nothing links to root 40. Deleting or editing 40 is then invisible to the chain.

Three statements also disagree:

- line 101: the change list is relative to `previous_inventory`;
- lines 131-132: it is relative to "the version it re-evaluates its preconditions against", which is the head, seq-1 (spec line 486);
- line 128: `created_at` is monotone with `seq`, enforced against "the base", which for a correction is older than seq-1.

statcatlib does not use `built_from` today; a search found it only in `_rules.py`.

**Recommended edit:** "`previous_root_sha256` hashes root `seq - 1` of the same chain, the head the create-if-absent won against. `changes` is relative to root `seq - 1`. `created_at` is at least root `seq - 1`'s plus 1 ms, across epochs as well. `previous_inventory` stays the version the content was built from." The chain is then linear, and the forward replay in "live at T" (line 242) is correct.

### M5. Clocks: expiry's "now", forward skew and checkpoints (lines 33-35, 128-130, 200-204, 330)

- **Expiry's "now".** Step 1 compares a successor's `created_at` with "now" and does not say whose clock gives it. The writer stamps `datetime.now(UTC)` (`store/inventory.py:422`). The release clock is the storage server's `Date` header with a skew bound (spec line 451), and the release job refuses to run when its own clock is ahead. For expiry, a clock running behind is also unsafe: a writer whose clock is behind by d stamps an early `created_at`, which ages the previous root by d.
- **Forward skew corrupts the audit.** One writer with a clock months ahead pins `created_at` there, and every later writer stamps base + 1 ms (line 129) until real time catches up. In that period no month boundary appears, so no checkpoints are made, and "live at T" (line 242) maps real dates to the wrong versions. Expiry stays safe, since roots look young.
- **The checkpoint rule needs a precise form.** Line 34 says "first version of each UTC month", and the test needs root N-1's `created_at`, which may sit in a segment.

**Recommended edits:**

- Expiry and the server writer take time from the storage `Date` header under §6.4's skew bound.
- A writer whose base `created_at` is more than a bound (say 5 minutes) ahead of its clock refuses and alerts, where today it would pin.
- State the rule: "N is a checkpoint when N = 1, N = `since_seq`, `restore_epoch[N] ≠ restore_epoch[N-1]`, or the UTC month of `created_at[N]` is later than that of `created_at[N-1]`. It is computed from roots and segment lines, and `verify-catalog` recomputes it."

### M6. The reader's floor rule misses three cases, and the name collides with §6.6 (lines 41-42, 226-229)

- **The name collides.** §6.6 step 4 already uses "floor" for the `seq` a reader holds (spec line 493; `_reader.py:129`). Line 227's "stops at the floor" could mean either.
- **A held root below the floor.** When `CURRENT` is missing, the code probes from `held.seq + 1` (`_reader.py:129, 139`). For a pod holding a root at or below `HISTORY.floor`, that `seq` is expired, so the pod keeps its held root (`_reader.py:137-138, 152`) and is stale for good.
- **An absent `HISTORY`.** `HISTORY` is first written by expiry. A 2.x catalog with `CURRENT` and `HISTORY` both missing, for example after a bad backup, makes the reader probe from 1.
- **The read cost.** The design does not say when the reader reads `HISTORY`. Reading it on every 5 s poll adds a GET per pod.

**Recommended edits:**

- Rename the field to `expired_through`.
- "On a 2.x catalog, the reader reads `HISTORY` only when `CURRENT` is missing or names a root that fails. Its walk back stops at `max(held seq, expired_through)`. Its probe starts at `max(held seq, expired_through) + 1`, and it drops a held root at or below `expired_through`. It fails closed when nothing is found above `expired_through`."
- Opt-in writes `HISTORY` with `expired_through: 0`, so that an absent `HISTORY` on a 2.x catalog is an error.

Above a correctly maintained floor, every root exists (N1's contiguous prefix). The forward probe therefore never meets a gap, and checkpoints above the floor are ordinary retained roots.

### M7. Backup order must put `HISTORY` and `history/` after roots (lines 249-250, 441)

Line 250 says only that a backup "copies `history/` with `inventory/`", and the Handoff (line 441) says "backups include `history/`". Expiry writes the segment, then `HISTORY`, then deletes roots. A backup that copies `history/` before roots while expiry runs captures neither the deleted roots nor their lines. The restored catalog then has a hole that its `HISTORY` does not cover, and every reader without `CURRENT` fails.

Copying in the order roots, `HISTORY`, `history/` is safe. A root missing at copy time was deleted after its segment and `HISTORY` were written, so later copies of `HISTORY` and `history/` contain the segment.

**Recommended edit to §10.3:** "`data/`, edition directories, leaves, roots, `inventory/HISTORY`, `history/`, then `CURRENT`. A backup never runs during an expiry step, or it copies in this order. A restore never deletes or overwrites under `history/`."

### M8. The bounds on W and the GC (lines 202-204, 442-443)

- **One bound is redundant.** §11.6 already orders backup retention ≤ the `data/` GC window (spec line 768), so "W ≥ backup retention" adds nothing. Either give it a reason or drop it.
- **Same-instant comparisons are not enough.** W ≥ GC window holds only when both sides measure from the successor's `created_at` in the same clock (M5). W also needs a margin for a GC walk in progress.
- **GC fails open on a missing root.** Round-1 M2 asked that GC fail closed on a missing root, and stop at the floor without treating a missing root as an empty version. The Handoff gives §11.4 only "GC never touches `inventory/` or `history/`" (line 442). The server GC is unbuilt, so the reviewer could not check how it walks.
- **The pod bound is trivial.** W > pod poll + fetch (line 204) holds for any W counted in days. The pod-staleness alert (spec line 774) gives the bound that matters. A pod stuck on a root for W loses uncached leaves (`_reader.py:177-184`).

**Recommended edits to §11.6:**

- W ≥ `data/` GC window + 1 day, both measured from the superseding root's `created_at` in storage time;
- the pod-staleness alert threshold is below W;
- GC refuses to start when either check fails, stops its walk at `expired_through`, and fails closed on a missing root above it.

### M9. Expiry reopens create-if-absent for expired names (lines 141-147, 185, 210)

Create-exclusive on `inventory/<seq>.json` is the compare-and-swap (spec line 480). Once root N is deleted, a writer whose base is N-1 creates N again in the same epoch, and `create_exclusive` succeeds (`store/inventory.py:432`). The result is a fork below the floor that readers never see and that N1's current text would delete. Reaching this needs a base older than W, as in a process paused across a long laptop sleep or an operator calling `try_commit` with an old base (it is public, `store/EGM.md:152`).

**Recommended edits:**

- "A 1.1 writer on a 2.x catalog refuses a base at or below `HISTORY.expired_through`."
- N1's delete condition ensures that such a root is reported and kept, never deleted.

## Minor

1. **Step 2's scope is costly (lines 205-207).** Verifying "from the newest checkpoint below the candidates up to the newest root" reads every retained root on every run. At W = 30 days and 10 versions a day that is about 300 roots × 1.3-4.5 MB, 3 to 10 times a day. Narrow it: verify the candidates, the link from the newest segment's last line, and the link into the first retained root. Leave the full walk to `verify-catalog`.
2. **Step 7 logs after the deletions (line 215).** A crash loses the log. Write the plan first (B4r), and record roots and leaves in the header (round-1 Nit 30 asked for `{expired_at, actor, roots, leaves}`, and the header at lines 175-177 has no `leaves`).
3. **Checkpoints are audit-only.** GC deletes the edition directories of retired editions (spec line 756), so an old checkpoint's leaves name manifests that are gone. Line 232's leaf check passes while a §10.3 full walk fails. Label checkpoints audit-only (round-1 M20).
4. **Segment size.** A first expiry over a year of 1.1 roots writes one segment of about 3,650 lines (about 330 MB at the design's 90 KB a release, more with republishes). Cap a segment at a line or byte count, and split the run.
5. **`since_seq` and opt-in (lines 154-161).** A statcatlib 0.13 laptop can write a 1.0 root after the first 1.1 root. Define `since_seq` as the lowest `seq` from which every root is 1.1, and have opt-in refuse otherwise. §6.1 allows `catalog.json` to be rewritten "only to bump `restore_epoch`" (spec line 328); add the opt-in rewrite, and say how it is written locally without losing a concurrent epoch bump (`write_catalog_json` is create-only, `store/inventory.py:365-379`).
6. **Tombstones that age out of `retired` produce no change item (lines 121-124).** A replay of `retired` from a checkpoint then diverges from the root. Either record the removals or say that a replay rebuilds `retired` only up to the tombstone window.

## Answers to the design's questions

**Question 2. Does step 6 need a grace period beyond the single-writer argument?** Yes.

- **Why the argument falls short.** It holds only while no other process writes with the release job's identity (B4r). Locally there is no lock, and the re-read in step 6 misses a root created after the re-read.
- **The rule.** Delete a leaf only when it meets both conditions:
  - it is named by no root read after step 5: the retained range above the floor, checkpoints and the roots older than `since_seq`;
  - its storage `Last-Modified` (locally its mtime) is older than G, with G at least the longest commit plus the clock-skew bound. A default of G = 24 hours costs nothing at this scale.
- **Precedent.** `CatalogAdmin.prune` already protects `data/` files the same way (`admin.py:715-719`).
- **What remains.** The rule misses one case: a writer that reuses an old leaf it finds with `exists()` (`store/inventory.py:339-344`). Cover it with step 6's recreate, which then becomes a backstop, and a final check that the head's leaves exist.
- **Locks.** With the grace period, writers need no lock. Expiry still needs its own lock for `HISTORY` and segments (M2).

**Question 3. Does K = 10 by default fit a 5 s pod poll interval?** Yes. The poll does not constrain K.

- A root expires only when it is below the newest K **and** its successor is older than W (line 200). W carries §11.6's poll bound, which any W counted in days meets many times over.
- K bounds two things: how far the fallback walk back from a bad `CURRENT` can go, and what survives a burst of versions inside W. At 3 to 10 versions a day, K = 10 keeps 1 to 3 days even with W at zero.
- **Recommendation:** keep K = 10 and K ≥ 2. State that the poll inequality is met through W. Add the requirement that the pod-staleness alert fires well inside W (M8), since a pod stuck longer than W loses its uncached leaves.

**Question 1 (outside the brief, follows from N2).** `catalog.json` 2.0 is the right opt-in and the right lock-out for writers. Old readers keep reading through it. Pair it with a root major version on opted-in catalogs so that old pods fail closed, or make the sdmxlib-rest pin a checked precondition of the first expiry.
