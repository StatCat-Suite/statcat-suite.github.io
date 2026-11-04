# Zoom-out review: Inventory history log

**Target:** `docs/design/inventory-history-log.md` (lines 1-276)
**Lens:** `egm-zoom-out`, against `zoom-out-standard.md`
**Read:** the target; sdmxlib spec §6.1-6.8, §10.1-10.3, §11.1-11.6 and `src/sdmxlib/inventory/EGM.md` (working tree, branch `docs/q1-product-granularity`); statcatlib `src/statcatlib/store/EGM.md`, `schema.py`, `docs/index.md`, `docs/design/products-editions-inventory.md` (working tree, branch `feat/gh-124-corpus-bench`). None of the cited sections looks branch-only.
**Verdict:** revise. Ship the audit record first; ship expiry after the §6.6 review; make the PROV-O mapping informative.

## 1. The arithmetic holds, the storage cost is small, and Goal 3 claims a bound the design does not give (Major; lines 28-46, 55-56)

7,000 x 190 bytes = 1.33 MB per root; 1,095 to 3,650 roots a year = 1.46 to 4.9 GB. About 88 bytes of each `products` entry is the `leaf` path, which `leaf_sha256` determines. 5 GB a year of hot blob storage costs under a dollar a month; 3,650 objects a year is one LIST page. `rebuild-inventory` reads manifests, not roots (spec §6.7, line 514); `--find-newest-consistent` walks back from the newest root (statcatlib `products-editions-inventory.md:643`); both are unbuilt Phase 9 tools. The real drivers are the audit gap and the spec's existing assumption that roots expire (§11.6, §6.7 "within retention", statcatlib RFC windows at `products-editions-inventory.md:677-682`). Monthly checkpoints accrue for good, so the root count is unbounded. With W = 90 days, 270 to 900 roots (0.35 to 1.2 GB) stay in steady state.

**Fix:** restate the problem with cost figures plus the audit gap; Goal 3 becomes "`inventory/` holds the roots within W, the newest K, and one checkpoint a month"; give an example W.

## 2. Three separable changes are bundled; ship the record first (Major; lines 73-196, 238-263)

(a) the record, write order and chain; (b) checkpoints, expiry, segments and a new delete right; (c) a normative PROV-O mapping and a PROV-JSON export. (a) alone meets Goals 1, 2, 4 and 5, adds no delete right, and does not touch §6.6's escape-route clause. It must come first anyway: records must exist for the versions expiry later deletes.

**Fix:** stage the Handoff. S1: record, write order, `verify-catalog` check, `history/` in the §10.3 backup order (sdmxlib#361). S2: expiry and checkpoints, after the §6.6 review. S3: the export, in a statcat-serve design.

## 3. Question 1: the §6.6 review is due; run it in this design (Major; lines 22, 149-163, 209, 218-223)

§6.6 (spec line 499): "If it ever needs checkpoints, leaf compaction or more tree levels, that need triggers a review of replacing it with a Delta table of Inventory rows rather than adding a feature." Terms line 22 defines a checkpoint as an *Inventory version* kept for good, so the checkpoints are on the Inventory, not only on the log. After this design the system is a per-version JSON commit log, a full snapshot per version, monthly checkpoints, and VACUUM-like expiry: Delta's structure in all but name. The prototype exists (`src/sdmxlib/inventory/EGM.md:74-80`; statcatlib RFC decision 31, `products-editions-inventory.md:898`). The likely outcome is to keep the Inventory: a Delta reader lists its log, losing §6.6's no-LIST probe; Delta's log retention (`delta.logRetentionDuration`, 30 days by default) and VACUUM delete history, so Delta would still need a separate permanent audit log; and a swap is a far larger change.

**Fix:** add a "§6.6 review" section with that comparison and its conclusion; in sdmxlib#361 amend the clause to record the review and to name what still triggers one (leaf compaction, more tree levels, roots too large to write per version); delete Question 1.

## 4. Make the PROV-O mapping informative; the exporter belongs in statcat-serve (Major; lines 57-58, 178-196, 208, 240-243, 255-257)

statcatlib's `lineage` table maps `prov:wasDerivedFrom` between datasets inside an edition (`docs/index.md:106`, `schema.py:335-347`) and shares no identifiers with Inventory versions, so Goal 4's "already use" is nominal. Line 187 offers two mappings for `reason`. Rows 189-190 need leaves and manifests that expiry deletes, so an export from the log alone cannot produce them for old versions. Lines 67-69 put exporters in statcat-serve, yet lines 241-242 and 256 give sdmxlib, which has no RDF dependency, a PROV-JSON export as an acceptance criterion.

**Fix:** Goal 4 becomes "the record carries the fields a PROV-O export needs"; keep the table informative and H7 as the intended reading; move the normative mapping, export and validation test to the statcat-serve exporter design; remove them from sdmxlib's contract and acceptance.

## 5. Segments are speculative and cost a delete right on the audit log and RFC 8785 (Major; lines 81-90, 126-128, 158-159, 162, 203, 235)

Records total about 1 to 18 MB a year. Segments force a LIST of `history/segments/`, need delete on `history/` for the identity the chain guards against (line 235), and are the only reason for RFC 8785: every other hash in the suite is over stored bytes (spec lines 358, 375, 491).

**Fix:** drop segments and delete on `history/`; make `history/` create-only; define `prev_sha256` over the previous record's stored bytes; add segments later as a 1.x addition if a listing cost is measured. (Synthesizer note: this touches H2, which is part of the owner's Delta Lake-style structure decision; it is offered as a safety argument, see the consolidated report.)

## 6. Goal 2 needs an outside anchor; backups supply one (Major; lines 52-54, 170-171, 235)

The design names no place outside the catalog that holds a hash. Backups (§10.3) sit outside the release job's write path.

**Fix:** add `history/` to the §10.3 backup order, records before roots; make the newest record hash in the latest backup the anchor `verify-catalog` checks; name immutable (WORM) backup retention as the stronger form.

## 7. Existing pieces answer much of the audit question; answer Question 4 with no (Nit; lines 42-46, 92-129, 274-275)

Every root already records `event {actor, reason, kind}`, `created_at`, `producer`, `previous_inventory` (spec §6.2, line 353). Leaves are content-addressed, so a diff while roots exist compares `leaf_sha256` values. Leaf entries carry `state_changed_at`; manifests carry `previous`. GC keeps a deletion log (§11.4) and `expunge` an audit entry (§11.3, line 752). For Question 4: "live at T" needs edition ids only; a rebuild gets `previous` and `schema_version` from manifests and `manifest_sha256` by hashing them; the record supplies state, which manifests lack.

**Fix:** say the record header copies root fields because roots expire; answer Question 4 with no; say whether the `expunge` audit entry and the GC deletion log stay separate.

## 8. Use §11.6's "Inventory version retention" for W (Nit; lines 23-24, 154-155)

**Fix:** rename W; add "backup retention <= Inventory version retention" and K to the §11.6 configuration that GC and prune check.

## 9. PREMIS and the RFC 9162 "room" are speculative (Nit; lines 70-71, 194-196, 205, 235)

**Fix:** delete the PREMIS paragraph or reduce it to one informative sentence; replace the RFC 9162 non-goal with "A Merkle log (RFC 9162) can later be built over record hashes with no format change."
