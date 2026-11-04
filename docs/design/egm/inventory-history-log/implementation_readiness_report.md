# Implementation readiness review: Inventory history log

**Target:** `docs/design/inventory-history-log.md` (lines 1-276; Cross-repo contract and Handoff at 238-263 stand in for the detailed range)
**Lens:** `egm-implementation-readiness`, against `implementation-readiness-standard.md` (Zero-Decision Rule)
**Read:** sdmxlib spec §6.2-6.7, §10.1, §10.3, §11.4, §11.6, `inventory/EGM.md`, `_format.py`, `conformance.py` (working tree, branch `docs/q1-product-granularity`); statcatlib `store/EGM.md`, `store/inventory.py`, `admin.py` (`prune`), the `verify-catalog` CLI (working tree, branch `feat/gh-124-corpus-bench`); hub `CLAUDE.md`.
**Verdict:** not ready. About 40 points need a guess; five are blockers.

## A. Blockers

**A1. The orphan-record replace rule can leave a root whose record names another root (lines 141-147, 273).** Same race as `design_storage_report.md` B1. The reuse branch never fires (`try_commit` stamps `now`, `inventory.py:422`). The local writer uses `create_exclusive` with link semantics (`inventory.py:432`; `store/EGM.md:353-358`) and has no ETag; it is multi-process (`tests/test_concurrent_seal.py`).
**Fix:** name records `history/<seq:012d>-<root_sha256>.json`, create-if-absent; add a required `previous_root_sha256` so record N names record N-1 after root N-1 expires; the newest record's name comes from `CURRENT`'s `root_sha256`; a record is valid when root N exists with that hash or the valid record N+1 names it; others are orphans that `verify-catalog` warns on and expiry deletes. If one name per seq is kept, give a local lock protocol and a server proof of a single writer.

**A2. A `fetch`-only reader cannot find segments (lines 82, 88-90, 158).** The reader takes only `fetch(path) -> bytes | None` (`inventory/EGM.md:7-9`; §6.6 step 3; §10.2).
**Fix:** segment boundaries at checkpoints, named `history/segments/<first:012d>.jsonl`, the next starting at last + 1, probed forward from `000000000001`; or a conditionally written `history/HEAD`. State how a reader holding only `CURRENT` finds record N.

**A3. The hash input and on-disk bytes are undefined (lines 126-128, 204).** sdmxlib's `encode` writes msgspec-indented JSON with a final newline (`_format.py:263-265`), which is not RFC 8785. Re-canonicalising a decoded struct drops unknown fields, which 1.x readers ignore (§6.3 Versioning), so the chain breaks on a minor addition.
**Fix:** a record's bytes are exactly its RFC 8785 serialisation, no trailing newline; `prev_sha256` = SHA-256 hex of the previous valid record's bytes, including its own `prev_sha256`; a segment line is those bytes plus `\n`; verification hashes raw bytes; a reader refuses non-canonical bytes. Name the RFC 8785 implementation (sdmxlib has no JCS dependency; add one with a cap, or write a minimal encoder, safe because records hold no floats).

**A4. Leaf expiry races concurrent writers (lines 156-163, 232, 236).** `_write_leaf` skips an existing path (`inventory.py:339-344`).
**Fix:** (a) delete a leaf only if no root names it and its object age exceeds W; (b) after deleting, re-read the head and every newer root and re-create any deleted leaf they name from bytes held in memory; (c) writers always call create-if-absent and treat `FileExistsError` as success.

**A5. No migration for existing catalogs.**
**Fix:** a "Migration" subsection: the first record is at the first post-upgrade version M, with `prev_sha256: null` and a required `history_starts_at: M`, and M is a checkpoint; roots below M never expire, or a one-time `backfill` diffs roots into records 1..M-1 (pick one). Lock out old writers by bumping `catalog.json` to 2.0: `decode_catalog` refuses another major (`_format.py:268-276`) and the Inventory reader never reads `catalog.json`, so pods are unaffected. Or add a field old writers cannot ignore.

## B. Record and segment schema

- **B1 (Major; lines 94-129, 240-241).** A field table as in §6.2 with presence and nullability; `*_sha256` as 64 lowercase hex; `created_at` RFC 3339 UTC `Z`; `event.kind` enum with unknown kinds accepted (`EGM.md:61-63`); schema file names and `schema(document)` keys; which fields are copied verbatim from the root.
- **B2 (Major; line 104).** `embargo`: "required, the root's `embargo`, copied".
- **B3 (Major; lines 105-123, 274-275).** Entries for retirement (`to: null`?), `reinstate` (`from: "tombstone"`?), unchanged state with changed `release_at`, `manifest_sha256` (`correct`) or `structure_source`; leaf `kind` or `lifecycle` changes; product added or removed; changed entries only or all; sort order; whether `release_at` is required and nullable.
- **B4 (Major; line 115).** `retired` delta or full list? Tombstones also leave by `reinstate` (§6.4 line 443) and by ageing out. **Fix:** `retired_added` and `retired_removed`, required, possibly empty.
- **B5 (Major; line 116).** `extensions_sha256`: "required; every key of the root's `extensions`, each the SHA-256 of the section's RFC 8785 bytes; `{}` when none".
- **B6 (Major; lines 82, 157-159).** Segments: 12-digit padding (roots use 12, `_format.py:245-250`); no header; no segment hash (the chain runs through records); never spans an epoch; where a segment and a per-record object overlap, use the segment line and require equal bytes.
- **B7 (Major; lines 96, 240).** History formats have their own version (`HISTORY_FORMAT = "1.0"`); root and leaf stay 1.0; a missing `history/` on a catalog marked pre-history is a doctor warning, never a finding.

## C. Write path, checkpoints, expiry

- **C1 (Major).** The writer fetches the base's record by name, refuses with a named error if missing (unless pre-history), re-derives per attempt of the `commit` loop (`inventory.py:471-488`); expiry never compacts records within the newest K.
- **C2 (Major).** Pseudo-code: read head; write leaves; encode and hash root; build and encode record; create record (`FileExistsError` on the same name = identical bytes = success); create root (`FileExistsError` raises `InventoryConflictError`, loop restarts, orphan stays); advance `CURRENT`. Name the sdmxlib pure function, for example `next_record(base_root, base_leaves, root, leaves, *, prev_sha256) -> HistoryRecord`, so conformance can check the diff (`EGM.md:41-46`).
- **C3 (Major).** A required boolean `checkpoint`, set by the writer (version 1, first after an epoch change, migration start, or a UTC month change from the base record); expiry trusts it, `verify-catalog` recomputes it. `created_at` uses the writer's clock (`inventory.py:422`), the release clock the storage `Date` header (§6.4 line 451).
- **C4 (Major).** W and K have no home: §11.6's "one configuration" is unnamed; statcatlib has no retention configuration; `prune` takes only `older_than` (`admin.py:520`). **Fix:** a `RetentionConfig` attrs class; `prune(keep_versions=K, expire_after=W)` and CLI flags; defaults (for example K = 10, W = 35 days); W measured from the successor's `created_at`; refuse to start when the inequalities fail.
- **C5 (Blocker as a group).** Numbered expiry with crash outcomes: compute retained set and range; write segment create-if-absent; re-read and verify chain and byte equality; delete per-record objects; delete roots; delete unreachable leaves (A4); write deletion log. A crash after the segment resumes at the deletes; a different-bytes segment is an error; leftovers in a segment's range are deleted next run; unreachable leaves after root deletes are safe to delete later; roots are never deleted before their records are compacted.
- **C6 (Major).** Dry run: `prune(dry_run=True)` exists (`admin.py:548`); list segments, records, roots and leaves with counts and bytes; extend `PruneReport`; say whether server expiry writes a forecast and alerts on deviation as GC does (§11.4).
- **C7 (Major).** `prune` documents "Prune deletes no Inventory root or leaf, never expires a tombstone" (`admin.py:538-539`), and P7 keeps everything (`phase-2a-catalog-editions.md:274`). The statcatlib Handoff must say P7 is superseded, the docstring and `docs/api/admin.md` change, and whether expiry is a fourth `prune` step or an `expire` method.
- **C8 (Major).** Back up `history/` after roots and before `CURRENT`; after `restore_to(seq)` in the same epoch (`conformance.py:110-112`), later records survive and become orphans that `verify-catalog` reports.
- **C9 (Major).** A null `prev_sha256` at an epoch change lets anyone start a fresh chain. **Fix:** the first record of an epoch carries a required `previous_epoch_last_sha256`.
- **C10 (Major).** A `history/` column in §10.1 (release job write and delete; GC none; pods none; preview read); the export takes `live_only: bool`.

## D. PROV-O

- **D1 (Major).** Pick one target for `reason`; classify actors (a local actor is `<os user>@<hostname>`, `inventory.py:214-220`) or always use `prov:Agent`; list all nine classes and the unknown-kind fallback; `hadRole` needs `prov:qualifiedAssociation` (or PROV-JSON's `prov:role` attribute).
- **D2 (Blocker for the export).** No `stc:` namespace and no IRI scheme; use `catalog_id` from `catalog.json`. See `prov_o_report.md` F6, F7.
- **D3 (Major).** The record lacks every leaf hash and `previous`; add `previous` and `manifest_sha256` to entries, or define the export over a checkpoint plus records. Question 4 must be decided before the schema.
- **D4 (Major).** Tombstone invalidation conflicts with `reinstate`; invalidate the state entity and generate "retired"; never invalidate the edition.
- **D5 (Nit).** Pre-history states have no `wasGeneratedBy`; state the time-field rule.
- **D6 (Major).** Name the API (for example `sdmxlib.inventory.prov_json(records, *, catalog_id, live_only=True) -> dict`), whether RDF is in scope, the validator (the W3C PROV-JSON member submission's JSON Schema, vendored and pinned, or the `prov` package as a test-only dependency), and a complete worked example (the current one's `…` fails any hex pattern).

## E. Verification, conformance, phasing, handoff

- **E1 (Major).** `verify-catalog` exits 0, 1 or 2 (`cli/__init__.py:458-460`) and has no `--find-newest-consistent`. List each new check and whether it is a finding or a warning: chain integrity; retained roots against records; retained roots' leaves; orphan records (warning); missing `history/` on a pre-history catalog; checkpoint flag mismatch; segment and record byte mismatch. Add `--expect-record-sha256 <hash>` as the outside anchor.
- **E2 (Major).** The `Backend` protocol (`conformance.py:75-116`) needs `history() -> Sequence[bytes]`, `commit_interrupted_after_record(base, leaves)`, `expire(keep, window, now)`; give each case's setup and assertion; say whether the Delta prototype backend must pass the history cases (`EGM.md:76-80` runs every check on both).
- **E3 (Major).** The statcatlib Handoff breaks hub `CLAUDE.md` (one issue per repository with acceptance checks). Write the checks now (every `InventoryWriter.commit` writes a valid record; history conformance passes in `tests/test_inventory_conformance.py`; dry and real expiry tests at each crash point; `verify-catalog` exit codes; migration test) and say the hub session files `StatCat-Suite/statcatlib#N` after sdmxlib#361 merges and releases.
- **E4 (Major).** The release job is Phase 5 (statcatlib `phase-3-structure-products.md:166`); local record writing need not wait. Split: (1) writer records, local expiry in `prune`, `verify-catalog`, as soon as sdmxlib releases, including raising the sdmxlib cap (hub `docs/conventions.md:94-96`); (2) release-job expiry in Phase 5.
- **E5 (Major).** sdmxlib#361: number and title the new section (§6.9?); list each section's edit (§6.6 record step; §6.7 orphan records; §10.1 `history/` column and delete; §10.3 backup order; §11.4 GC excludes `history/`; §11.6 W and K); one PR or spec then code; minor bump.
- **E6 (Nit).** "Based on" omits sdmxlib-rest's commit (hub `CLAUDE.md:59`); name the "live at T" reader API; mark the `rebuild-inventory` claim as future work.
