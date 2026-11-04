# Storage and safety review, round 3: Inventory change lists and history segments

**Target:** `docs/design/inventory-history-log.md`, revision 3 (830 lines, uncommitted on `docs/design-inventory-history-log`). Line numbers refer to this file.
**Lens:** `egm-design`, storage and safety. Mode REVIEW, round 3.
**Result:** 1 Blocker, 8 Major, 9 Nit. Of round 2's six blockers, four are closed (1, 2, 3, 4) and two are partly closed (5, 6). Revision 3 introduces one new blocker: the root-major fallback does not fail closed.

## What was read

- **Persona and hub:** `agents/design_critic.md` (egm 0.1.0) and the hub `CLAUDE.md`. Round 1 `review_report.md`. Round 2 `review_report.md`, `design_storage_report.md` and `zoom_out_report.md`. Only the opening of `prov_o_report.md`, since PROV-O is outside this lens.
- **Commits:** every checkout is on `main`, and `refs/heads/main` equals `refs/remotes/origin/main` equals the cited commit: sdmxlib `b6c79892`, statcatlib `95fd7ad`, sdmxlib-rest `f1582e4`. The reviewer could not see whether the working trees hold uncommitted edits. Every citation the design makes that was checked matches these files: `_reader.py:119-155, 128, 177-184`, `_format.py:138-140, 245, 284-290, 306-315`, `store/inventory.py:214-220, 315, 339-344, 426, 432`, `admin.py:538`, `app.py:233-245`, `pyproject.toml:38`, `conformance.py:110-112`.
- **sdmxlib:**
  - `src/sdmxlib/inventory/EGM.md`, `_reader.py`, `_format.py:1-340`, `conformance.py:98-117`;
  - spec `docs/design/sharded-bundle-catalog.md` §6.6 (478-497), §10.1-10.3 (693-718), §11.2-11.6 (733-774), §9.2 (681-685);
  - plan `docs/design/sharded-bundle-catalog-plan.md:153, 320-346`;
  - `CHANGELOG.md` head.
- **statcatlib:** `store/inventory.py:180-490` and `admin.py:520-770`, plus a search of `src/` for `commit`, `try_commit` and `InventoryWriter(`.
- **sdmxlib-rest:** `src/sdmxlib_rest/EGM.md`, `app.py:140-247` and `pyproject.toml`, plus a search of `src/` for Inventory reads.
- **Not found:** sdmxlib#348 has no design file in the sdmxlib checkout. Its content comes from the plan's Phase 4 text (plan 324-328, 343, 378) and spec line 382.

## Round-2 status

| Round-2 finding | Status | Where revision 3 answers it | Remaining defect |
| --- | --- | --- | --- |
| Blocker 1, chain against `previous_inventory` | Closed | 49-54, 140-146, 181-187, H10 (545), conformance case 688-689 | verify-catalog keys "a `seq` present in both" by `seq` alone, which breaks after a restore (Major 7) |
| Blocker 2, `from_seq` | Closed | H11 (546), 500-504, 181-184 | Outside lens |
| Blocker 3, seal fact | Closed | 108-111, H15 (550), 508-512 | Outside lens |
| Blocker 4, crash rule deletes unrecorded roots | Closed for roots | Terms 69-73; step 1 370-376; step 5 387-388; crash rule 394-399; acceptance 701 | A run's plan spans several segments, and step 6's "retained roots" set is undefined (Majors 5, 6) |
| Blocker 5, lock-out claim | Partly closed | 266-274 corrected; stage-1 reader 235-256; precondition 284-297 | The fallback does not fail closed (Blocker 1). The pod check runs once and misses workloads (Major 1). A stale `CURRENT` path is still open (Major 2). |
| Blocker 6, leaf deletion lock | Partly closed | Exclusion 354-366; H12 (547); recreate dropped (389-390); plan in header (327-329); Handoff 712-713, 728-731 | The lock's kind, scope and reentrancy are unspecified, and `try_commit` bypasses it (Major 3). The lease mechanics are unspecified, and S3 has no lease (Major 4). |
| Major 1, epochs | Partly closed | 316-318, 325-326, 339-341, 242-244, 415-427, 461-464 | `expired_through` across epochs, verify-catalog keying, the discard-segment kind, failover, epoch-keeping rollback against object lock (Major 7) |
| Major 2, floor cases | Closed | 69-73, 238-251, 275-276 | New gap: a valid `CURRENT` at or below `expired_through` (Major 2) |
| Major 3, segment naming and crash | Mostly closed | 313, 319-321, 333-335, 341-342, 381-385 | Adoption checks no chain link and no range (Major 5, Nit 5) |
| Major 4, segment lines bound only by chain | Closed | 102-103, 336-338, 385, 453, 622 | None |
| Major 5, clocks | Closed | 60-62, 185-192, 373-374 | None |
| Major 6, backup order | Closed | 428-431 | None |
| Major 7, W bounds and GC | Closed | 401-413, Handoff 680 | None |
| Major 8, rebuild | Closed | 124-125; §6.7 gone from Handoff | None |
| Major 9, expired names reopened | Partly closed | 193-195, 397-399, 620 | The refusal must run after the lock or lease is taken, against a fresh read of `HISTORY` (Major 3) |
| Major 13, staging | Closed | 650-660 | None |

## Blocker

### 1. The root-major fallback does not fail closed (lines 298-302, H13 at 548, 598-599, risk row 619, Question 2 at 812-814)

Line 300 says an old pod "fails closed and never serves a checkpoint as the head". The reader code does something else:

- `_root_at` turns a major-version refusal into `None` and a `skipped` entry (`_reader.py:109-113`).
- The walk back runs `while found is None and seq > floor` and steps over absent and undecodable roots alike (`_reader.py:134-136`). It stops at the first root that decodes.
- The forward probe also skips undecodable roots and continues (`_reader.py:141-148`).
- Roots below `since_seq` stay 1.x and never expire (lines 262-265).

An opted-in catalog writing 2.0 roots therefore produces two failures:

- A fresh old pod walks back to the last 1.x root before the opt-in and serves it as the head.
- An old pod with a held root keeps that root (`_reader.py:137-138, 152`).

Both serve a stale version, and only `skipped` and the staleness alert record it. This starts at the opt-in, before any expiry, so the fallback is worse than the hazard it guards against, which needs `CURRENT` to fail first.

The only old-reader path that raises is `decode_current`, which sits outside any `try` (`_reader.py:127`; `_format.py:299-303`). A lock-out that works would have to make `CURRENT` undecodable for old readers, and that stops every old pod at once.

**Edit:** delete the root-major fallback from lines 298-302, H13, the Alternatives entry at 598-599 and risk row 619. Replace it with the time-based precondition in Major 1. If the owner keeps a format lock-out, specify it on `CURRENT` and state that every old pod stops serving from the opt-in.

## Major

### 1. The first-expiry pod check runs once and misses readers (lines 284-297, H13, 619, 645-646, 736-738)

- **The check runs once.** Line 295 says "Later runs skip the check, since the floor in item 1 holds". The floor constrains only new sdmxlib-rest builds. The spec keeps a rollback window for the pod image (§9.2 step 5, spec line 685; §11.6, line 772), so a rollback after the first expiry brings pre-stage-1 readers back.
- **One headless Service covers too little.**
  - Headless Service DNS lists only Ready pods unless `publishNotReadyAddresses` is set (verify before citing).
  - The spec has three serving Deployments (`hot`, `base`, `search`; spec line 897).
  - Other workloads read the Inventory too: the preview deployment's `EmbargoReader`, the pre-materialisation job on the pods' image (spec line 737), and GC, which reads the chain (§11.4).
- **`GET /` can lose the version.** A consumer replaces the payload through `root_payload` (`app.py:143, 233-236`). sdmxlib-rest's `src/` reads no Inventory object: `LiveInventory` appears only in `tests/test_inventory_describe.py`. The reader in a pod is the consumer's `CatalogProvider`.

**Edit:**

- Run the check on every expiry run.
- Enumerate every Inventory-reading workload from configuration: Services with `publishNotReadyAddresses`, or the Kubernetes API by label.
- Take the version from `importlib.metadata.version("sdmxlib")` in the serving process. Count an unreachable pod or a missing field as a failure.
- Add a time precondition that uses the spec's existing concept: no expiry until the rollback window for the last pre-stage-1 pod image has closed (§9.2 step 5). On an opted-in catalog the image runbook forbids rolling back to a pre-stage-1 image.

### 2. A valid `CURRENT` at or below `expired_through` makes every reader serve a checkpoint (lines 238-239, 370-376)

When `CURRENT` names a root that verifies, the new reader reads no `HISTORY` (line 238). The probe from `CURRENT.seq + 1` stops at the first absent root (`_reader.py:142-144`). `CURRENT` lags after a crash between the root and `CURRENT` (`store/inventory.py:432-436`), and after a lost replace race (`:349-351`). Step 1 can expire the root `CURRENT` names once it lags by K versions and W. A lagging `CURRENT` that names a checkpoint then serves the checkpoint on old and new readers alike, which is the round-1 B3 failure.

**Edit:** step 1 never takes a root at or above `CURRENT.seq`. Expiry first brings `CURRENT` up to the head under the lock or lease, as the release job already does on startup (spec line 495), and `prune` does the same. Add a conformance case with `CURRENT` lagging past K.

### 3. The local catalog lock is unspecified, sits in the wrong method, and deadlocks `prune` (lines 74-75, 312, 356-360, 193-195, 712-713)

- **Kind.** Specify an OS advisory lock (`fcntl.flock`, or `LockFileEx` on Windows) on `inventory/LOCK`. The OS releases it when the process dies, so no stale lock survives a crash, and the file is never unlinked. Cite spec line 497 (network shares are unsupported) for the advisory-lock assumption. A lock taken by creating the file exclusively would leave a stale lock after a crash.
- **Scope.** `try_commit` is public (`store/EGM.md:152`), and it holds both the leaf check and the root create (`store/inventory.py:415, 432`). Put the lock in `try_commit`, or a direct caller bypasses it. `commit` reads the base before any lock (`:472`). The stale-base refusal at lines 193-195 must therefore run after the lock is taken, against a fresh read of `HISTORY`. Otherwise an expiry between the head read and the lock reopens round-2 Major 9.
- **Reentrancy.** `prune` commits its `retire` version through `commit` (`admin.py:663`). If expiry in `prune` holds the lock while that commit takes it again, a per-open-file `flock` deadlocks. Say that `prune` commits `retire` before it takes the expiry lock, or make the lock reentrant within a process.
- **Coverage.** Opt-in (lines 278-280), restores and every expiry step take the same lock.

### 4. The `HISTORY` lease's duration, renewal, loss and store support are unspecified (lines 361-366, H12, 617, 826-827)

- **Duration and loss.** Azure leases last 15 to 60 s or are infinite (verify before citing). Choose a finite lease, renew it every 20 s at most, and abort before the next destructive call when a renewal fails. A paused holder (VM freeze, network partition) can still delete after its lease lapsed, and a lease on `HISTORY` fences no other blob.
- **Fencing the leaf race.** The writer overwrites, with the same bytes, a leaf it finds present among the leaves it writes (`store/inventory.py:339-344`), which changes the leaf's ETag. Step 6 deletes each leaf with `If-Match` on the ETag read at its final check (verify Delete Blob conditional headers). In either order the leaf survives, so leaf safety no longer depends on lease timing. Carried-forward leaves are safe because their base root is retained (Major 3).
- **Blocking.** A holder that hangs while it still renews blocks an emergency `CatalogAdmin` withdraw or rollback. Set a maximum hold time, and write a runbook for breaking the lease.
- **Store support.** Phase 4 targets `S3Store` as well as `AzureStore` (plan line 329), and S3 and GCS have no blob lease. Either declare server expiry Azure-only, or define a lock object created conditionally, with a TTL and with fencing through `If-Match` on `HISTORY`.

### 5. Crash recovery when one run writes several segments (lines 316-318, 381-399)

A run writes one segment per epoch and splits at 1,000 lines, but `HISTORY` advances once, and "the plan in the newest segment's header" covers only that segment. Adoption at line 382 checks lines against roots and checks nothing else. The next run cannot tell whether the previous run finished steps 5 and 6, so it would have to search every reachable segment for a matching line.

**Edit:**

- A run writes its segments in chain order.
- Adopt an orphan only when its `previous_segment` equals `HISTORY.newest_segment` (or chains to it through other orphans), and its `first` is `expired_through + 1`.
- `HISTORY` gains `cleaned_through`, the newest segment whose steps 5 and 6 finished, written after step 6.
- The crash rule processes only the headers between `cleaned_through` and `newest_segment`.

### 6. Step 6's "retained roots" set and its cost are undefined (lines 387-392, 617, 726-727)

The retained roots include the roots below `since_seq`, the checkpoints, and the unmatched roots kept below `expired_through`. The reader's range from `expired_through + 1` to the head misses all three, and only a LIST of `inventory/` finds them. In the statcatlib#126 corpus (lines 41-43), 2,979 pre-opt-in versions at 560 KB to 1.6 MB each come to 1.7 to 4.7 GB read per run, 3 to 10 runs a day.

**Edit:** step 6 LISTs `inventory/*.json` and reads every retained root, caching each root's leaf set by its SHA-256 (roots never change). State the cost. Mention in the Handoff that the cache is the release job's.

### 7. Restores leave `expired_through`, verify-catalog and object lock inconsistent (lines 69-73, 343-344, 415-431, 437-438, 679)

- **`expired_through` across epochs.** Terms (69-70) define it as the highest `seq` removed "in the current `restore_epoch`", and line 343 sets it to the `last` of "the newest segment of the current epoch". After a restore, expiry removes old-epoch roots up to S, and under that definition `expired_through` stays at its old value. The fallback probe from `expired_through + 1` then meets an absent root and stops (`_reader.py:142-144`), so the reader finds no root. Define it as the highest `seq` removed from the chain that ends at the head, whatever the root's epoch.
- **Key by epoch.** Check 1 (437-438) matches "a `seq` present in both". The restore's discarded lines S+1..N (epoch e) and the new roots S+1.. (epoch e+1) share `seq` values and would be reported as mismatches. Key by `(restore_epoch, seq)`, and say that the chain branches at S.
- **Segment kind.** Give the segment header a `kind` (`expiry` or `restore`), so the crash rule and the `expired_through` check ignore discard segments. A discard segment's `last` is N, which is greater than S.
- **Failover.** After a failover, the discarded roots may be unreadable. Say that the restore writes what it can read.
- **Epoch-keeping rollback.** Lines 424-427 restore `history/` from a backup. That contradicts line 420 ("never deletes or overwrites under `history/`") and the Handoff at 679 ("restores never touch `history/`"). Under the recommended object lock (337, 600-604), newer segments survive, `(epoch, seq)` gets reused, and verify-catalog reports mismatches for good. On an opted-in catalog, every restore must bump the epoch, and an epoch-keeping rollback is unsupported (`restore_to` stays for 1.x catalogs).
- **Order.** Give the restore's order under the lock or lease: discard segment, `HISTORY` (new epoch, link), `catalog.json` epoch, delete roots above S, root S+1, `CURRENT`. A crash after the `HISTORY` write leaves readers failing closed until S+1 exists.

### 8. `since_seq` depends on the minor number that sdmxlib#348 also claims (lines 135-136, 197, 262-265)

`since_seq` is "the lowest `seq` from which every root is 1.1". The plan gives 1.1 to Phase 4's routing fields (plan 324-328, 343). If that 1.1 ships first, a writer can write "1.1" roots without `changes`. Opt-in's check then passes, and step 1 meets roots with no change list. Phase 4 also brings `reinstate` (plan 333), which this design's 1.1 adds as a kind at line 197.

**Edit:** define `since_seq` and the opt-in refusal by the presence of `changes` and `previous_root_sha256`, and write the format rules against "the minor that adds `changes`". Expiry stops at any root at or above `since_seq` that lacks `changes`, and verify-catalog reports it. Recommendation (a) below gives the numbering.

## Nit

1. **Lines 271-273.** sdmxlib-rest's `src/` reads no Inventory object, so the sentence about `catalog.json` is true but beside the point. State that no serving reader reads `catalog.json`: `_Chain.refresh` reads only `CURRENT` and roots, and the pod's reader is the consumer's provider.
2. **Line 241.** The fallback reads `catalog.json`, and the §10.1 table (spec 697-704) gives pods no row for it. Add it to the §10.1 Handoff item at 677-678.
3. **Line 312.** Placing `inventory/LOCK` under `inventory/` means backups, verify-catalog and step 6's LIST must each skip it. Moving it to `<catalog>/LOCK` avoids that.
4. **Line 318.** A 1,000-line segment of republishes is about 6.5 GB (line 217). Also split by bytes (for example 64 MiB), so writes and verify-catalog downloads stay bounded.
5. **Lines 381-384.** Adopt an orphan only when its range lies within the current candidates. A K or W raised between runs would otherwise expire roots the new configuration keeps.
6. **Opt-in race.** An old writer can decode `catalog.json` before the rewrite and create a root after it, with no lock (`store/inventory.py:426-432`). Run the first expiry in a later call than the opt-in, and apply Major 8's stop rule.
7. **Orphan leaves.** Leaves from a commit that crashed before its root are in no header, so they are never deleted. Say so: the leak is safe and bounded.
8. **Step 1 cost.** The first run reads about 3,650 roots for `created_at` alone (about 5.8 GB). `created_at` is the fifth field in field order (`_format.py:153-157`), so a ranged GET of the first kilobyte is enough.
9. **Verify before citing (816-830).** Add three items: Kubernetes headless Service and not-ready pods; Azure lease durations, renewal and break; Delete Blob `If-Match`.

## Recommendations on the two open questions

**(a) sdmxlib#348 and Inventory 1.1.** Do not share 1.1.

- One constant versions roots and leaves (`INVENTORY_FORMAT`, `_format.py:22-23`). A reader refuses only another major (`_format.py:274`) and ignores unknown fields. The number therefore matters only to writer rules, schemas and the checks that test `format_version`, and this design's `since_seq` is one of those checks (Major 8).
- Sharing would tie this design's stage 1, which "waits for no phase" (line 657), to Phase 4's specification PR, whose scope is still open (`pool` and `pinned` are undecided, plan 326).
- Minors are cumulative, so the number follows merge order. The second specification PR to merge takes the next minor.
- Write this design against "the minor that adds `changes`" and test for the fields. If a number is needed now, take 1.2, since #348 claimed 1.1 first.
- Coordinate the `reinstate` kind with Phase 4, so only one minor adds it.

**(b) Pod polling or the root major from the start.** Take neither as written.

- The root major does not fail closed. It freezes old pods on stale versions from the opt-in (Blocker 1), so it is the worse choice.
- Keep the pod check as detection, strengthened as in Major 1: run it every expiry run, cover every Inventory-reading workload, and count unknown as failure.
- Make the gate the §9.2 rollback window. No expiry runs until the last pre-stage-1 pod image is out of the rollback window, and the runbook forbids rolling back to it.
- If the deployment cannot give the release job pod addresses, use the time precondition alone.
- With Major 2 fixed, an old pod misbehaves only when `CURRENT` is missing or names a root that fails to verify, and the time gate covers that residue.
