# Design review (storage, write order, expiry, safety): Inventory history log

**Target:** `docs/design/inventory-history-log.md` (lines 1-276; PROV-O section out of scope except where the record constrains it)
**Lens:** `egm-design`, instance A, against `feature-spec-standard.md`
**Read:** sdmxlib spec §6.1-6.7, §10.1-10.3, §11.2-11.6, `src/sdmxlib/inventory/EGM.md`, `_reader.py` (working tree, branch `docs/q1-product-granularity`); statcatlib `src/statcatlib/store/EGM.md`, `inventory.py`, `docs/design/products-editions-inventory.md` (§3, §15, §16, D31), `phase-2a-catalog-editions.md` (Alternative F) (working tree, branch `feat/gh-124-corpus-bench`).
**Result:** 2 Blocker, 9 Major, 7 Nit. The risk table omits both concurrency failures, migration and the restore collision.

## Blockers

### B1. Replacing an orphan record is unsafe, and H3 does not hold (lines 141-147, 204, 233; Question 3)
A slow writer and a dead writer look the same from storage. Local writers race routinely (statcatlib `tests/test_concurrent_seal.py`; journal repair from another process, `store/EGM.md:328-347`); on the server `concurrencyPolicy: Forbid` (§11.2 item 4) is the only serialisation.
1. A creates `history/42.json`; B's create fails.
2. B sees a different `root_sha256` and replaces the record under If-Match; it succeeds.
3. A, still alive, creates `inventory/42.json` and advances `CURRENT`.
4. B's root create fails; B retries at 43.

Version 42 exists, its record describes B's version that never happened, and A's record is gone. In the reverse interleaving (B replaces after A's root lands; nothing re-checks the root just before the put) a valid record is overwritten, and if record 43 already hashed record 42, the chain raises a false tamper alarm. A lease cannot fix it: a writer paused past the bound still writes its root later, and blob storage has no two-object transaction. The design reintroduces the hazard §6.6 (line 480) removes: a second compare-and-swap object that is not the commit point. The "reuse" branch never fires, since every attempt stamps `now` into the root (`inventory.py:422`). The validity rule (lines 141-142) is circular and uncheckable after expiry.
**Fix (keeps H3's order):** content-address records and never replace them. Name a record `history/<restore_epoch>/<seq>.<root_sha256>.json`, created exclusively by §6.6's rule. The valid record for N is the one whose name carries `sha256(inventory/N.json)`; a reader holding root N finds it with one GET, and the writer of N+1 fetches its predecessor the same way. Records from lost races are harmless candidates (at most `MAX_RACES` per commit) that compaction drops and `verify-catalog` counts. Delete the ETag rule, the overwrite permission and the portability question. H3's reason becomes "a root is created only after a record naming its hash exists". Owner alternative, changing H3: carry `changes` in the root as a 1.x optional field, so the root is both record and commit point, and copy it into a segment before deleting the root, as a Delta commit file does.

### B2. Expiry races writers on leaves (lines 156-159, 232)
A writer writes leaves before the root that names them (§6.6 line 484) and skips an existing leaf (`_write_leaf` returns on `path.exists()`, `inventory.py:339-344`). A new leaf is named by no root until step 4, and a reused leaf named only by an expiring root passes `exists()` and is then deleted. The reader does not validate leaves when it picks a root (`_root_at`, `_reader.py:100-117`), so that root becomes the head and every read of the product raises "is missing" (`_reader.py:181-184`). "After a release, never inside one" serialises only the server; local `prune` runs beside seals with no lock.
**Fix:** two-phase leaf deletion: phase 1 logs candidates; phase 2, at least a grace period G (longer than the longest commit) later, deletes only candidates no root created since names. Expiry holds the writer's serialisation (same job on the server; a catalog lock file that `prune` and `InventoryWriter.commit` both take locally). Add a conformance case. `verify-catalog` and release-job startup check the newest root's leaves.

## Majors

### M1. Seq numbers repeat across restore epochs; backups omit `history/` (lines 81-82, 99, 126-128, 151-152, 234)
`restore_epoch` is defined in §6.1 (line 334) and on every root (§6.2 line 347); a restore bumps it (§10.3 line 718), and the next write reuses seq numbers (statcatlib `products-editions-inventory.md:636-640`). `history/<seq>.json` then collides with the pre-restore record, which the current rule would replace. §10.3's order omits `history/`.
**Fix:** key records and segments by epoch; add `history/` to §10.3 before roots; a restore never deletes or rewrites old-epoch records; cite §6.1.

### M2. W is tied to the wrong window; GC reads the roots expiry deletes (lines 154-157, 163)
§11.4 (line 756) walks the chain through its window; §6.7 (line 509) keys repair on "within retention"; §11.6 (line 769) requires pod poll plus fetch < retention. GC runs concurrently in its own identity; if a vanished root reads as "no editions", it deletes data files. "Older than W" has two readings.
**Fix:** in §11.6's configuration, W >= max(`data/` GC window, pod poll plus fetch, backup retention), measured from the superseding root's `created_at`; K >= 2 for §6.6 step 2's fallback; GC fails closed on a missing root or leaf and refuses to start if the inequality fails; amend §11.4 to say GC walks retained roots plus their `retired` lists. Explain why W must cover backup retention: it matters only if backups mirror deletes or failover replicates them asynchronously; say which.

### M3. Goal 5 is contradicted, and delete on `history/` defeats the chain (lines 59-60, 160-163, 207, 235)
With write and delete on `history/`, the release identity can erase every record, write a fresh self-consistent chain, and bump `restore_epoch` to justify `prev_sha256: null`. The ETag rule needs overwrite permission, so create-only cannot be enforced (Azure RBAC write includes overwrite; S3 can enforce via the `s3:if-none-match` condition key if asked). HNS forgoes blob versioning (§10.2 line 714), but container-level time-based WORM remains if `history/` has its own container.
**Fix:** restate Goal 5 honestly, or give expiry its own delete-and-read identity; make `history/` create-only; make compaction optional or drop per-record deletion (3,650 objects a year is 4 LIST pages); put `history/` under a time-based immutability policy (shorter than the compaction delay if compaction stays); publish the newest record hash outside the catalog at every release; add a `history/` column to §10.1.

### M4. Records cannot rebuild a leaf (lines 105-115, 121-123, 168-176; Question 4)
An entry lacks `previous`, `manifest_sha256`, `schema_version`, `state_changed_at`, `structure_source`/`artefacts`, Phase 4 fields, and the leaf's `kind` and `lifecycle`. Without `schema_version`, "live at T" fails during a schema rollout (§6.4 line 446). Non-state changes (rescheduled `release_at`, `lifecycle` final to revisable, `correct`) change the leaf hash with empty `entries`. `reinstate`'s `from` is undefined. After expiry `leaf_sha256.to` points at nothing.

### M5. Segments are under-specified (lines 82, 88-90, 157-159)
A reader listing segments then records can run mid-compaction and see neither (a false "record removed"). Segments are not said to be created exclusively. A crash plus a moved W yields overlapping segments. Unpadded names do not list in order. Segment lines must equal the record's RFC 8785 bytes. Reading needs LIST (acceptable for audit tools; say so). Delta deletes old commits; Goal 1 says records are permanent.
**Fix:** exact RFC 8785 bytes everywhere; exclusive, contiguous, non-overlapping segments per epoch, 20-digit padded; a crashed compaction verifies and finishes; delete per-record objects one run later; readers read per-record objects first and re-list on 404; a record above the newest root is pending; segments are never deleted; conformance cases for each.

### M6. Migration, old writers and `prev_sha256` sourcing are missing (lines 126-128, 133-139, 204, 244-246)
**Fix:** the first version by a record-aware writer is a checkpoint, starts the chain with null, and pre-feature roots expire only after it exists; `verify-catalog` reports roots after it without records; a writer-version floor in `catalog.json` (Delta's `minWriterVersion`), with an alert for mixed writers; the predecessor record is found from root N's hash (B1).

### M7. The escape-route review is due (lines 209, 218-223; Question 1). See the answer below.

### M8. Checkpoint rule: clock, determinism, empty months, verification (lines 55-56, 151-153, 206, 232)
`created_at` uses the writer's clock (`inventory.py:422`); §6.4 (line 451) uses the storage server's. Skew yields two or zero "first" versions in a month. Expiry must decide checkpoints from records. H5's "at most a month" fails for a quiet catalog. GC deletes edition directories of retired editions (§11.4), so §10.3's full walk fails on old checkpoints, which are not restore points.
**Fix:** N is a checkpoint if N = 1, or first of a new epoch, or month(`created_at`[N]) is later than every earlier record's month, computed from records; optional count cap; H5 becomes "replays the versions since the previous checkpoint"; verify checkpoint roots for leaf presence and hash only, labelled audit-only.

### M9. The embargo boundary covers `history/` and any export (lines 105-115, 180-181; §10.1 lines 706-710)
Records reveal the release calendar. §10.1 makes the live-only replica the only touchpoint for analytics and governance tools (statcatlib D30).
**Fix:** `history/` has the readers of `inventory/`; an export outside the container drops events and entries for editions still embargoed, as `export(live_only=True)` does.

## Nits

- N1 (lines 30-33, 129): arithmetic checks out (1.33 MB; 1.46-4.86 GB a year) but omits the root's `retired` list and new leaves; a full republish in one version (§9.2) is 7,000 x ~400 bytes = 2.8 MB, more than a root. Give the worst case.
- N2 (line 110): `release_at` on an embargoed-to-live entry conflicts with §6.3 (null for non-embargoed).
- N3 (line 40): `--find-newest-consistent` is in statcatlib `products-editions-inventory.md:643`, not sdmxlib §6.7 or §10.3; after expiry it must LIST, since seq gaps stop a probe.
- N4: §6.6 step 2's fallback (`_reader.py:133-136`) walks absent seqs to the floor; K >= 2 keeps it cheap.
- N5 (lines 146-147): `verify-catalog` should also report a record whose root exists with another hash, and count losing candidates.
- N6 (line 145): S3 added `If-Match` on PutObject in November 2024 (`If-None-Match` in August 2024); S3-compatible stores differ; GCS uses generation preconditions; a local filesystem has no ETag, and object_store's `LocalFileSystem` may not implement `PutMode::Update` (verify). B1's fix removes the need.
- N7 (line 234): every record names the epoch.

## Answers

**Question 1.** The review is due. §6.6 (line 499; statcatlib `products-editions-inventory.md:161-164`) triggers on checkpoints, and line 22 defines a checkpoint of the Inventory itself; expiry changes what `inventory/` holds, affecting the reader fallback, GC, verification and restore. The design rebuilds three Delta pieces: a commit file that is record and commit point (B1 is the cost of splitting them), checkpoints, and VACUUM with retention (B2 is the cost of doing it without a grace period). The review need not adopt Delta: Phase 2a Alternative F's reasons (a Delta writer on laptops; the per-product, per-`schema_version` fast-forward) still hold. Record it as a decision in the §6.6 amendment, run the new conformance cases against the delta-rs prototype (sdmxlib `tests/support/inventory_backends.py`) so D31 stays proven, and add those cases to the Cross-repo contract.

**Question 3.** Not safe (B1). Name records by root hash, create exclusively, never replace, and select the valid record from the root's hash.

**Question 4.** Yes for every entry the version adds or changes; no for unchanged entries. Carry the full "to" `LeafEntry`, plus the leaf's `kind` and `lifecycle` when they change, and specify the canonical leaf encoding so a replay can rebuild each changed leaf and check it against `leaf_sha256.to`. This makes Goal 2 verifiable after expiry, makes "live at T" correct per `schema_version`, and gives the post-rollback `rebuild-inventory` what it needs. Cost: 300-400 bytes per changed entry, tens of KB per typical release, 3-5 MB once for a full republish.

**H1-H8.** H1 and H8 sound (H8 should say this log is kept forever, unlike Delta's). H2 sound only with B1's naming and M5's rules. H3 not guaranteed as specified. H4 holds within one epoch and only with an outside anchor. H5 needs M8's rule. H6 contradicts Goal 5 and widens the release identity's power.
