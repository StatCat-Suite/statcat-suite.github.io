# PROV-O review, round 2: Inventory history log

**Target:** `docs/design/inventory-history-log.md`, revision 2 (516 lines). The review covers the PROV-O mapping (254-321), the root format and change list (92-139), segments (165-191), H7 and H8 (333-334), Goal 4 (73-75) and the alternatives at 379-382.
**Lens:** `egm-design` (design critic), as the W3C PROV-O and provenance standards reviewer.
**Mode:** REVIEW. The mapping is informative (H8), so a mapping error counts as Major. A Blocker means the normative 1.1 data lacks a fact the exporter needs, or defines one in a way that cannot be produced.

## What was read

The reviewer could not run git, so it could not confirm the cited commits. The paths are the working trees:

- sdmxlib `EGM.md`; `docs/design/sharded-bundle-catalog.md` §4.2 (133-206), §6 to §6.7 (320-514), §10 (691-718), §11.3 to §11.6 (742-774).
- sdmxlib `src/sdmxlib/inventory/_format.py` (41-46, 80-219), `_rules.py` (98-237, 380-530), `conformance.py` (100-249). The design cites `b6c79892`.
- statcatlib `src/statcatlib/store/inventory.py` (200-491) and `src/statcatlib/admin.py` (300-700), plus a grep of every `kind=` passed to `commit` under `src/statcatlib`. The design cites `95fd7ad`.
- Round 1: `../prov_o_report.md` and `../review_report.md`.

Where the code differs from the design's description:

- **No `search` kind exists.** `EventKind` is nine values (`_format.py:41-43`, spec §6.2:353), yet line 266 defines `stc:Search`.
- **`reinstate` has no event kind and no statcatlib caller.** sdmxlib has the rule (`_rules.py:425-461`), and grep finds no `reinstate(` call in statcatlib. The mapping relies on it at 124 and 306.
- **The writers that exist pass no `built_from`.** `next_root` accepts one for `correct` (`_rules.py:481, 495-496, 511`), so `previous_inventory` can be a seq other than `seq - 1`, as `_format.py:138-140` states.
- **`state_changed_at` and `created_at` come from separate clock reads.** One is taken in the change (`admin.py:325`), the other in `try_commit` (`inventory.py:422`), so they differ.
- **The `describe` and `embargo-change` versions change no leaf** (`admin.py:483, 514`), so their change lists are empty.

The rest of what the design says about §6.2 and §6.3 fields matches the spec and the code.

## Blockers

### B1. The change list and the root chain are defined against two different versions

- **Scope:** lines 100-101, 131-132, 244, 297.
- **Problem:**
  - Line 101 diffs `changes` against version `previous_inventory`, and line 100 hashes root `previous_inventory`.
  - Line 131 tells the writer to diff against its base version, the head it re-evaluates against. For a `correct`, that head is `seq - 1`, while `previous_inventory` is `built_from` (`_rules.py:511`; `_format.py:138-140`).
- **Effect on the export:** if the list follows line 101, a correction at N built from N-5 does three things wrong:
  - It reports `from` and `from_seq` as of N-5, so state entities ended in N-4 to N-1 get a second `prov:wasInvalidatedBy`. That breaks PROV-CONSTRAINTS unique-invalidation.
  - States generated in N-4 to N-1 are never ended.
  - "Live at T" (line 242) replays wrong answers.
- **Effect on the chain:** if `previous_root_sha256` follows line 100, the chain skips N-4 to N-1, so they can be removed without detection. That contradicts Goal 2.
- **Why it is a Blocker:** no writer records `correct` today, but 1.1 is the normative format being fixed now.
- **Edit:**
  - Line 100: "SHA-256 of the stored bytes of the base version, root `seq - 1` (after a restore, the root the restore built from)."
  - Line 101: "one item per product whose leaf hash differs from the base version's."
  - Keep `previous_inventory` as "built from", which is what `prov:wasRevisionOf` at line 297 should follow.
  - Add a conformance case: a correction built from an older version, checked for its change list and chain.

### B2. The writer cannot compute `from_seq` under its own rule

- **Scope:** lines 117, 131-132, 159-160, 300.
- **Problem:**
  - Line 132 says the writer "reads no other version" than its base.
  - The base leaf gives an entry's `state` and `state_changed_at` (`_format.py:212-219`), but not the seq that put it there. The base's change list names only what the base itself changed.
  - `state_changed_at` cannot be matched to a root's `created_at`, because the two come from separate clock reads (`admin.py:325` against `inventory.py:422`).
  - For an entry whose state was entered in a 1.0 version (below `since_seq`), no change list exists at all.
  - Line 117 allows `from_seq: null` only with `from: null`, so a 1.1 writer has no legal value for these entries. It would have to scan back through every earlier root, which line 132 forbids.
- **Effect on the export:** without `from_seq`, the exporter cannot name the state it ends (line 300).
- **Edit (pick one before 1.1 ships):**
  - **(a)** Leaf format 1.1 adds an optional `LeafEntry.state_seq`, plus `state_epoch` (see M1). The writer sets them whenever it writes a state, and `from_seq` is the base entry's `state_seq`. For an entry carried from a 1.0 leaf, allow `from` non-null with `from_seq: null`, meaning the state was entered at or before `since_seq`. The mapping then mints one baseline state entity per such entry, keyed to `since_seq`, with no generation asserted.
  - **(b)** Allow a bounded scan back, and say so at line 132.

  The reviewer recommends (a). It is one field per entry, and it keeps the writer reading one version.

### B3. "Generated once, by its seal" needs a fact the Inventory never carries

- **Scope:** lines 73-75 (Goal 4), 264, 299.
- **Problem:**
  - The seal is when the edition's manifest is written. Its time and producer are manifest fields (`created_at`, `producer`, spec §4.2:141), and `LeafEntry` copies neither (§6.3:368-380).
  - On a server, the seal runs on a build node. The Inventory later records a fold of `pending/` (§11.2:735-736), whose `event.kind` the spec does not name.
  - So no Inventory activity or instant exists for "its seal". An `stc:Seal` version records a sealed edition and does not generate it.
  - GC deletes retired editions' manifests after the window (§11.3, §11.4), so an exporter that later reads the manifest loses the fact.
- **Why it is a Blocker:** Goal 4 says the record carries every fact the export needs, and this row needs one it lacks. The choice has a deadline, because the manifests it would draw on are deleted.
- **Edit (pick one):**
  - **(a)** Line 299 becomes "a `prov:Entity` that `prov:specializationOf` its product and `prov:wasRevisionOf` its `previous`. The Inventory export asserts no generation for it and never invalidates it." Define `stc:Seal` as "the version that records a sealed edition". This needs no format change.
  - **(b)** Add `sealed_at` and `sealed_by` (the manifest's `created_at` and `producer`) to each change-list item whose `from` is null. The exporter then emits `prov:generatedAtTime` and a seal activity of its own, distinct from the Inventory version's activity.

## Major

### M1. State and version IRIs across a restore: `from_seq` names no epoch, and a fork double-invalidates

- **Scope:** lines 117, 186-187, 284, 297, 300, 303-305, 390.
- **Problem:**
  - After a restore with an epoch bump, the first root of epoch E+1 has `previous_inventory` pointing into epoch E (`conformance.py:114-115, 239`).
  - An entry whose state was entered at (E, 95) and ended at (E+1, 101) has `from_seq: 95`. Line 300 then reads `(edition, epoch, from_seq)` as (E+1, 95), a state that was never generated, and the real (E, 95) is never ended.
  - Line 297's `prov:wasRevisionOf` for the epoch's first root has the same gap.
  - The exporter could recover the epoch by walking epoch-start checkpoints and `previous_root_sha256`, but the design does not describe that walk.
- **The fork case:** the design keeps the lost versions' history (186-187). If that history contains an end of the same pre-fork state (say at (E, 120)), the surviving branch's end at (E+1, 101) is a second invalidation of the same entity, which breaks unique-invalidation.
- **Edit:**
  - Add `from_epoch` beside `from_seq` at line 117, or adopt B2(a)'s `state_epoch`.
  - Add a mapping rule: "The first version of an epoch ends no earlier-epoch state. The exporter mints a baseline state `(edition, E+1, s_E)` for every entry of that checkpoint root, linked by `prov:wasRevisionOf` to the entity it continues. Later items in E+1 end those baselines."
  - Or export each epoch's lineage as its own `prov:Bundle`, if PROV-CONSTRAINTS checks bundles separately (verify).
  - Add a restore case to the constraint checks named at line 392.

### M2. The IRI key (catalog_id, epoch, seq) is unique only under rules the design does not state

- **Scope:** lines 186-187, 276-288, 390.
- **Problem:**
  - **Restores that keep the epoch.** The conformance suite models one (`restore_to`, "keeping the epoch", `conformance.py:110-112`), as storage rolled back to an older copy. The next write reuses (E, seq), so `<base>inventory/E/N`, `<base>history/E/N` and the segment `history/E/<first>-<last>.jsonl` can each name two versions. Line 219's "finds the same segment, verifies it and goes on" then meets a segment from the lost branch.
  - **Exports that keep `catalog_id`.** `CatalogAdmin.export` keeps it (§6.1:333). If an export or a live-only replica writes its own chain, its IRIs collide with the source's.
  - **A configurable base.** "or a base the exporter is given" (line 277) gives the same thing two IRIs across exports. That breaks the stability H8 promises and the DCAT join in Goal 4.
- **Edit:**
  - State that every restore bumps `restore_epoch`, and that `verify-catalog` reports a `previous_root_sha256` that disagrees with a segment line for the same (epoch, seq).
  - State whether an export keeps its source's Inventory or starts a new one. If it starts a new one, it gets a new `catalog_id`.
  - Make the default base fixed. If another base is allowed, record it in `catalog.json` so every exporter uses it.
  - Optionally assert the root's `ni:` IRI on the version (see Minor 6), which is collision-free.

### M3. The unscoped `prov:actedOnBehalfOf` accumulates misleading statements

- **Scope:** line 296.
- **Problem:**
  - The unqualified `prov:actedOnBehalfOf` (Agent to Agent) is legal PROV-O, but it is tied to no activity.
  - The producer IRI `https://pypi.org/project/statcatlib/0.14.0/` is shared by every catalog and every actor. Across activities, the graph ends up saying statcatlib 0.14.0 acts for `release-job@stc`, `alice@laptop` and every other actor, with no way to tell which delegation held in which activity.
- **Edit:** use the qualified form, `<producer> prov:qualifiedDelegation [ a prov:Delegation ; prov:agent <actor> ; prov:hadActivity <activity> ]`. Keep the unqualified triple as well if consumers want it. Also state at line 296 that the producer has both the plain `prov:wasAssociatedWith` and the qualified association. The example has both; the row omits them.

### M4. Content-addressed leaf entities can be generated twice and form revision cycles

- **Scope:** lines 286, 297-298; the example's `prov:wasGeneratedBy` on the leaf.
- **Problem:**
  - A leaf's `ni:` IRI is its bytes. A correction built from an older version, or a `restore`-kind version, puts an earlier leaf back.
  - The change item then reads `{from: L_new, to: L_old}`. Row 298 asserts `L_old prov:wasRevisionOf L_new`, which closes a cycle with the earlier `L_new prov:wasRevisionOf L_old`.
  - The example's leaf generation would give `L_old` a second generation. That breaks unique-generation, and the cycle breaks derivation-generation-generation-ordering (verify whether that ordering is strict).
- **Edit (pick one):**
  - Model a leaf in a version as `<base>leaf/<product_id>/<epoch>/<seq>`, `prov:specializationOf` the `ni:` bytes entity, and put generation and revision on that.
  - Or assert neither generation nor revision on `ni:` entities, only `prov:hadMember`.

  Either way, name the case in the constraint checks.

### M5. Partial `prov:hadMember` makes the export depend on when it runs

- **Scope:** line 297.
- **Problem:**
  - "Each leaf it changed (every leaf when exported from a retained root)" gives the same version two graphs, depending on expiry. A golden-file isomorphism test (line 257) cannot pin that down.
  - A consumer reading `prov:hadMember` also takes the changed leaves for the whole collection.
  - The full membership can always be derived. Every version's full `products` map is the checkpoint at or before it plus the `leaf_sha256.to` values of the change lists forward, which needs B1's fix. So the exporter loses no data.
- **Edit:**
  - Emit `stc:changedMember` (`rdfs:subPropertyOf prov:hadMember`) for the changed leaves on every export.
  - Emit full `prov:hadMember` by replay, as an option, and make the default deterministic.
  - Say on the line that unchanged leaves after expiry are derivable.

### M6. The mapping table never links a state to its edition

- **Scope:** lines 300, 303-306.
- **Problem:** row 300 generates and ends state entities with `stc:state`. Nothing in the table says they are `prov:specializationOf` the edition. H7 rests on that link, and it appears only in the round-1 example. Without it, only the IRI path ties the state to the edition.
- **Edit:** add to row 300: "each state entity `prov:specializationOf` the edition `urn:uuid:<edition_id>`."

### M7. `from_seq` is ambiguous when an entry changes and keeps its state

- **Scope:** lines 109, 116-118.
- **Problem:**
  - `entries` lists every entry "added, changed or removed". Phase 4's routing fields (§6.3:382), a rescheduled `release_at`, or `artefacts` added would change an entry while its state stays the same.
  - "The seq of the version that put the entry into `from`" then reads as the first entry into that state. Line 300 makes every item a new state interval, so the next item must end the latest interval.
  - Read as the first entry, one entity is ended twice and the others are never ended.
- **Edit:** "`from_seq`: the `seq` of the most recent change item for this edition (the version that generated the state it leaves)." State that an item with `from == to` starts a new interval. Today every `_moved` call changes state (`_rules.py:113-124`), so no current writer is affected.

### M8. The linked Turtle example does not parse and has drifted from revision 2

- **Scope:** lines 310-312, 458; round-1 `prov_o_report.md` lines 96-154.
- **Parse errors:**
  - Turtle 1.1 `PN_LOCAL` does not allow an unescaped `/`, so `cat:history/0/42`, `cat:state/…/0/40` and `cat:agent/…` fail to parse.
  - `…` (U+2026) is outside `PN_CHARS_BASE` in a prefixed name.
  - Check both with rdflib. The handoff lists this example as sdmxlib acceptance (line 458).
- **Disagreements with revision 2:**
  - It asserts `prov:used cat:inventory/0/41`, which the table never mentions.
  - It sets `stc:kind "release"` on a known kind, while lines 267-268 use `stc:kind` only for unknown kinds.
  - It gives the leaf a `prov:wasGeneratedBy` (M4).
  - It carries `stc:rootSha256` as a literal, while line 286 gives root bytes an `ni:` IRI.
  - Its header still assumes round-1 fixes, such as "`retired` holding only this version's tombstones", which revision 2 replaced with `to: retired` items.
  - It shows no `stc:Retire` or `reinstate` case.
- **The anchor still resolves.** The heading "Recommended mapping: the example record as Turtle" gives `recommended-mapping-the-example-record-as-turtle`. A design that points at a round-1 evidence file breaks when that file changes, though.
- **Edit:** move a corrected example into the design or the spec PR. Use full IRIs or escaped local names and real hex values. Add a second example for one `retire` and one `reinstate`, and decide `prov:used` either way.

## Minor

1. **Line 300 reads backwards.** "The activity `prov:wasInvalidatedBy`-ends the state entity" puts the activity in subject position, but `prov:wasInvalidatedBy` runs from entity to activity. Rewrite: "The state entity `(edition, from_epoch, from_seq)` `prov:wasInvalidatedBy` the activity, with `prov:invalidatedAtTime`. The state entity `(edition, epoch, seq)` `prov:wasGeneratedBy` it, with `prov:generatedAtTime`, `stc:state` and `prov:specializationOf` the edition."
2. **The event-kind classes (lines 264-268) do not match the kinds.**
   - `stc:Search` has no kind (`_format.py:41-43`); drop it.
   - Give the kind-to-class rule (`embargo-change` becomes `stc:EmbargoChange`).
   - Say which kind a `reinstate` version and a server fold of `pending/` record. Neither is defined, yet lines 124 and 306 depend on `reinstate`.
3. **`retired` as a state (lines 118, 270, 305) contradicts §6.4:424**, "Retirement is a tombstone, never a state." The spec PR should amend that sentence, or name the individual `stc:tombstoned`.
4. **The monotone rule's scope.** Line 128 says "within a `restore_epoch`", while 129-130 compare against the base. The first root of a new epoch is unconstrained against its base in the old epoch, so `prov:invalidatedAtTime` can precede `prov:generatedAtTime` across a restore. Word the rule against the base version.
5. **Times.** State that state entities take `created_at`, never `LeafEntry.state_changed_at`; the two differ (see What was read). The activity has no start or end time, which PROV allows. Say so at line 294.
6. **IRI minting needs exact rules (lines 281-288):**
   - Lowercase `urn:uuid` (RFC 9562).
   - Convert hex to unpadded base64url for `ni:`.
   - Percent-encode every UTF-8 octet outside RFC 3986 unreserved, in uppercase hex. RDF compares IRIs as strings, so `@` and `%40` are different IRIs.
   - Handle a producer version of `"unknown"` (`inventory.py:210`), dev or local versions, and non-PyPI producers, none of which give a real PyPI page.
   - The local actor is `<os user>@<hostname>` (`inventory.py:214-220`), which puts personal data into IRIs. Note it under Embargo and access.
7. **`embargo-change` and `describe` export as empty changes.** Their lists are empty (`admin.py:483, 514`). The export then shows an activity and a version with no visible effect, since `embargo` and the extension digests are unmapped (line 307). Add `stc:embargo` on the version entity, and map the `describe` extension digest to an `ni:` member. Also define which bytes the "`extensions` digests" at line 182 hash.
8. **The edition is "never invalidated" (lines 299, 306-307), but its bytes do end.** GC deletes them after retirement and `expunge` deletes them at once (§11.3:750-752), and neither writes an Inventory version. Phrase the claim as an export rule: "The export never invalidates an edition, because no Inventory activity records the end of its bytes."
9. **Expiry has no mapping.** The segment header carries `expired_at` and `actor` (line 177), and the review response counts that as done, but the mapping gives no `stc:Expiry` activity. Add one informative row.
10. **H7 (line 333)** says "PROV allows one generation and one invalidation per entity". Name the source: "PROV-CONSTRAINTS' unique-generation and unique-invalidation constraints (a valid document has at most one of each per entity)". Line 304 reads the same way.
11. **Line 380** says "PROV-DM attributes are fixed". PROV-DM §5.1.1 says an entity has "some fixed aspects", and PROV-O renders attributes as ordinary RDF properties. Reword: "An entity's attributes describe its fixed aspects (PROV-DM §5.1.1), so a state that changes cannot be one."
12. **The DCAT join (lines 74-75, 285).** No repository yet mints `<base>product/<product_id>` as a `dcat:Dataset` IRI. Add that rule to the Cross-repo contract for whichever DCAT exporter exists, and reserve `/id/` beside `/ns/` at line 412. The design should also state whether a multi-dataflow product is one `dcat:Dataset`, which is a DCAT modelling choice.
13. **PREMIS crosswalk (lines 314-321).**
    - `eventIdentifier` is mandatory in PREMIS 3 and missing; map the activity IRI to it.
    - Add `linkingObjectRole`.
    - The containers are `linkingAgentIdentifier` (with `linkingAgentIdentifierType` and `linkingAgentIdentifierValue`) and `eventDetailInformation/eventDetail`. Check both.
14. **`stc:reason` (lines 272-273).** In OWL 2 DL, `rdfs:comment` is an annotation property, so `stc:reason` must be declared `owl:AnnotationProperty` for the sub-property axiom to stay in DL. Give the vocabulary an `owl:versionIRI`.
15. **The embargo filter (line 251).** In a live-only export, an `embargoed` to `live` item keeps the generation of the live state and drops the invalidation of the embargoed state. Say so, so that the embargoed state's IRI (which carries `from_seq`) does not leak.

## Verify before citing

- **PROV-CONSTRAINTS names and numbers.** The reviewer believes the uniqueness constraints are named unique-generation and unique-invalidation (about Constraints 24-25), not "generation-uniqueness". Also check generation-precedes-invalidation, specialization-generation-ordering, specialization-invalidation-ordering, whether derivation-generation-generation-ordering is strict (M4), whether constraints apply per bundle (M1), and whether time values take part in validity at all.
- **`prov:hadRole`.** Check whether the domain is `prov:Influence`, or a union including `prov:Association`. Either way, `prov:Association` carries it.
- **PROV-O qualification.** Check whether PROV-O §3.3 recommends asserting the unqualified triple beside the qualified one. Check `prov:qualifiedDelegation` and `prov:hadActivity` on `prov:Delegation`.
- **DCAT 3.** Check whether `dcat:previousVersion` is a sub-property of `prov:wasRevisionOf`, and `dcat:hasVersion` of `prov:hadRevision`. Revision 2 no longer cites them; check whether the spec does.
- **PREMIS 3.0 Data Dictionary.** Check `eventIdentifier` (mandatory), `eventType`, `eventDateTime`, `eventDetailInformation/eventDetail`, `linkingAgentIdentifier/linkingAgentRole` and `linkingObjectIdentifier/linkingObjectRole`. Confirm that the LoC eventType vocabulary has no release or rollback term, and whether PREMIS-OWL aligns `premis:Event` with `prov:Activity`.
- **`rdfs:subPropertyOf rdfs:comment`.** Check its OWL 2 DL status (annotation property).
- **RFC 6920 §3.** Confirm `ni:///sha-256;<val>` with an empty authority, the hash name "sha-256" from the Named Information Hash Algorithm Registry, and base64url without padding.
- **PROV-DM §5.1.1.** Check the exact "fixed aspects" wording behind line 380.
- **Turtle 1.1 grammar.** Confirm that `PN_LOCAL` requires `\/` for a slash and excludes U+2026 (M8). Test with rdflib.
- **RFC 9562.** Confirm that `urn:uuid` is written in lowercase.
