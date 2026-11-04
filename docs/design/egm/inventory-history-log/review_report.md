# EGM review report: Inventory history log, expiry and PROV-O mapping

**Target:** `docs/design/inventory-history-log.md`, lines 1-276. The draft is uncommitted, on hub branch `docs/design-inventory-history-log` at `17d6e5d`.
**Date:** 2026-11-03
**Mode:** REVIEW, consolidated. No implementation plan section was found. The feature range is lines 1-237. The Cross-repo contract and Handoff sections (lines 238-263) were reviewed as the detailed range.

## What was read

The design is based on sdmxlib `b6c79892`, statcatlib `95fd7ad` and hub `17d6e5d`. The reviewers could read only the working trees, which were on these branches:

- sdmxlib: `docs/q1-product-granularity`;
- statcatlib: `feat/gh-124-corpus-bench`;
- sdmxlib-rest: `main`.

Every `file:line` below refers to those working trees. No reviewer found that a finding depends on text that exists only on the branch. The one exception is the 7,000-product figure, which comes from sdmxlib `docs/design/sharded-bundle-catalog-plan.md:94`. Before the design is revised, check the cited spec lines against `git -C ../sdmxlib show origin/main:docs/design/sharded-bundle-catalog.md`.

The reviewers had no shell and no web access, with two consequences:

- Nobody read the owner's comments on GH-19. The reviewers treated decisions H1-H8 as the owner's decisions, as the brief asked.
- The W3C PROV, PREMIS and DCAT points rest on the reviewers' own knowledge of those standards. Where a reviewer was unsure, the text says so, and those points need checking against the documents before the specification cites them.

## Reviewer reports

| Lens | Report |
| --- | --- |
| Zoom-out (`egm-zoom-out`) | `zoom_out_report.md` |
| Comprehension (`egm-comprehension`) | `comprehension_report.md` |
| Design, PROV-O (`egm-design`, instance B) | `prov_o_report.md` |
| Design, storage and safety (`egm-design`, instance A) | `design_storage_report.md` |
| Structural (`egm-structural`) | `structural_report.md` |
| Style (`egm-style`) | `style_report.md` |
| Implementation readiness (`egm-implementation-readiness`) | `implementation_readiness_report.md` |
| Codebase details (`egm-codebase-details`) | `codebase_details_report.md` |

This run skipped the intermediate zoom-out stage, because the lenses ran in parallel.

## Summary

The design has 7 Blocker, 17 Major and 10 Nit findings.

The audit record is worth building, and H7, the specialization model, is the right PROV reading once one change is made. Two parts of the design are unsafe as written:

- **The write and retry protocol.** It contradicts H3: a version can exist whose record describes a different root.
- **Expiry.** It can delete leaves that a writer is about to name. It also leaves gaps in `seq` that the current reader mistakes for the end of the chain.

The PROV-O mapping is labelled normative, but it has no namespace, no rules for minting IRIs, and no worked example, so no test can check it. Three of its rules also break PROV-CONSTRAINTS on rollback and `reinstate`.

Every Blocker can be fixed without reopening the owner's decisions:

- deltas plus monthly checkpoints;
- expiry by the release job;
- a linear hash chain;
- the Delta Lake-style structure.

Finding 1's fix changes the shape of the record keys and keeps the write order of H3.

## Prioritized findings (Blocker, then Major, then Nit)

### Blockers

#### 1. Replacing an orphan record races a live writer and breaks H3 - Severity: Blocker
* **Reviewer Lens:** design (storage), implementation readiness, codebase details, comprehension, structural
* **Affected Scope:** lines 141-147, 204 (H3), 233, 272-273 (Q3)
* **Discrepancy Description:** Storage cannot tell a slow writer from a dead one. The race runs like this:
  1. Writer A creates `history/42.json`.
  2. Writer B finds that record, and finds no `inventory/42.json` yet. B replaces the record under If-Match.
  3. A, still alive, wins `inventory/42.json`.
  4. B loses the root and retries at 43.

  Version 42 now exists, and its record describes B's root, which was never written. If the steps interleave the other way, a valid record is overwritten, and a record 43 that already hashed record 42 raises a false tamper alarm. A lease cannot fix this: a writer paused past the lease still writes its root. Local writers race as a matter of course (statcatlib `tests/test_concurrent_seal.py`). Three further problems:
  - The "reuse" branch never fires. Every attempt stamps a new `created_at` (sdmxlib `_rules.py:515`; statcatlib `inventory.py:417-428`).
  - The writer is local-disk only, through `create_exclusive` and `os.link` (`storage/_files.py:89-116`). It has no ETag and no conditional replace.
  - The validity rule at lines 141-142 is circular.
* **Rationale & Recommendation:** Content-address records and never replace them.
  - Name each record `history/<restore_epoch>/<seq:012d>.<root_sha256>.json` and create it by the §6.6 create-if-absent rule.
  - The valid record for `seq` N is the one whose name carries `sha256(inventory/N.json)`. A reader that holds root N fetches it with one GET. The writer of N+1 finds its predecessor the same way.
  - Records left by a lost race are orphans. `verify-catalog` lists them and expiry deletes them.
  - Delete the ETag rule and Question 3.
  - Restate H3's reason: "a root is created only after a record naming its hash exists".
  - Add a conformance case for the race.

#### 2. A restore reuses `seq`, so records collide across epochs and the chain breaks silently - Severity: Blocker
* **Reviewer Lens:** codebase details, design (storage), comprehension, implementation readiness
* **Affected Scope:** lines 81-82, 99, 126-128, 234
* **Discrepancy Description:** After a restore, the next write reuses `seq` numbers. The sources:
  - sdmxlib `conformance.py:110-115`;
  - statcatlib `products-editions-inventory.md:638-639`;
  - `next_root` numbers versions `previous.seq + 1` (`_rules.py:506`).

  `history/<seq>.json` then names the record of a lost version, and the retry rule would replace it. That destroys the audit record of exactly the versions the restore lost. `restore_to` also keeps the epoch, so line 127's rule (`null` at an epoch change) never fires. A null `prev_sha256` at an epoch change lets anyone start a fresh chain. `restore_epoch` is defined in spec §6.1 (line 334), and the design never cites it.
* **Rationale & Recommendation:**
  - Key records and segments by epoch, which finding 1's naming already does.
  - State that no record is ever replaced or deleted, except by compaction.
  - Give the first record of an epoch a required `previous_epoch_last_sha256` field.
  - Cite §6.1.
  - Add a conformance case: restore, write the reused `seq`, and check that the old record survives.

#### 3. Seq gaps left by expiry make the reader return a stale version - Severity: Blocker
* **Reviewer Lens:** codebase details
* **Affected Scope:** lines 37-38, 64 (non-goal), 151-158
* **Discrepancy Description:** sdmxlib `_reader.py:119-148` walks back from a bad `CURRENT` root down to the floor, then probes forward to the first absent `seq`. With no `CURRENT`, it starts from 0. Two cases go wrong once expiry has run:
  - `CURRENT` is missing, for example because §10.3 backs it up last. A fresh reader reads checkpoint 1, finds root 2 expired, and returns version 1 as the newest.
  - `CURRENT` is corrupt, and so are the K-1 roots below it. The reader walks past the gap to a month-old checkpoint.

  The non-goal "changing how a reader finds the current version" therefore cannot hold. Spec §6.6 step 3 (line 492) assumes there are no holes in the `seq` range.
* **Rationale & Recommendation:** Add a §6.6 rule and a matching reader change:
  - Expiry deletes only roots below the oldest of the newest K, with K ≥ 2.
  - The reader's fallback walks back at most K versions.
  - A missing `CURRENT` on a catalog that holds checkpoints is an error, never a probe from 1.

  Add conformance cases for both failures. Name the sdmxlib release that carries the change, since sdmxlib-rest reads through it. Move this item from Non-goals into the design.

#### 4. Expiry races writers on leaves - Severity: Blocker
* **Reviewer Lens:** design (storage), implementation readiness, codebase details, comprehension
* **Affected Scope:** lines 156-163, 232, 236
* **Discrepancy Description:** A writer writes its leaves before the root that names them (§6.6 line 484). It also skips a leaf that already exists (`_write_leaf`, statcatlib `inventory.py:339-344`) and reuses the base version's leaf refs (`inventory.py:412-416`). Expiry can therefore delete a new leaf that no root names yet, or a reused leaf that only an expiring root names. The new head then names a missing leaf. The reader does not check leaves when it picks a root (`_reader.py:100-117`), so every read of that product fails (`_reader.py:181-184`). The rule "after a release, never inside one" serialises only the server. A local `prune` runs beside seals with no lock.
* **Rationale & Recommendation:**
  - Delete leaves in two phases. Phase 1 logs the candidates. Phase 2 runs at least a grace period G later, where G is longer than the longest commit, and deletes only the candidates that no root created since then names.
  - Require expiry to hold the writer's exclusion: on the server, the same job; locally, a catalog lock that both `prune` and `InventoryWriter.commit` take.
  - Have writers always call create-if-absent, and treat "exists" as success.
  - Recompute reachability from a re-read head after deleting roots and before deleting leaves.
  - Add a conformance case.

#### 5. The §6.6 escape-route review is triggered and left open - Severity: Blocker
* **Reviewer Lens:** structural, zoom-out, design (storage), codebase details
* **Affected Scope:** lines 22, 209 (H8), 218-223, 267-268 (Q1)
* **Discrepancy Description:** §6.6 (line 499) says: "If it ever needs checkpoints, leaf compaction or more tree levels, that need triggers a review of replacing it with a Delta table of Inventory rows rather than adding a feature." Line 22 defines a checkpoint as an *Inventory version* kept for good. Expiry also changes which roots exist, which the reader fallback, GC (§11.4), repair (§6.7) and backups (§10.3) all depend on. The claim that the design adds checkpoints "to a log beside the Inventory" therefore contradicts the design's own Terms. Under the Alternatives Rule, an alternative left open counts as not considered.
* **Rationale & Recommendation:** Run the review in this design.
  - Add a short "§6.6 review" section with decision H9.
  - Give the likely outcome, keeping the Inventory, with its reasons:
    - A Delta reader lists its log, which gives up §6.6's probe without LIST.
    - Delta's log retention and VACUUM delete history, so a permanent audit log would still be needed beside it.
    - Phase 2a Alternative F's reasons still hold.
  - Run the new conformance cases against the Delta prototype (sdmxlib `tests/support/inventory_backends.py`), so that D31 stays proven.
  - In sdmxlib#361, amend the §6.6 clause to record the review and its date, and to name what still triggers one: leaf compaction, more tree levels, or roots too large to write per version.
  - Remove Question 1.
  - Cite the RFC correctly: the escape route is RFC §3 (`products-editions-inventory.md:161-164`), and D31 is the prototype (lines 898-899).

#### 6. The PROV-O mapping is called normative but cannot be tested - Severity: Blocker
* **Reviewer Lens:** design (PROV-O), implementation readiness, structural, zoom-out, codebase details
* **Affected Scope:** lines 180-196, 240-243, 255-257
* **Discrepancy Description:**
  - The `stc:` namespace is defined nowhere in the four repositories.
  - There is no rule for minting IRIs for versions, activities, editions, state entities, leaves or agents.
  - `reason` has two targets.
  - Seven of the nine kinds are left out as "…".
  - There is no worked example in triples.

  PROV-JSON is a W3C Member Submission. Its JSON Schema checks syntax only, so "validates against PROV-JSON" would pass wrong IRIs or duplicate generations. Two correct implementations could produce different graphs.
* **Rationale & Recommendation:** Pick one route.
  - **(a) Complete the mapping.** Add these to the Cross-repo contract:
    - the namespace `https://statcat-suite.github.io/ns/inventory#`, owned by sdmxlib and published by the hub, with an `owl:versionIRI`;
    - one `rdfs:subClassOf prov:Activity` per kind, and a fallback to a plain `prov:Activity` with `stc:kind` for an unknown kind;
    - the IRI table in `prov_o_report.md` F7, with versions as `<base>inventory/<restore_epoch>/<seq>`, editions as `urn:uuid:<edition_id>`, and hashes as RFC 6920 `ni:` IRIs;
    - a golden Turtle file of the worked example.

    Acceptance then means three checks: the RDF output is graph-isomorphic to the golden file; the PROV-JSON output loads with the `prov` package and converts to the same graph; and SHACL or SPARQL checks pass for generation-uniqueness, invalidation-uniqueness, generation-precedes-invalidation and specialization ordering, over the rollback, reinstate and restore cases.
  - **(b) Mark the section informative.** Move the normative mapping and the exporter into the statcat-serve exporter design. This matches Non-goal line 67-69, which puts exporters there.

  The reviewers lean to (b) for sdmxlib#361. Under (b), the record must still carry the fields an export needs (findings 9 and 12).

#### 7. Existing catalogs have no migration path - Severity: Blocker
* **Reviewer Lens:** implementation readiness, design (storage), comprehension, structural
* **Affected Scope:** no section; lines 126-128, 204, 244-246
* **Discrepancy Description:** Catalogs written by statcatlib 0.13.0 have roots and no records. Undefined:
  - the first record and its `prev_sha256`;
  - whether roots from before the feature may expire;
  - how `verify-catalog` treats the gap.

  Older writers, which ignore unknown files, keep writing roots without records, so H3's "no gaps" fails silently.
* **Rationale & Recommendation:** Add a "Breaking changes and migration" section:
  - The first version written by a writer that knows about records, M, is a checkpoint. It has `prev_sha256: null` and a required `history_starts_at: M`.
  - Roots below M never expire, or a one-time backfill diffs them into records. Pick one.
  - Lock out old writers by bumping `catalog.json` to 2.0. `decode_catalog` refuses another major version (`_format.py:268-276`), and the Inventory reader never reads `catalog.json`, so pods are unaffected.
  - State the record's versioning rule, adopting spec §6.3 line 384.

### Major: PROV-O mapping

#### 8. A state entity must stand for one interval, since states come back (H7) - Severity: Major
* **Reviewer Lens:** design (PROV-O), comprehension, codebase details
* **Affected Scope:** lines 191, 208, 269-271 (Q2)
* **Discrepancy Description:** PROV-CONSTRAINTS allows an entity one generation and one invalidation (generation-uniqueness and invalidation-uniqueness; the reviewer did not verify the constraint numbers). An edition re-enters `live` by rollback (§6.4 lines 440-442) and re-enters `superseded` by `reinstate` (line 443). One entity "edition X as live" would therefore be generated twice. The alternatives do not work:
  - A qualified generation of the edition fails the same way, because the seal generates the edition once.
  - A PROV-DM attribute cannot carry a state, because attributes are an entity's fixed aspects.
  - The leaf entry within a version expires with the leaf.
* **Rationale & Recommendation:** Keep H7 and make the entity specific.
  - Rewrite row 191: "an edition's state is a `prov:Entity` for one interval in one state, identified by edition, `restore_epoch` and the `seq` that entered it. It is `prov:specializationOf` the edition and carries `stc:state`. The entering version's activity generates it, and the leaving version's activity invalidates it."
  - Add `from_seq` to each entry, so that one record can name the state it leaves.
  - Require that `created_at` never decreases with `seq` within an epoch, so that generation precedes invalidation even when writers' clocks drift.
  - Record the rejected alternatives under Alternatives.

#### 9. A tombstone must not invalidate the edition, and `retired` has no defined scope - Severity: Major
* **Reviewer Lens:** design (PROV-O), codebase details, comprehension, implementation readiness
* **Affected Scope:** lines 102, 115, 192
* **Discrepancy Description:**
  - **Invalidation is final in PROV.** `reinstate` brings a tombstone back to `superseded` (§6.4:443), and the edition's bytes survive until the backup window closes.
  - **`retired` has no defined scope.** In the root, `retired` lists every tombstone within the window (§6.2:352). Copied into each record, it would re-assert the invalidation with a new activity in every version.
  - **The example retires inside a `release` record.** Retirement has its own kind, `retire`, written by the prune job (§6.4:444; `admin.py:525-528`).
* **Rationale & Recommendation:**
  - Model retirement as a state. The `retire` activity invalidates the last state entity and generates "X retired since N". `reinstate` reverses that.
  - Never invalidate the edition entity, except perhaps at `expunge`.
  - Define `retired_added` and `retired_removed` as this version's changes only.
  - Move the example's tombstone into a `retire` record.

#### 10. Agents: `hadRole` needs a qualified association, and actor and producer form a delegation - Severity: Major
* **Reviewer Lens:** design (PROV-O), codebase details, comprehension, implementation readiness
* **Affected Scope:** lines 102, 186, 188
* **Discrepancy Description:** `prov:hadRole` has domain `prov:Influence`, so it cannot sit on an unqualified `wasAssociatedWith`. The actor is a token object id, or `<os user>@<hostname>` locally (`inventory.py:214-220`), and may be a person driving `CatalogAdmin`. Typing it `prov:SoftwareAgent` is therefore a guess. The producer is the program acting for the actor.
* **Rationale & Recommendation:**
  - Use `prov:qualifiedAssociation [ a prov:Association ; prov:agent … ; prov:hadRole … ]`, and keep the unqualified link as well.
  - Type the actor as `prov:Agent` with role `stc:actor`.
  - Make the producer a `prov:SoftwareAgent` (`https://pypi.org/project/statcatlib/<version>/`) with role `stc:writer` and `prov:actedOnBehalfOf` the actor.

#### 11. Times and reason: one instant is not an activity span, and a reason is not a Plan - Severity: Major
* **Reviewer Lens:** design (PROV-O), style, structural
* **Affected Scope:** lines 100, 110, 185, 187
* **Discrepancy Description:**
  - `created_at` is fixed at write step 2, before the record, the root and `CURRENT`. Taking both start and end from it claims a zero-length activity. PROV allows that, but it is not true.
  - `release_at` on an entry that goes `live` conflicts with §6.3 line 378, under which it is null outside `embargoed`.
  - `prov:Plan` is a set of intended steps, and "08:30 release" is a reason.
  - A normative row with two outputs cannot be tested.
* **Rationale & Recommendation:**
  - Emit `prov:generatedAtTime` and `prov:invalidatedAtTime` from `created_at`, defined as "the instant the writer fixed the version's content", and emit no start or end time.
  - Map `release_at` to `stc:releaseAt` on the embargoed state, and move it in the record to the entry that enters `embargoed`.
  - Map `reason` only to `stc:reason`, declared `rdfs:subPropertyOf rdfs:comment`.

#### 12. Rows need data that the record lacks once roots expire - Severity: Major
* **Reviewer Lens:** design (PROV-O), comprehension, implementation readiness, zoom-out
* **Affected Scope:** lines 105-123, 189-190
* **Discrepancy Description:** Three rows need data the record does not carry:
  - "A `prov:Collection` of its leaves" needs every leaf.
  - An edition's `prov:wasRevisionOf` needs the manifest's `previous`, which only the leaf holds.
  - IRIs need `catalog_id`.

  Leaves are the right members of the collection, and a content-addressed leaf can be shared across versions. Membership is open-world, so asserting only the leaves that changed is sound.
* **Rationale & Recommendation:**
  - Row 189 becomes: "`prov:hadMember` each leaf this version changed (every leaf when exported from a retained root)".
  - Add a row: "a changed leaf `prov:wasRevisionOf` the leaf it replaced".
  - Add `previous` to new entries, which follows from the answer to Question 4.
  - Add `catalog_id` to the record.
  - Note PROV-Dictionary (a W3C Working Group Note) only as an informative extension.

#### 13. Goal 4 overstates the alignment with `lineage` and DCAT-AP - Severity: Major
* **Reviewer Lens:** design (PROV-O), zoom-out, codebase details
* **Affected Scope:** lines 57-59
* **Discrepancy Description:**
  - **`lineage` shares no IRIs with this graph.** statcatlib's `lineage` links dataset ids (SDMX URNs; `schema.py:335-347`, `docs/index.md:106`), and it already maps more than `wasDerivedFrom`: `docs/tutorial.md:560-569` maps `revision_of` and `replaces` to `wasRevisionOf`. It shares no IRI with editions or versions, so the two graphs never join.
  - **DCAT-AP 3 uses PROV lightly.** The terms are `prov:wasGeneratedBy` and `prov:qualifiedAttribution`. `dct:provenance` is Dublin Core, and statcatlib's DCAT side uses it (`model/quality.py:27`).
  - **StatDCAT-AP adds no PROV.**
  - **DCAT 3 versioning may line up.** DCAT 3 declares `dcat:previousVersion` a sub-property of `prov:wasRevisionOf` (the reviewer was not certain of this; check DCAT 3). If it does, this mapping is consistent with a DCAT export.
* **Rationale & Recommendation:** Rewrite Goal 4: "The record maps to W3C PROV-O. The product IRI joins it to DCAT: a product is the `dcat:Dataset` each edition `prov:specializationOf`, and a DCAT export lists editions with `dcat:hasVersion` and `dcat:previousVersion` following manifest `previous`. statcatlib's `lineage` joins only if a later design links products to dataset URNs." Also add "each edition `prov:specializationOf` its product" to the mapping.

#### 14. The embargo boundary does not cover `history/` or the export - Severity: Major
* **Reviewer Lens:** structural, design (storage), implementation readiness, codebase details
* **Affected Scope:** lines 104-113, 180-181, risk table 228-236
* **Discrepancy Description:** Records name embargoed editions, their `release_at`, and the `embargo` flag, which together reveal the release calendar. §10.1 (lines 706-710) puts a copy of a catalog outside the embargo boundary, and makes the live-only replica the only touchpoint for analytics tools. The design names no readers for `history/` and gives the export no filter.
* **Rationale & Recommendation:**
  - Give `history/` the same readers as `inventory/`.
  - Have the exporter take `live_only=True` by default and drop the events and entries of editions still embargoed, as `CatalogAdmin.export` does.
  - Add a risk row.

### Major: format, write order, expiry and safety

#### 15. Goal 5 is contradicted, and delete on `history/` lets one identity rewrite the chain - Severity: Major
* **Reviewer Lens:** all eight lenses
* **Affected Scope:** lines 52-54 (Goal 2), 59-60 (Goal 5), 160-163, 170-171, 205, 207, 235
* **Discrepancy Description:** §10.1 (line 700) gives the release job write only on `inventory/`, and has no `history/` column. The design adds delete on both prefixes. With write and delete on `history/`, the release identity can erase every record and write a fresh chain that checks out, and can bump `restore_epoch` to justify `prev_sha256: null`. A linear chain also cannot detect a truncated tail. Goal 2 therefore promises more than the design delivers, and risk row 4 specifies no mitigation.
* **Rationale & Recommendation:**
  - Rewrite Goal 5: "No new principal gains access. The release job gains delete on `inventory/` and `history/`, used only by expiry."
  - Add a `history/` column to §10.1.
  - Make `history/` create-only, which finding 1's naming allows.
  - Put `history/` under container-level time-based immutability, shorter than the compaction delay if compaction stays.
  - Name an anchor held outside the catalog: the newest record hash in the latest backup (§10.3), or a hash published with each release. Add `verify-catalog --expect-record-sha256`.
  - Or narrow Goal 2 to "detects an edit to any record at or before a hash the reader holds".

#### 16. The retention window W ignores §11.4 and §11.6, and K is undefined - Severity: Major
* **Reviewer Lens:** design (storage), codebase details, comprehension, structural, implementation readiness, zoom-out
* **Affected Scope:** lines 23-26, 154-157
* **Discrepancy Description:** Other parts of the spec depend on old roots:
  - GC "reads the Inventory chain back through the retention window" (§11.4 line 756).
  - The §6.7 repair keys on "within retention".
  - §11.6 (lines 766-770) also requires pod poll plus fetch time < Inventory version retention.

  W tied only to backup retention can be shorter than the window GC walks, and GC may then delete data files. W also has two age rules: from supersession (Terms), and from the root's own `created_at` (line 156). K has no value. The reason at line 155 ("so a whole-catalog restore finds its roots") does not match §10.3, since a restore brings roots back from the backup and a restored version "is never made current".
* **Rationale & Recommendation:**
  - Rename W to §11.6's "Inventory version retention".
  - Add to §11.6's checker: retention ≥ max(`data/` GC window, pod poll plus fetch, backup retention), measured from the superseding root's `created_at`; K ≥ 2.
  - Have expiry and GC refuse to start when the check fails, and have GC fail closed on a missing root. Alternatively, amend §11.4 so GC reads only the newest root's leaves and its `retired` list.
  - Give defaults, and a home for them: a `RetentionConfig`, and `prune(keep_versions=, expire_after=)`.
  - Correct or drop the restore reason.

#### 17. The hash input is undefined, and the suite has no RFC 8785 implementation - Severity: Major
* **Reviewer Lens:** codebase details, implementation readiness, zoom-out
* **Affected Scope:** lines 116, 124-128, 205
* **Discrepancy Description:** Every digest in the suite today is over the bytes as written, from msgspec's indented `encode()` (`_format.py:258-265`). No pyproject depends on an RFC 8785 library. `sdmxlib.edition.canonical_json` (`_canonical.py:56`) is not RFC 8785: its key order and number formatting differ. Re-canonicalising a decoded record drops unknown fields, which 1.x readers ignore, so the chain would break on a minor addition. `extensions_sha256` hashes bytes that the design never names.
* **Rationale & Recommendation:** Pick one.
  - **(a)** Define `prev_sha256` as the SHA-256 of the previous valid record's exact stored bytes, including its own `prev_sha256`. Write records as compact msgspec JSON, and make each segment line those same bytes plus `\n`, so that verification never re-encodes.
  - **(b)** Keep RFC 8785, name the dependency and its cap, and require a reader to refuse bytes that are not canonical.

  The reviewers recommend (a). Either way, define the bytes behind `extensions_sha256`, and say that `prev_sha256` chains to `seq - 1` in the same epoch while `changes` diffs against `previous_inventory` (`_format.py:138-140`).

#### 18. Segments: readers cannot find them without LIST, and the format is undefined - Severity: Major
* **Reviewer Lens:** structural, implementation readiness, design (storage), comprehension, zoom-out
* **Affected Scope:** lines 82, 88-90, 157-159, 240
* **Discrepancy Description:** The sdmxlib reader takes only `fetch(path)` and never lists (`inventory/EGM.md:7-9`; §6.6, §10.2). Segment names of the form `<first>-<last>` cannot be probed. Undefined:
  - whether segments are created exclusively;
  - zero-padding;
  - the line bytes;
  - the overlap left by a crash mid-compaction;
  - a reader that lists during compaction and sees neither the segment nor the records.

  Delta deletes old commits, while Goal 1 promises a permanent record.
* **Rationale & Recommendation:** H2 is part of the owner's Delta-style structure, so keep segments and specify them:
  - one segment per checkpoint interval, named `history/<epoch>/segments/<first:012d>.jsonl` and created exclusively;
  - contiguous and never overlapping, each one starting at the last one's end + 1;
  - a fixed entry point, or a `history/<epoch>/segments/index.json` written conditionally;
  - per-record objects deleted only one expiry run after their segment exists;
  - readers read per-record objects first and re-list on a 404;
  - segments are never deleted.

  The zoom-out lens recommends dropping segments instead: at 3,650 records a year they save four LIST pages, and they cost a delete right on the audit log. The owner should weigh that against H2.

#### 19. Expiry has no step order, no crash recovery and no dry-run definition - Severity: Major
* **Reviewer Lens:** implementation readiness, comprehension, style, design (storage)
* **Affected Scope:** lines 156-159, 232
* **Discrepancy Description:** Lines 156 and 158 state the order twice, and the two disagree. "Closed range" is undefined. No rule covers a crash between steps, a failed chain check, or a root deleted before its record is compacted. `prune(dry_run=True)` exists (`admin.py:548`), but the design does not say what an expiry dry run reports.
* **Rationale & Recommendation:** Give a numbered procedure:
  1. Compute the retained set: checkpoints ∪ newest K ∪ roots younger than retention.
  2. Compute the range to compact.
  3. Write the segment, create-if-absent.
  4. Re-read the segment and verify its chain and its bytes against the per-record objects. On failure, stop and alert.
  5. Before deleting each root, verify its bytes against `root_sha256`, and record `root_verified` in the segment.
  6. Delete per-record objects in a later run.
  7. Delete the expired roots.
  8. Delete unreachable leaves (finding 4).
  9. Write the deletion log.

  Give the outcome of a restart after each step, and the dry run's `PruneReport` fields.

#### 20. Checkpoints: which clock decides, how they are marked, and what verifying them means - Severity: Major
* **Reviewer Lens:** design (storage), implementation readiness, comprehension, structural
* **Affected Scope:** lines 151-153, 206 (H5), 232
* **Discrepancy Description:** `created_at` comes from the writer's clock (`inventory.py:422`), while §6.4 (line 451) uses the storage server's clock. With skew, a month can get two first versions or none. Nothing marks a checkpoint. H5's "at most a month" fails for a catalog that writes nothing for a month. GC deletes the edition directories of retired editions (§11.4), so §10.3's full walk fails on old checkpoints, and checkpoints cannot be restore points.
* **Rationale & Recommendation:**
  - Add a required boolean `checkpoint` that the writer sets: true for version 1, for the first version of an epoch, for the migration start, and when the UTC month of `created_at` is later than every earlier record's month.
  - Have expiry trust the flag, and `verify-catalog` recompute it.
  - Reword H5: "replays the versions since the previous checkpoint".
  - Verify checkpoint roots for leaf presence and hash only, and label them audit-only.

#### 21. The record's fields and entries are under-specified - Severity: Major
* **Reviewer Lens:** implementation readiness, comprehension, codebase details, structural
* **Affected Scope:** lines 94-129
* **Discrepancy Description:** Undefined:
  - presence and nullability;
  - whether `embargo` is copied every time or only on change;
  - entries for retirement, `reinstate`, products added or removed, and leaf `kind` or `lifecycle` changes;
  - non-state changes: a rescheduled `release_at`, `correct`, Phase 4 fields;
  - whether `entries` lists changed entries or all of them;
  - sort order;
  - the record's format version family.

  The `…` placeholders fail any hex pattern, so "the schemas validate the examples here" (line 255) fails as written. The size claim (line 129) breaks on a full republish: 7,000 changes × about 400 bytes is about 2.8 MB, more than a root.
* **Rationale & Recommendation:**
  - Add a field table in the style of §6.2, and state that the header fields are copied from the root because roots expire.
  - Adopt §6.3's versioning rule under a separate `HISTORY_FORMAT = "1.0"`.
  - Give a complete example with full values.
  - State the worst-case size.
  - Rename `prev_sha256` to `previous_record_sha256` to match `previous_inventory`.

#### 22. The design rests on wrong or overstated citations - Severity: Major
* **Reviewer Lens:** codebase details, comprehension, structural, zoom-out
* **Affected Scope:** lines 33-46, 125, 172-176
* **Discrepancy Description:**
  - **P7 is quoted without its time limit.** It says roots, leaves and tombstones "are kept until Phase 4" (`phase-2a-catalog-editions.md:274`), and that design assigns root and leaf deletion to the server GC (lines 168-170, 875-876).
  - **`--find-newest-consistent` is not where the design says.** It is not in §6.7 or §10.3, but in statcatlib `products-editions-inventory.md:643`.
  - **Two cited commands are unbuilt.** `rebuild-inventory` and `--find-newest-consistent` are Phase 9 work.
  - **`verify-catalog` does less than implied.** It reads only the newest root (`diagnostics.py:303-353`).
  - **"Phase 7 `search` version" has no source.** No kind exists for it, and `describe` means the catalog description "and nothing else".
  - **The scan cost the Problem names is future cost.** It falls on unbuilt tools. Storage at 5 GB a year costs a few dollars a month.
* **Rationale & Recommendation:**
  - Quote P7 in full, and state that this design moves expiry from the planned server GC to the release job.
  - Fix the citations.
  - Restate the Problem as the audit gap plus the spec's existing assumption that roots expire (§11.6, §6.7), with cost figures.
  - Drop the Phase 7 example, or note that Phase 7 needs a new kind.

#### 23. Backups, layout and the Handoff omit `history/` and the specification edits - Severity: Major
* **Reviewer Lens:** codebase details, implementation readiness, structural, comprehension
* **Affected Scope:** lines 77-83, 249-263
* **Discrepancy Description:**
  - **Backups and layout.** §10.3's order (line 718), §4.1, and hub `docs/architecture.md:41-42` omit `history/`.
  - **sdmxlib Handoff.** It names spec sections without saying what changes in each.
  - **statcatlib Handoff.** It lists no acceptance checks, which hub `CLAUDE.md` requires, and names nobody to file the issue.
  - **Conformance protocol.** The `Backend` protocol (`conformance.py:75-116`) has no hook for records or expiry.
  - **Supersessions not stated.** The Handoff does not say that `prune`'s docstring ("deletes no Inventory root or leaf", `admin.py:538-539`) and P7 are superseded.
  - **Commits.** "Based on" omits sdmxlib-rest's commit.
* **Rationale & Recommendation:**
  - Add a "Specification changes" table, one row per section: the new §6 section, §4.1, §6.6, §6.7, §10.1, §10.3 (`history/` after roots, before `CURRENT`), §11.4, §11.6.
  - Add a conformance-case table with columns case, setup, expected result and repository. Include the negative cases: a tampered record, a removed tail, an orphan record, overlapping segments, a writer race, a reused `seq` after a restore, a missing or corrupt `CURRENT` after expiry, and a leaf reused during expiry. Name the new `Backend` methods and the three implementations that change.
  - Add acceptance checks under statcatlib, and the `verify-catalog` findings, warnings and exit codes.
  - State that the hub session files StatCat-Suite/statcatlib#N after sdmxlib#361 is released.
  - Add an sdmxlib-rest entry: no code change, and the sdmxlib reader release it must pin (finding 3).

#### 24. Stage the work, and add the alternatives a reader would expect - Severity: Major
* **Reviewer Lens:** zoom-out, structural, implementation readiness
* **Affected Scope:** lines 211-226, 244-246, 259-263
* **Discrepancy Description:**
  - **The work is bundled.** The record, expiry and the PROV-O mapping are three separable changes. The record alone meets Goals 1, 2, 4 and 5, adds no delete right, and does not trigger §6.6. It also has to ship first, because records must exist for the versions expiry will delete.
  - **Local writing waits on an unbuilt job.** Local record writing need not wait for the Phase 5 release job (`phase-3-structure-products.md:166`).
  - **Expected alternatives are missing:**
    - object lock or WORM on `history/`;
    - carrying `changes` in the root, which makes the root the record and the commit point at once, as a Delta commit file is;
    - the §14 governance mirror (line 845);
    - signed records (§17 Q3).
* **Rationale & Recommendation:**
  - Add a Staging table:
    - S1: the record, write order, chain, `verify-catalog`, backup order, and local writing, as soon as sdmxlib releases, including raising statcatlib's sdmxlib cap.
    - S2: checkpoints and expiry, after the §6.6 review.
    - S3: the PROV export.
  - Add one Alternatives bullet for each option above, with its reason for rejection. Cite GH-19 for "Rejected by the owner".

### Nits

#### 25. Undefined terms - Severity: Nit
* **Reviewer Lens:** comprehension, style
* **Affected Scope:** Terms (16-26) and passim
* Add Terms entries or links for: release job, `restore_epoch`, tombstone versus `retired` versus `withdrawn`, orphan record, closed range, segment, retained root, K, ETag, fold, `describe`, seal, LeafEntry (§6.3), Phase 5, statcat-serve. Use "version" for the concept (a root plus the leaves it names) and "root" for the file only.

#### 26. Writing-style violations - Severity: Nit
* **Reviewer Lens:** style
* **Affected Scope:** lines 1, 9-11, 33, 37, 42-46, 160-163, 165-176, 202-209
* Rewrite these:
  - H1, "Record deltas, not roots.", is contrast by negation.
  - The bold question labels at lines 167-176 are answered in place.
  - "never inside one" and "GC never touches either prefix" end on negations.
  - The colon setup at line 9.
  - "The specification gives this mapping as normative" states a proposal as fact.
  - The `it`s with unclear referents at lines 142-146 and 156-159.

  `style_report.md` gives a rewrite for each.

#### 27. The PREMIS paragraph is partly wrong and should be informative - Severity: Nit
* **Reviewer Lens:** design (PROV-O), codebase details, zoom-out
* **Affected Scope:** lines 194-196
* PREMIS 3 has `linkingAgentIdentifier` with `linkingAgentRole`; it has no `linkingAgent`. `eventType` expects the Library of Congress vocabulary, so `kind` maps to local values. Mark the paragraph informative, and give the full crosswalk: `eventDetailInformation` for `reason`, and `linkingObjectIdentifier` for the changed editions and leaves. The reviewer believes the PREMIS 3 OWL ontology aligns `premis:Event` with `prov:Activity`; check this.

#### 28. `prov:wasRevisionOf` is right; state the restore case - Severity: Nit
* **Reviewer Lens:** design (PROV-O)
* **Affected Scope:** lines 189-190
* Revision fits both versions (`previous_inventory`) and editions (manifest `previous`), and a rollback at N+1 is still a revision of N. sdmxlib must say what `previous_inventory` holds in the first version after a restore. If it is null, emit no revision.

#### 29. Question 2 names a term that does not exist - Severity: Nit
* **Reviewer Lens:** design (PROV-O), codebase details, style
* **Affected Scope:** line 270
* PROV-O has no `prov:Attribute` class. Reword the question, or remove it once finding 8 is adopted.

#### 30. Expiry deletes objects and leaves no provenance record - Severity: Nit
* **Reviewer Lens:** design (PROV-O)
* **Affected Scope:** lines 149-163
* The segment should record `{expired_at, actor, roots, leaves}`, mapped informatively to an `stc:Expiry` activity that invalidates nothing.

#### 31. Size figures - Severity: Nit
* **Reviewer Lens:** zoom-out, style, codebase details
* **Affected Scope:** lines 30-33
* 1.3 MB × 3 × 365 is 1.4 GB, so the range is 1.4 to 4.9 GB a year. With indent 2, a `products` entry is about 220-230 bytes. The plan has about 6,550 products covering 7,000 tables. Say "up to 7,000" and mark the figures as estimates.

#### 32. Goal 3's bound - Severity: Nit
* **Reviewer Lens:** style, zoom-out, structural
* **Affected Scope:** lines 55-56
* Checkpoints accrue at 12 a year or more. State the bound: the roots within retention, plus the newest K, plus one per month, plus one per restore epoch.

#### 33. Notation and metadata - Severity: Nit
* **Reviewer Lens:** structural
* **Affected Scope:** lines 6-14
* In the hub, write the issue as GH-19. Add an "Evidence:" bullet giving the sources of the size figures, and a "Reviewed against" commit line after this review.

#### 34. The RFC 9162 non-goal and the Purview aside - Severity: Nit
* **Reviewer Lens:** zoom-out, style
* **Affected Scope:** lines 67-71
* Replace "the format leaves room for one" with "a Merkle log (RFC 9162) can later be built over record hashes with no format change". Drop the Purview and Fabric clause, or state the one fact that matters.

## Answers to the design's questions for review

**Q1. Does the history log stay clear of §6.6's escape route, or is the Delta-table review due?**
The review is due (finding 5). The trigger in §6.6 names checkpoints, and line 22 defines a checkpoint as an Inventory version kept for good. Expiry also changes which roots exist. After this design, the system has four parts:
- a JSON commit log, one file per version;
- a full snapshot per version;
- checkpoints;
- expiry that does the work of Delta's VACUUM.

That is Delta's structure. Findings 1 and 4 are the price of having two of Delta's parts and not the third: here the record is not the commit point, and leaf expiry has no grace period. The review need not end in adopting Delta. A Delta reader lists its log, and Delta's log retention deletes history, so a separate permanent audit log would still be needed. Phase 2a Alternative F's reasons also still hold. Run the review in this design, record it as decision H9, check it with the existing Delta prototype, and amend §6.6 to record it.

**Q2. Is the specialization-entity model (H7) the right PROV-O reading, or should a state be a qualified generation?**
Specialization is right, but each state entity must stand for one interval (finding 8). A qualified generation of the edition fails, because a seal generates the edition once and states come back after rollback and `reinstate`. A PROV-DM attribute fails too, because attributes are fixed for the life of the entity. `prov:Attribute` is not a PROV-O class. Name each state entity by edition, epoch and the `seq` that entered it. Model retirement as a state, and never invalidate the edition (finding 9).

**Q3. Is replacing an orphan record under a conditional put safe against two writers racing for the same `seq`?**
No (finding 1). A live writer whose record was replaced can still win the root, which leaves a version whose record describes another root. Locally there is no ETag at all. Name each record by its epoch, its `seq` and its root's hash, create it exclusively, and never replace it. The valid record is the one whose name carries the root's hash, and records left by lost races are harmless orphans.

**Q4. Should records carry each entry's full `LeafEntry`?**
Yes, for every entry the version adds or changes. No, for unchanged entries. The full "to" `LeafEntry` brings three things the delta-only record lacks:
- `previous`, which the PROV revision row needs;
- `schema_version`, which "live at T" needs during a schema rollout (§6.4 line 446);
- `manifest_sha256`, which lets a replay rebuild each changed leaf and check it against `leaf_sha256.to`. That keeps Goal 2 verifiable after expiry.

Add the leaf's `kind` and `lifecycle` when they change, and specify the leaf's byte encoding so that a rebuild reproduces the hash. The cost is about 300-400 bytes per changed entry: tens of KB for a typical release, and about 3 MB once for a full republish. The zoom-out lens disagreed. It argued that edition ids are enough for "live at T", and that manifests can supply the rest. That holds only while the manifests exist, and GC deletes retired editions' manifests (§11.4). The consolidated recommendation is therefore yes, for changed entries.

## Traceability

| Consolidated finding | Raw findings |
| --- | --- |
| 1 | storage B1; IR A1, C2; codebase B2; comprehension B1, B2, M7; structural 7; style M5, M6 |
| 2 | codebase B1; storage M1; comprehension M5; IR C8, C9 |
| 3 | codebase B3; storage N4 |
| 4 | storage B2; IR A4; codebase M11; comprehension M8 |
| 5 | structural 1; zoom-out 3; storage Q1; codebase N1, M10 |
| 6 | PROV F6, F7, F14; IR D1, D2, D6; structural 8; zoom-out 4; codebase M8; style M8 |
| 7 | IR A5; storage M6; comprehension M6; structural 13 |
| 8 | PROV F1, F16; codebase M8; comprehension 6(c) |
| 9 | PROV F2, F3; codebase M7; comprehension M9, E3; IR B4, D4; structural 8 |
| 10 | PROV F4, F5; codebase M8; IR D1 |
| 11 | PROV F8, F9; style M8; comprehension E1 |
| 12 | PROV F10; comprehension E2, E10; IR D3; zoom-out 4 |
| 13 | PROV F13; zoom-out 4; codebase M8 |
| 14 | structural 3; storage M9; IR C10; codebase M9 |
| 15 | style M1; structural 2, 6; storage M3; comprehension M1; codebase M1; zoom-out 6; IR C10 |
| 16 | storage M2; codebase M3; comprehension M2, M3; structural 5; IR C4; zoom-out 8 |
| 17 | codebase M5, M6; IR A3, B5; zoom-out 5 |
| 18 | structural 4; IR A2, B6; storage M5; comprehension M4; zoom-out 5 |
| 19 | IR C5, C6; comprehension M3; style M7 |
| 20 | storage M8; IR C3; structural nits |
| 21 | IR B1-B3, B7; comprehension E4-E9, E11; storage N1, N2; codebase N2 |
| 22 | codebase M2, M12, N3; comprehension Part 2 items 9, 11, 23; structural nits; zoom-out 1 |
| 23 | codebase M4, M10; IR C7, E1-E3, E5, E6; structural 11, 12 |
| 24 | zoom-out 2; structural 10; IR E4; storage B1 (owner alternative) |
| 25-34 | style N1-N34; comprehension Part 2; PROV F11, F12, F15, F17; zoom-out 1, 7, 9; codebase N4; structural nits |
