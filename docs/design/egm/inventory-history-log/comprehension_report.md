# Comprehension review: Inventory history log

**Target:** `docs/design/inventory-history-log.md` (lines 1-276)
**Lens:** `egm-comprehension`, against `re-implementation-standard.md`
**Read:** the target first on its own, then sdmxlib spec §6.1-6.7, §10.1-10.3, §11.1-11.6, §13 and `src/sdmxlib/inventory/EGM.md` (working tree, branch `docs/q1-product-granularity`); statcatlib `src/statcatlib/store/inventory.py:381-490`, `docs/design/phase-2a-catalog-editions.md`, `docs/index.md`, `src/statcatlib/store/schema.py` (working tree, branch `feat/gh-124-corpus-bench`).
**Verdict:** the design does not meet the re-implementation bar. The write protocol is the weakest part; the expiry algorithm has undefined inputs; the PROV-O mapping cannot be produced from a record alone.

## Part 1. Safety and correctness

**B1. The orphan-record replacement races (Blocker; lines 141-147, 203-204, 272-273).** Writers A and B build version N. A creates `history/N`. B's create fails; B reads it, sees a different `root_sha256`, finds no `inventory/N` (A is between steps 3 and 4), and replaces the record under its ETag. A then creates `inventory/N`. B's root create fails and B retries at N+1 (spec §6.6 line 486; `inventory.py:471-487`). Record N now describes B's never-written root while root N is A's, and nothing repairs it. The text also never says what a writer does with its own record after losing the root race.
**Fix:** make the record's create-if-absent the compare-and-swap for seq N: the loser of the record create retries at N+1. Replace an orphan only after a stated lease measured from `created_at` against the storage server's clock (§6.4 line 451), and re-check that `inventory/N` is absent before writing the root. State the local equivalent of an ETag replace; the local writer uses `create_exclusive` (`inventory.py:432`).

**B2. "Reuses it (the same version, retried)" cannot happen as written (Major; lines 143-145).** Every attempt recomputes root bytes with `now=datetime.now(UTC)` and the actor (`inventory.py:417-428`), so a retried root never has the same hash unless the writer kept the first attempt's bytes.
**Fix:** reuse applies only within one attempt that holds the exact root bytes it hashed; otherwise B1's rule applies.

**M1. Goal 5 contradicts expiry (Major; lines 59-60, 160-163, 207).** The release job gains delete on `inventory/` and write and delete on `history/`, which §10.1 (lines 697-704) has no column for.
**Fix:** rewrite Goal 5; add `history/` to the §10.1 change in the Handoff.

**M2. W ignores GC's window (Major; lines 154-155).** §11.4 line 756: GC "reads the Inventory chain back through the retention window" and keeps `data/` files listed in editions "recorded or tombstoned within the window". §11.6 line 768 allows the GC and tombstone windows to exceed backup retention, so with W = backup retention GC can lose sight of editions recorded only in expired roots. §11.6 line 769 (pod poll plus fetch < Inventory version retention) is not mentioned.
**Fix:** W >= max(backup retention, `data/` GC window, pod poll plus fetch), checked with §11.6's other inequalities.

**M3. Expiry has no definition of age, K or closed range, and no crash order (Major; lines 22-26, 154-159).** Terms measures age from supersession; line 156 reads as the root's own `created_at`. K has no value; the §6.6 reader falls back to "the version before" (line 491), so K >= 2. The order of steps is stated twice and disagrees. No rule for a crash between steps, overlapping segments, or a failed chain check.
**Fix:** a numbered algorithm: inputs (W, K >= 2, `now` from the storage Date header), retained set, compaction range, create-if-absent segment, verify and failure action, delete order, idempotent restart.

**M4. A reader cannot find segments without LIST (Major; lines 82, 88-90).** §6.6 line 492 and §10.2 line 714 forbid listing.
**Fix:** a conditionally written pointer object (`history/_segments.json`) or fixed-size segments with predictable names; state zero-padding and line format.

**M5. Backups and restores omit `history/` (Major; lines 151-153, 234, 253-254).** The §10.3 order (line 718) has no `history/`. After a restore, `history/` may hold records for roots not restored. §10.3 says a restored version is never made current; it is unclear which seq comes next. Line 234's "the first record after it names the epoch" adds nothing, since every record carries `restore_epoch`.
**Fix:** add `history/` to §10.3, records before roots; define how a restore treats records above the restored newest root; replace line 234 with a testable rule.

**M6. Migration of existing catalogs is undefined (Major; lines 126-128, 204).** Catalogs from statcatlib 0.13.0 have roots and no records; "null for the first record" assumes the log starts at 1; older writers keep producing gaps.
**Fix:** state the first seq recorded, the marker of where the log starts, a minimum writer version, and how `verify-catalog` reports a root with no record.

**M7. Validity of a record whose root expired cannot be checked (Major; lines 141-142, 146-147).** The definition is circular, and after expiry an expired root is indistinguishable from one that never existed.
**Fix:** expiry verifies root bytes against `root_sha256` before deleting, and records the result in the segment (for example `root_verified`).

**M8. Leaf deletion races a concurrent local writer (Major; lines 156-157, 232, 236).** §6.6 line 484 lets a writer skip a leaf that exists; local `prune` and seals can overlap (the server release job is serialized, line 738).
**Fix:** mutual exclusion between expiry and writers, or writers always write their leaves.

**M9. Retirement under `kind: release` contradicts the spec (Major; lines 102, 115).** §6.4 line 444 assigns retirement to the prune job, and §6.2 line 353 has a `retire` kind.
**Fix:** move the retired entry to a `retire` example, or cite where a release version may retire.

## Part 2. Terms used before definition or never defined

Major: release job; `embargo` (operation at line 32, field at line 104; copied every time or only on change?); tombstone vs a record's `retired` entry; `restore_epoch` (spec §6.1 lines 328-336); P7 (statcatlib `phase-2a-catalog-editions.md:274`, which says roots, leaves and tombstones are kept "until Phase 4", and lines 168-170 plan a server GC that deletes roots and leaves, so line 33's "nothing may delete it" and lines 216-217 overstate P7); Phase 5 (plan file and scope); "Phase 7 `search` version" (found nowhere in the spec; cite or drop); W; K; specialization entity; closed range; segment; checkpoint (which `created_at` decides the month; nothing marks a checkpoint); ETag (absent locally); `stc:` prefix and its terms (no IRI; seven of nine kinds elided; `embargo-change` needs a class-name rule; rule for unknown kinds); `--find-newest-consistent` (not in §6.7 or §10.3; only in sdmxlib `docs/design/sharded-bundle-catalog-plan.md:426`).

Nit: fold (§11.2 line 736), rollback, describe, seal, LeafEntry (§6.3 lines 368-380), escape route (quote §6.6 line 499), principal, RFC 8785 (say which hashes are over bytes as written; `CURRENT` uses bytes as written, lines 336, 491), statcat-serve, Fabric, OneLake, PREMIS 3, Delta Lake, Iceberg `metadata-log`, `CatalogAdmin.prune` (today it retires entries; expiry is a new job for it).

## Part 3. Sentences read twice

Lines 141-142 (circular validity); 143-146 (comparison, two outcomes and an unproven justification in one sentence); 156-157 (write retained = checkpoints ∪ newest K ∪ {age < W}); 161-163 (present tense for a proposed §10.1 change); 180 ("The specification gives this mapping as normative": not yet); 191 (three relations in one cell); 218-223 (concedes the §6.6 trigger it argues against); 234.

## Part 4. Example record against prose

- E1 (line 110): `release_at` on an entry going to `live`; §6.3 line 378 makes it null for non-embargoed entries. Give a field table for `changes[].entries[]`.
- E2: entries carry no `previous`, `manifest_sha256` or `state_changed_at`, which the PROV mapping needs (line 190) once leaves expire.
- E3 (line 115): the root's `retired` is every tombstone in the window (§6.2 line 352); the example suggests only new ones. A retirement changes the leaf (§6.3 line 358), yet `changes` shows nothing for `0197…02`.
- E4: no encoding for entries removed from a leaf, products added or removed, or `leaf_sha256.from` for a new product.
- E5: `extensions_sha256` hashes undefined bytes; complete map in every record or only on change?
- E6: say the record's `created_at` equals the root's.
- E7: `producer.version` 0.14.0 vs the spec's 0.12.0 and base 0.13.0; say 0.14.0 is the first writer of records.
- E8: is `format_version` "1.0" the history format, versioned apart from the Inventory format? Adopt §6.3 line 384's rule.
- E9: chain over seq-1 or over `previous_inventory`? Equal today (§6.4 line 448); say so.
- E10: no `catalog_id` (§6.1 line 333), so PROV IRIs cannot be globally unique.
- E11: line 129's size: a batched release of hundreds of products (§11.2 item 4) is far larger; give a per-entry size.

## Part 5. Claims not verifiable from the cited sources

190 bytes per entry and 3-10 versions a day (no measurement); P7 overstated; `--find-newest-consistent` citation; DCAT-AP / StatDCAT-AP "already use" PROV-O (statcatlib `docs/index.md:5, 106` confirms only statcatlib's lineage); Purview and Fabric ingest; Phase 7 `search` extension; "the only write path" holds on the server only (locally the writer is `WorkingCopy` / `CatalogAdmin`, `inventory.py:5`); "the specification states where this log differs" (it does not yet); "validates against PROV-JSON" (name the W3C member submission's JSON Schema).

## Part 6. Restatement attempts

**(a) Write protocol.** Leaves create-if-absent; build root (seq = head+1, `created_at` = now) and hash bytes as written; build record with `prev_sha256` over RFC 8785 of record seq-1; create `history/<seq>.json`; if present and equal, continue, else [gap: check `inventory/<seq>` first? no local ETag, no lease] replace; create root; on loss re-read head and retry [gap: the loser's record]; advance `CURRENT`. Missing: lease, local replace, loser cleanup, the clock, race limit, orphan classification in `verify-catalog`.

**(b) Expiry.** Inputs W, K, now [none defined]. List roots; checkpoints = 1 ∪ first of each epoch ∪ first of each UTC month [which clock]; retained = checkpoints ∪ newest K ∪ younger than W [age rule disagrees]; compact a "closed range" [undefined] into a segment [naming, create-if-absent], verify chain [failure action]; delete per-record objects; delete roots; delete unreferenced leaves. Gaps: step order conflict, crash rule, dry-run output, local exclusion, `root_sha256` check before delete, GC and pod-poll windows, backups.

**(c) PROV-O for the example record** (placeholder IRIs; the design gives no IRI scheme):

```turtle
:v42-act  a prov:Activity, stc:Release ;
          prov:startedAtTime "2026-10-09T12:30:00.412Z"^^xsd:dateTime ;
          prov:endedAtTime   "2026-10-09T12:30:00.412Z"^^xsd:dateTime ;
          prov:wasAssociatedWith :agent-release-job, :statcatlib-0.14.0 ;
          rdfs:comment "08:30 release" ;
          prov:qualifiedAssociation [ a prov:Association ; prov:agent :statcatlib-0.14.0 ; prov:hadRole stc:producer ] .
:inv-42   a prov:Entity, prov:Collection ; prov:wasGeneratedBy :v42-act ; prov:wasRevisionOf :inv-41 ;
          prov:hadMember :leaf-to-hash .          # other members need the root, which may have expired
:ed-0199  a prov:Entity ; prov:wasRevisionOf :ed-unknown .   # previous not in the record
:ed-0199-embargoed prov:specializationOf :ed-0199 ; prov:wasInvalidatedBy :v42-act .
:ed-0199-live      prov:specializationOf :ed-0199 ; prov:wasGeneratedBy :v42-act .
:ed-0198-live      prov:specializationOf :ed-0198 ; prov:wasInvalidatedBy :v42-act .
:ed-0198-superseded prov:specializationOf :ed-0198 ; prov:wasGeneratedBy :v42-act .
:ed-0197  prov:wasInvalidatedBy :v42-act .      # tombstone
```

Shortfalls: no IRI scheme, and a state entity's IRI must change each time an edition re-enters a state (live, superseded, live again after rollback), so it needs the seq; `prov:hadRole` needs a qualified association; `reason` has two targets; invalidating the edition at retirement is final in PROV, but `reinstate` (§6.4 line 443) brings a tombstone back; unmapped fields (seq, `restore_epoch`, `root_sha256`, `prev_sha256`, `embargo`, `extensions_sha256`, `leaf_sha256`, `release_at`, `product_id`); no `catalog_id`; the `from: null` case is unstated.
