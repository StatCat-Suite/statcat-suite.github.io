# Review report, round 3: Inventory change lists and history segments

**Target:** `docs/design/inventory-history-log.md`, revision 3 (lines 1-830, uncommitted on `docs/design-inventory-history-log`).
**Reviewer:** one `egm-design` reviewer, storage and safety lens. Full report: `design_storage_report.md` in this directory.
**Code read:** every checkout on `main` at origin/main: sdmxlib `b6c79892`, statcatlib `95fd7ad`, sdmxlib-rest `f1582e4`. The design's code citations match these commits. The synthesizer checked the blocker's reader lines (`_reader.py:100-155`) against the sdmxlib checkout.
**Result:** 1 Blocker, 8 Major, 9 Nit.

## Round-2 blocker status

| Round-2 blocker | Status | Remaining defect |
| --- | --- | --- |
| 1, chain against `previous_inventory` | Closed (49-54, 140-146, 181-187, H10) | verify-catalog keys by `seq` alone (Major 7) |
| 2, `from_seq` | Closed (H11, 500-504) | None |
| 3, seal fact | Closed (108-111, H15, 508-512) | None |
| 4, crash rule deletes unrecorded roots | Closed for roots (69-73, 370-399, 701) | Multi-segment runs and step 6's retained set (Majors 5, 6) |
| 5, lock-out claim | Partly closed (235-297) | Fallback does not fail closed (Blocker 1); pod check gaps (Major 1); lagging `CURRENT` (Major 2) |
| 6, leaf deletion lock | Partly closed (354-366, H12, 712-713, 728-731) | Lock kind, scope and reentrancy (Major 3); lease mechanics and S3 (Major 4) |

Of the round-2 storage majors, 2, 4, 5, 6, 7, 8 and 13 are closed, 3 is mostly closed, and 1 and 9 are partly closed.

## Blocker

### 1. The root-major fallback does not fail closed (298-302, H13, 598-599, 619, 812-814)

An old reader turns a root it cannot decode into `None` (`_reader.py:109-113`) and walks back past it to the first root it can decode (`_reader.py:134-136`). The forward probe skips it too (`_reader.py:141-148`). Pre-opt-in 1.x roots never expire (262-265). From the opt-in, a fresh old pod therefore serves the last 1.x root as the head, and an old pod with a held root keeps serving that root. Only `skipped` and the staleness alert record either case. Only `decode_current` raises (`_reader.py:127`). **Edit:** delete the root-major fallback and use the time precondition in Major 1. A working lock-out would have to make `CURRENT` undecodable and would stop every old pod at the opt-in.

## Major

1. **The pod check runs once and misses readers (284-297).** An image rollback after the first expiry brings old readers back (spec §9.2 step 5). Headless Service DNS omits not-Ready pods. The spec has three serving Deployments, and the preview `EmbargoReader`, the pre-materialisation job and GC also read the Inventory. A consumer's `root_payload` can replace `GET /` (`app.py:143, 233-236`). **Edit:** check on every run, enumerate every Inventory-reading workload, read `importlib.metadata.version("sdmxlib")`, count unknown as failure, and gate on the §9.2 rollback window closing.
2. **A lagging `CURRENT` can name an expired-down-to-checkpoint root (238-239, 370-376).** A reader that verifies `CURRENT` reads no `HISTORY`, and its probe stops at the first absent root. **Edit:** step 1 never takes a root at or above `CURRENT.seq`; expiry and `prune` first bring `CURRENT` up to the head under the lock or lease. Add a conformance case.
3. **Local lock unspecified (74-75, 312, 356-360, 193-195).** Specify `fcntl.flock` or `LockFileEx` on a never-unlinked file, so a crash leaves no stale lock. Take it in the public `try_commit` (`store/inventory.py:415, 432`). Run the stale-base refusal after the lock, against a fresh `HISTORY`. `prune` commits `retire` through `commit` (`admin.py:663`), which deadlocks a non-reentrant lock, so order the two calls or make the lock reentrant. Opt-in and restores take the same lock.
4. **Lease mechanics unspecified (361-366, H12, 617).** Give a finite lease, renewal interval, and abort-on-renewal-failure rule, a maximum hold time, and a break runbook. Delete leaves with `If-Match` on the ETag read at the final check, so a concurrent same-bytes rewrite (`store/inventory.py:339-344`) survives. S3 and GCS have no lease, so either make server expiry Azure-only or define a conditional lock object with a TTL.
5. **Crash recovery across several segments per run (316-318, 381-399).** Write segments in chain order. Adopt an orphan only if it links to `newest_segment` and starts at `expired_through + 1`. Add `HISTORY.cleaned_through`, written after step 6, and limit the crash rule to segments after it.
6. **Step 6's retained-root set and cost (387-392).** Pre-opt-in roots, checkpoints and kept roots lie outside the reader's range. Step 6 must LIST `inventory/` and read every retained root (1.7 to 4.7 GB per run on the statcatlib#126 corpus). Cache leaf sets by root SHA-256 in the release job, and state the cost.
7. **Restores (69-73, 343-344, 415-431, 437-438, 679).** Define `expired_through` across epochs on the chain that ends at the head. Key verify-catalog by `(restore_epoch, seq)`. Add a segment `kind` (`expiry` or `restore`). An epoch-keeping rollback that restores `history/` contradicts lines 420 and 679 and fails under object lock, so require an epoch bump on opted-in catalogs. Give the restore's write order.
8. **`since_seq` tied to the minor sdmxlib#348 claims (135-136, 197, 262-265).** Define `since_seq` and the opt-in refusal by the presence of `changes` and `previous_root_sha256`, not by `format_version`. Expiry stops at any root at or above `since_seq` that lacks `changes`.

## Nit

1. Lines 271-273: state that no serving reader reads `catalog.json`.
2. Line 241: add the fallback's `catalog.json` read to the §10.1 Handoff item (677-678).
3. Line 312: move the lock to `<catalog>/LOCK`, so LIST, backups and verify-catalog need no skip rule.
4. Line 318: also split segments by size (for example 64 MiB).
5. Lines 381-384: adopt an orphan only when its range lies within the current candidates.
6. Opt-in race with an old writer: run the first expiry in a later call than the opt-in.
7. State that orphan leaves from a crashed commit leak, and that the leak is safe and bounded.
8. Step 1: read `created_at` with a ranged GET of the first kilobyte.
9. Verify before citing: Kubernetes not-ready pods, Azure lease limits, Delete Blob `If-Match`.

## Recommended edits, in order

1. Remove the root-major fallback (Blocker 1) and replace it with the rollback-window gate and the strengthened pod check (Major 1).
2. Add the `CURRENT` rule to step 1 (Major 2).
3. Specify the local lock and the lease (Majors 3, 4).
4. Add `cleaned_through`, the orphan-adoption link check and the step 6 LIST (Majors 5, 6).
5. Fix the restore rules (Major 7).
6. Write the format rules against the fields, and number the minor 1.2 (Major 8).

## Open questions

**(a) Share Inventory 1.1 with sdmxlib#348 or take 1.2.** Take a separate minor. The number matters only to writer rules and to checks that test `format_version`, since readers refuse only a different major (`_format.py:274`). Sharing ties this design's stage 1 to Phase 4's specification PR, whose scope is still open (plan 326). Write the rules against the fields this design adds. If a number is needed now, use 1.2, since #348 claimed 1.1 first, and let merge order settle the final number. Coordinate the `reinstate` kind so only one minor adds it.

**(b) Pod polling or the root major from the start.** Drop the root major: it serves stale versions from the opt-in (Blocker 1). Gate the first expiry and every later one on the §9.2 rollback window for the last pre-stage-1 image, with a runbook rule that forbids rolling back to it. Keep the pod check as detection, run on every expiry and counting unknown as failure. Where the release job cannot reach pods, use the time gate alone.
