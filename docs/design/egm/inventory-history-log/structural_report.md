# Structural review: Inventory history log

**Target:** `docs/design/inventory-history-log.md` (lines 1-276)
**Lens:** `egm-structural`, against `feature-spec-standard.md` and the hub `CLAUDE.md` suite-design rules
**Read:** the target; the hub's only other suite design, `docs/design/localised-string.md`, and `docs/design/egm/localised-string/README.md`; sdmxlib spec §6, §10-§11.6, §14-§17 (working tree, branch `docs/q1-product-granularity`); statcatlib `docs/design/phase-2a-catalog-editions.md`, `docs/index.md`, `src/statcatlib/admin.py` (working tree, branch `feat/gh-124-corpus-bench`).
**Result:** 1 Blocker, 12 Major, 9 Nit. Headings are complete and well nested; the gaps are omitted content and contradictory claims. Against the local precedent, "Breaking changes and migration", "Acceptance criteria", "Staging" and the "Evidence:" metadata bullet are missing.

## Blocker

### 1. The §6.6 escape-route review is left open (lines 22, 218-223, 267-268)
Spec §6.6 (line 499) makes a need for checkpoints a trigger for a Delta-table review "rather than adding a feature". The design adds the feature and hands the review to reviewers (line 222, Q1); under the Alternatives Rule an open alternative counts as unconsidered. Lines 220-221 say the root and leaf protocol is unchanged, yet Terms line 22 defines a checkpoint as an Inventory version, and expiry changes which roots exist (§6.7 "within retention", §10.3, §11.4).
**Fix:** record the review outcome as decision H9 with reasons and the replacement §6.6 text; reword: "Expiry changes root retention; the root and leaf formats and the §6.6 write and read protocol are unchanged." Remove Q1.

## Major

### 2. Goal 5 contradicts the design (lines 59-60, 160-163, 207)
Line 162 gives the release job delete on `inventory/` and `history/`; §10.1 (line 700) grants write only. `history/` has no column in §10.1 and no named readers. "§10.1 adds" reads as if the spec already says it.
**Fix:** reword Goal 5; add the §10.1 table change with a `history/` column for every principal.

### 3. The embargo risk of the log and the export is missing (lines 104-113, 180-181, 228-236)
Records carry embargoed edition ids, `release_at` and the `embargo` flag. §10.1 (lines 706-710) says a copy of a catalog is outside the embargo boundary; a PROV export is a copy.
**Fix:** add a risk row, and a mitigation: the exporter emits only transitions of editions that have been `live`, or takes `live_only=True` as `CatalogAdmin.export` does. Name the reader identity for `history/`.

### 4. Readers cannot find segments or checkpoints without listing (lines 79-90, 149-158, 167-169)
§6.6 and §10.2 (lines 493, 714) say readers probe and never list. `<first>-<last>` names cannot be probed; checkpoint seqs are undiscoverable once `inventory/` has gaps. The segment format is claimed as format 1.0 (line 240) and is undefined: line bytes, zero padding, create-if-absent, overlap after a crash mid-compaction.
**Fix:** add a "Segment" subsection: line format, naming, a probe-able index (`history/segments/index.json` written conditionally, or a pointer in `CURRENT`), the overlap rule, and checkpoint discovery (`"checkpoint": true` in the record or a list in the index).

### 5. The retention rule omits §11.6's inequalities (lines 154-157)
§11.6 (lines 768-770) also requires pod poll interval plus fetch time < Inventory version retention; GC reads the chain back through its window (§11.4, line 756). K is undefined.
**Fix:** state backup retention <= `data/` GC window <= W and pod poll + fetch < W, in §11.6's existing checker; define K; expiry refuses to start when the check fails.

### 6. The chain cannot detect a removed tail (lines 52-54, 170-171, 205, 235)
Goal 2 promises detection of removal; a linear chain detects neither a truncated tail nor a rewritten segment without an outside hash, and risk row 4 specifies none.
**Fix:** either specify the anchor (for example `CURRENT` carries the newest record hash, and the head hash goes to a location outside the release job's write rights, named in §10.1), or narrow Goal 2. Add object lock on `history/` as an alternative.

### 7. The orphan-record retry rule is unresolved but cited as a mitigation (lines 141-147, 233, 272-273)
Race: writer A writes record N and stalls; writer B replaces record N; A then wins `inventory/N.json`. Root N and record N disagree. Local catalogs have concurrent writers (spec §16 M8, line 891). Local files have no ETag.
**Fix:** specify the rule (a writer replaces record N only after root N is decided, and rewrites it to match the root that exists; or the root is authoritative and readers repair); give the local mechanism; add a conformance case; remove Q3.

### 8. The "normative" PROV-O mapping has gaps (lines 180-196, 208, 269-271)
`reason` has two targets; PREMIS is optional; kinds end in "…". No `stc:` namespace IRI and no IRI rule for versions or editions. Rows need data the record lacks (manifest `previous`, every leaf, `catalog_id`). Fields with no row: `entries` from/to, `release_at`, `leaf_sha256`, `root_sha256`, `prev_sha256`, `extensions_sha256`, `restore_epoch`, `embargo`. The tombstone row invalidates the edition, but §6.4 `reinstate` (line 443) moves a tombstone back to `superseded`, and a PROV invalidation cannot be undone; it also contradicts H7. `prov:Attribute` is no PROV-O class.
**Fix:** one target per row; namespace and IRI rule; a row or "not exported" for every field; state the export's inputs; map retirement as invalidation of the last state entity.

### 9. Decisions restate instead of justifying (lines 207-209)
H8 defers its content ("the specification states where this log differs"). The main difference: in Delta the log entry is the commit; here the root commits and the record is a side record, which drives H3 and finding 7. H6 repeats line 161; H7 repeats line 191 and does not weigh Q2's alternative.
**Fix:** add "Differences from Delta Lake and Iceberg" under H8; give H6 and H7 comparative reasons.

### 10. Expected alternatives are missing (lines 211-226)
Object-store versioning or object lock (§10.2, line 714, notes HNS gives up versioning); roots as deltas against a checkpoint; the §14 governance mirror (line 845) as the audit store; the delta carried inside the root; signed records (spec §17 Q3); PROV alternatives for H7. Line 215 should cite GH-19 and the owner's reason. Lines 85 and 226: S3 Express One Zone directory buckets support append since 2024; say "no append in S3 general-purpose buckets or in a portable API".
**Fix:** one bullet per alternative with a specific rejection reason.

### 11. No conformance-case table, acceptance criteria or staging (lines 240-263)
The five cases are nouns. No negative cases: tampered record, removed tail, orphan record, overlapping or missing segments, writer race, unknown `format_version`, expiry against a checkpoint's leaves, a reader fetching an expired leaf. The example uses `…` and `0199…a1`, so "the schemas validate the examples here" (line 255) fails any hex or UUID pattern.
**Fix:** a "Conformance cases" table (case, setup, expected result, repository); per-repository acceptance criteria; a "Staging" table as in localised-string.md:538-616; full values in the example.

### 12. Handoff names sections without content; statcatlib's has no acceptance checks (lines 251-263)
Open: where `history/` goes in the §10.3 backup order; what §6.7 `rebuild-inventory` may now do; whether §11.4 GC reads across gaps; the §6.6 text.
**Fix:** a "Specification changes" table (section, change); acceptance checks under statcatlib.

### 13. Migration and breaking changes are missing
Existing catalogs with roots 1..N and no history; older tools that assume a full chain (`rebuild-inventory`, GC, `--find-newest-consistent`); a marker so old tools refuse; the record versioning rule (spec line 384 has one for roots).
**Fix:** add "Breaking changes and migration".

## Nits

- Questions for review (265-276) belong only in the draft; convert answers to decisions; leftovers go to spec §17.
- The append rationale appears three times (lines 85, 203, 226). "What a reader can answer" (165-176) is rationale inside Design.
- Risk row 1 (232) relies on a dry run and a `verify-catalog` check the Design never specifies. Checkpoint roots name editions GC has since deleted (§11.3, §11.4), so `verify-catalog` must not check their manifests; say checkpoints are audit artefacts and are not restorable (§10.3).
- Goal 3 (55-56): state the bound (K + versions within W + one per month + one per restore) and `history/` growth in MB a year.
- Line 40 attributes `--find-newest-consistent` to §6.7 and §10.3; the flag appears only in statcatlib `docs/design/products-editions-inventory.md:643` and `docs/design/phase-2a-catalog-editions.md:174`. Line 35's P7 is `phase-2a-catalog-editions.md` line 274. Link "statcatlib RFC decision 31", Phase 5 and Phase 7.
- Line 6: write the issue as GH-19 in the hub.
- Metadata: add "Evidence:" (sources for 1.3 MB and 190 bytes) and a "Reviewed against" commit line.
- Record format (115, 121-123): does `retired` list only this version's new tombstones or every tombstone in the window; what `leaf_sha256.from`/`to` hold for an added or removed product; consider `catalog_id`.
- Line 151: name the clock that decides "first version of each UTC month" (§6.4, line 451, uses the storage server's clock). Line 247: state the guarantee pods get as roots expire (newest K, pod poll inequality). Add "sdmxlib-rest: none" under Handoff.

## Goal-to-design trace

| Goal | Design element | Decision | Gap |
|---|---|---|---|
| G1 | Record | H1 | none |
| G2 | `prev_sha256`, `root_sha256` | H3, H4 | findings 6, 7 |
| G3 | Checkpoints and expiry | H5, H6 | findings 4, 5 |
| G4 | PROV-O mapping | H7 | finding 8 |
| G5 | Expiry identity | H6 | finding 2 |
