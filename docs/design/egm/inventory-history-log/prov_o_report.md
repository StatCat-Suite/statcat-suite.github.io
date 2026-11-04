# PROV-O review: Inventory history log

**Target:** `docs/design/inventory-history-log.md`, PROV-O mapping (lines 178-196), H7 (line 208), Goal 4 (lines 57-59), the record (lines 92-129), Question 2 (lines 269-271)
**Lens:** `egm-design`, instance B (provenance ontology), against `feature-spec-standard.md`
**Read:** sdmxlib spec §6.1-6.4 and §10.3 (working tree, branch `docs/q1-product-granularity`); statcatlib `docs/index.md:100-106`, `docs/tutorial.md:558-569`, `src/statcatlib/store/schema.py:334-347` (working tree, branch `feat/gh-124-corpus-bench`).
**Caveat:** the reviewer had no web access. W3C, PREMIS and DCAT citations come from memory; constraint numbers in PROV-CONSTRAINTS are marked where unsure and should be checked against https://www.w3.org/TR/prov-constraints/ before the specification cites them.

## Verdict

H7 is the right PROV reading, with one change: a state entity stands for one interval in one state, and needs an IRI that includes the `seq` that entered it. The mapping is not fit to be normative yet. `stc:` is defined nowhere, there are no IRI rules, one row offers two outputs, `prov:hadRole` is placed where PROV-O does not allow it, and there is no worked example in triples. Three rules break PROV-CONSTRAINTS on cases the specification allows: states that recur (rollback, `reinstate`), a tombstone that invalidates the edition, and a `retired` list of unclear scope.

## Findings

### F14. "Normative" but untestable (Blocker for normative status; lines 180-181, 255-257)
PROV-JSON is a W3C Member Submission (2013), not a Recommendation. Its JSON Schema checks syntax only; it would pass wrong IRIs, a misplaced `hadRole`, or duplicate generations. With F6, F7 and F9 open, two correct implementations produce different graphs.
**Fix:** the specification gives the worked example's export as a golden Turtle file; the exporter's RDF output is graph-isomorphic to it (`rdflib.compare.isomorphic`); its PROV-JSON output loads with the `prov` package and converts to the same graph; conformance runs SHACL or SPARQL checks for generation-uniqueness, invalidation-uniqueness, generation-precedes-invalidation and specialization ordering over the rollback, reinstate and restore cases. Until the golden file exists, call the mapping informative.

### F1. One generation per state entity; states recur (Major; lines 191, 208, 269-271)
PROV-CONSTRAINTS allows an entity one generation and one invalidation (generation-uniqueness and invalidation-uniqueness; numbering unverified). An edition re-enters `live` by rollback (spec §6.4 lines 440-442) and `superseded` by `reinstate` (line 443). A single entity "edition X as live" would be generated twice.
The alternatives are worse. A qualified generation of the edition fails the same way: the edition is generated once, by its seal. PROV-DM attributes are an entity's fixed aspects (PROV-DM §5.1.1), so a changing state cannot be one. The state on the leaf entry within a version is sound, but leaves expire and records are deltas, so a log-only export cannot produce it. Specialization fits a delta log: each `changes[].entries[]` item becomes one invalidation and one generation.
**Fix:** replace row 191 and H7's reason with: "An edition's state is a `prov:Entity` for one interval in one state, identified by the edition, the `restore_epoch` and the `seq` of the version that entered it. It `prov:specializationOf` the edition and carries `stc:state`. The activity of the version that entered it generates it; the activity of the version that left it invalidates it. A current state has no invalidation." Add `from_seq` beside `from` in each entry so one record names the state it leaves without a scan back. Add "`created_at` never decreases with `seq` within a `restore_epoch`; a writer refuses a lower one", so generation-precedes-invalidation holds on drifting clocks.

### F2. A tombstone must not invalidate the edition (Major; lines 192, 115)
`reinstate` brings a tombstoned edition back to `superseded` (spec §6.4:443); its new state would specialize an already-invalidated entity and break specialization-invalidation ordering. It is also false on the facts: the manifest and bytes stay until the backup window ends (§11.3).
**Fix:** retirement invalidates the last state entity and generates "X retired since N" (`stc:state stc:retired`); `reinstate` invalidates that and generates a new superseded state. The edition entity is never invalidated. If an invalidation of the edition is wanted at all, attach it to `expunge`, the only operation that destroys content at once, and only if `expunge` writes a record. `withdrawn` is an ordinary state.

### F3. `retired` scope is undefined (Major; lines 115, 192)
In the root, `retired` lists every tombstone in the window (§6.2:352). Copied into each record, every record would re-assert the invalidation with a new activity. The example also retires inside a `release` record, while `retire` is its own kind (§6.2:353) done by the prune job (§6.4:444).
**Fix:** define it as "tombstones this version adds"; state whether a release may carry them, or move the example entry to a `retire` record.

### F4. `prov:hadRole` cannot sit on an unqualified `wasAssociatedWith` (Major; lines 186, 188)
`prov:hadRole` has domain `prov:Influence` and attaches to a qualified node.
**Fix:** `prov:qualifiedAssociation [ a prov:Association ; prov:agent <agent> ; prov:hadRole stc:… ]`, keeping the unqualified `prov:wasAssociatedWith` for consumers that read only that.

### F5. Actor and producer: agent type and delegation (Major; lines 102, 186, 188)
`actor` is the writer's identity, a token object id (§6.2:353); `rollback`, `cancel` and `reinstate` go through `CatalogAdmin` (§6.4:437-443), which a person may drive, and a local actor is `<os user>@<hostname>`. The record cannot tell a person from a service. `producer` is the program acting for that identity: PROV's delegation (PROV-DM §5.3.4).
**Fix:** actor is a `prov:Agent` (no subclass unless a 1.x field gives the type), with role `stc:actor`. Producer is a `prov:SoftwareAgent` (IRI `https://pypi.org/project/statcatlib/0.14.0/`), role `stc:writer`, `prov:actedOnBehalfOf` the actor. Drop `stc:producer` as a role name.

### F6. The `stc:` namespace is defined nowhere (Major; lines 185, 188, 240-243)
A search of the hub, sdmxlib and statcatlib finds `stc:` only in this design; statcatlib "adopts the concepts without the RDF runtime".
**Fix:** in the Cross-repo contract: IRI `https://statcat-suite.github.io/ns/inventory#`, prefix `stc`; sdmxlib owns the terms, the hub publishes the file; `owl:versionIRI …/ns/inventory/1.0`, additions only within 1.x. One class per kind (`stc:Seal`, `stc:Release`, `stc:Rollback`, `stc:Withdraw`, `stc:Retire`, `stc:EmbargoChange`, `stc:Restore`, `stc:Correct`, `stc:Describe`, plus `stc:Reinstate` if it gets a kind), each `rdfs:subClassOf prov:Activity`; state individuals; roles `stc:actor`, `stc:writer`; properties `stc:kind`, `stc:reason`, `stc:state`, `stc:releaseAt`, `stc:rootSha256`, `stc:product`. An unknown kind exports as a plain `prov:Activity` with `stc:kind` set to the string (matching §6.2:353 and §6.3:384).

### F7. No IRI rules; `seq` is not unique across a restore (Major; lines 183-192, 98-99)
After a restore, readers accept a lower `seq` when `restore_epoch` changes (§6.6:493, §6.1:334), so one `seq` can name two versions. The same collision affects the `history/<seq>.json` key (line 81).

| Thing | IRI |
| --- | --- |
| Edition | `urn:uuid:<edition_id>` |
| Catalog base | `https://statcat-suite.github.io/id/catalog/<catalog_id>/`, or a base the exporter is given |
| Inventory version | `<base>inventory/<restore_epoch>/<seq>` |
| Activity | `<base>history/<restore_epoch>/<seq>` |
| State | `<base>state/<edition_id>/<restore_epoch>/<seq>` |
| Product | `<base>product/<product_id>` |
| Leaf, root, extension bytes | `ni:///sha-256;<base64url digest>` (RFC 6920) |
| Actor | `<base>agent/<percent-encoded actor>` |

The record needs `catalog_id` (§6.1:333) or the exporter must take it from `catalog.json`.

### F8. `created_at` is when the content was fixed, not an activity span (Major for ordering, Nit otherwise; lines 100, 110, 131-147, 185)
`created_at` is fixed at write step 2, before the record, root and `CURRENT`. Both `startedAtTime` and `endedAtTime` from it claim a zero-length activity: PROV allows it, but it is not true. `release_at` on an entry going `live` conflicts with §6.3:378 (null for non-embargoed entries) and is the planned instant, not the actual go-live.
**Fix:** emit `prov:generatedAtTime` from `created_at` on the version entity and each state it generates, and `prov:invalidatedAtTime` on states it ends, defined as "the instant the writer fixed the version's content"; emit no start or end time. `release_at` becomes `stc:releaseAt` on the embargoed state; in the record, move it to the entry that enters `embargoed`, or rename it `from_release_at`. Add the monotone rule from F1.

### F9. `reason`: two outputs, and a reason is not a Plan (Major; line 187)
`prov:Plan` is a set of intended actions (PROV-DM §5.3.3, used via `prov:hadPlan`). "08:30 release" is a reason. The release schedule could be a Plan, but the record does not carry one.
**Fix:** one output, `stc:reason` declared `rdfs:subPropertyOf rdfs:comment` (or `dcterms:description`; pick one). Drop the Plan option.

### F10. Collection membership and edition revisions need data the record lacks (Major; lines 121-123, 189, 190)
Leaves are the right members: a root names them (§6.2:351), and PROV does not make membership exclusive, so sharing a content-addressed leaf across versions is fine. `prov:hadMember` is open-world, so asserting only changed leaves is sound, but row 189 reads as if every member is emitted. PROV-O has no collection-change vocabulary; PROV-Dictionary's `derivedByInsertionFrom` / `derivedByRemovalFrom` is a Working Group Note. A per-product leaf revision expresses the change. Row 190 needs the manifest's `previous`, which only the leaf carries, and leaves expire.
**Fix:** row 189: "a `prov:Collection` that `prov:hadMember` each leaf this version changed (every leaf when exported from a retained root)". Add a row: "a changed leaf `prov:wasRevisionOf` the leaf it replaced". Add `previous` to each entry whose `from` is null. PROV-Dictionary may be an informative extension.

### F11. `prov:wasRevisionOf` holds for versions and editions (Nit; lines 189, 190)
`previous_inventory` means "built from", which is revision (PROV-DM §5.2.2). A rollback at N+1 is still a revision of N; that one product matches an earlier state is carried by the state entities. Optionally add `prov:used` from the rollback activity to the target's superseded state. After a restore, §10.3:718 says a restored version is never made current; sdmxlib must say what `previous_inventory` holds then, and if null no revision is emitted. Add "each edition `prov:specializationOf` its product".

### F12. PREMIS names are partly wrong; status unclear (Nit; lines 194-196)
PREMIS 3 has no `linkingAgent`; the unit is `linkingAgentIdentifier` (with `linkingAgentRole`). `eventType` expects the Library of Congress controlled vocabulary, which has no "release" or "rollback", so `kind` maps to local values. The PREMIS 3 OWL ontology aligns `premis:Event` with `prov:Activity` and `premis:Agent` with `prov:Agent` (reviewer not certain; check).
**Fix:** mark the paragraph informative and either drop it or give the full crosswalk: `kind` to `eventType` (local values); `created_at` to `eventDateTime`; `reason` to `eventDetailInformation/eventDetail`; `actor` and `producer` to `linkingAgentIdentifier` with `linkingAgentRole` ("authorizer", "executing program"); changed editions and leaves to `linkingObjectIdentifier` with `linkingObjectRole`; the activity IRI to `eventIdentifier`.

### F13. Goal 4 overstates the alignment (Major; lines 57-59, 189-190)
statcatlib `lineage` links dataset ids whose IRIs are SDMX URNs (`schema.py:335-347`, `docs/index.md:102, 106`) and already maps `revision_of` and `replaces` to `prov:wasRevisionOf` (`docs/tutorial.md:565, 569`). The history graph's entities are editions, versions and leaves; no IRI is shared, so the graphs never join. DCAT-AP 3 uses PROV lightly on `dcat:Dataset` (`prov:wasGeneratedBy`, `prov:qualifiedAttribution`, possibly `prov:wasUsedBy`); `dct:provenance` / `dct:ProvenanceStatement` is Dublin Core. StatDCAT-AP adds statistical properties and no PROV. DCAT 3 versioning has `dcat:hasVersion`, `dcat:isVersionOf`, `dcat:previousVersion`, `dcat:hasCurrentVersion`, `dcat:version`, `adms:versionNotes`; DCAT 3 declares `dcat:previousVersion` a sub-property of `prov:wasRevisionOf` (reviewer not certain; check), which would make this mapping consistent with a DCAT export. "Live now" is `dcat:hasCurrentVersion`, a snapshot fact for the DCAT export, not the provenance export.
**Fix:** rewrite Goal 4: "The record maps to W3C PROV-O. The product IRI joins the history graph to DCAT: a product is the `dcat:Dataset` each edition `prov:specializationOf`, and a DCAT export lists editions with `dcat:hasVersion` and `dcat:previousVersion` following manifest `previous`. statcatlib's `lineage` graph joins only if a later design links products to dataset URNs."

### F15. Question 2 names a term that does not exist (Nit; lines 269-271)
PROV-O has no `prov:Attribute` class. PROV-DM attributes (`prov:type`, `prov:label`, `prov:role`, `prov:location`, `prov:value`) render in PROV-O as `rdf:type`, `rdfs:label`, `prov:hadRole`, `prov:atLocation`, `prov:value`.
**Fix:** reword Question 2, and record the F1 answer under Alternatives.

### F16. No alternatives or risks for the mapping (Major; lines 208, 211-236)
**Fix:** add Alternatives "a state as an attribute or qualified generation of the edition" (rejected: one generation per entity, fixed attributes) and "the state as the leaf entry within a version" (rejected: leaves expire, records are deltas). Add a risk row "the export breaks PROV-CONSTRAINTS on a rollback or reinstate", mitigated by the F14 checks.

### F17. Expiry deletes objects with no provenance record (Nit; lines 149-163)
**Fix:** the segment records `{expired_at, actor, roots, leaves}`; informative mapping to a `stc:Expiry` activity that invalidates nothing.

## Recommended mapping: the example record as Turtle

Assumes the fixes above: `from_seq` (40, invented), `previous` on new entries, `release_at` on the embargoed state, `retired` holding only this version's tombstones. The retirement belongs in a separate `retire` record.

```turtle
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix stc:  <https://statcat-suite.github.io/ns/inventory#> .
@prefix cat:  <https://statcat-suite.github.io/id/catalog/01a0…/> .

cat:history/0/42 a prov:Activity, stc:Release ;
    stc:kind "release" ;
    stc:reason "08:30 release" ;
    prov:used cat:inventory/0/41 ;
    prov:wasAssociatedWith cat:agent/release-job%40stc ,
                           <https://pypi.org/project/statcatlib/0.14.0/> ;
    prov:qualifiedAssociation
        [ a prov:Association ; prov:agent cat:agent/release-job%40stc ; prov:hadRole stc:actor ] ,
        [ a prov:Association ; prov:agent <https://pypi.org/project/statcatlib/0.14.0/> ; prov:hadRole stc:writer ] .

cat:agent/release-job%40stc a prov:Agent .
<https://pypi.org/project/statcatlib/0.14.0/> a prov:SoftwareAgent ;
    prov:actedOnBehalfOf cat:agent/release-job%40stc .

cat:inventory/0/42 a prov:Entity, prov:Collection ;
    stc:rootSha256 "…" ;
    prov:wasGeneratedBy cat:history/0/42 ;
    prov:generatedAtTime "2026-10-09T12:30:00.412Z"^^xsd:dateTime ;
    prov:wasRevisionOf cat:inventory/0/41 ;
    prov:hadMember <ni:///sha-256;TO…> .            # changed leaves only, from the log

<ni:///sha-256;TO…> a prov:Entity ;
    stc:product cat:product/14100287 ;
    prov:wasGeneratedBy cat:history/0/42 ;
    prov:wasRevisionOf <ni:///sha-256;FROM…> .

<urn:uuid:0199…a1> a prov:Entity ;                  # generated once, at seal; never invalidated
    prov:specializationOf cat:product/14100287 ;
    prov:wasRevisionOf <urn:uuid:0198…f3> .
<urn:uuid:0198…f3> a prov:Entity ;
    prov:specializationOf cat:product/14100287 .

cat:state/0199…a1/0/40 a prov:Entity ;               # embargoed since version 40
    prov:specializationOf <urn:uuid:0199…a1> ;
    stc:state stc:embargoed ;
    stc:releaseAt "2026-10-09T12:30:00Z"^^xsd:dateTime ;
    prov:wasInvalidatedBy cat:history/0/42 ;
    prov:invalidatedAtTime "2026-10-09T12:30:00.412Z"^^xsd:dateTime .

cat:state/0199…a1/0/42 a prov:Entity ;
    prov:specializationOf <urn:uuid:0199…a1> ;
    stc:state stc:live ;
    prov:wasGeneratedBy cat:history/0/42 ;
    prov:generatedAtTime "2026-10-09T12:30:00.412Z"^^xsd:dateTime .

cat:state/0198…f3/0/38 prov:wasInvalidatedBy cat:history/0/42 ;   # 38 = that entry's from_seq
    prov:invalidatedAtTime "2026-10-09T12:30:00.412Z"^^xsd:dateTime .
cat:state/0198…f3/0/42 a prov:Entity ;
    prov:specializationOf <urn:uuid:0198…f3> ;
    stc:state stc:superseded ;
    prov:wasGeneratedBy cat:history/0/42 ;
    prov:generatedAtTime "2026-10-09T12:30:00.412Z"^^xsd:dateTime .
```

Left unmapped on purpose: `embargo` and `prev_sha256` (integrity data). `extensions_sha256` may later map to `ni:` members of the version.

## Answers to the brief

1. H7: sound as one entity per state interval; retirement must not invalidate the edition; `prov:Attribute` is no PROV-O term (F1, F2, F15).
2. `prov:Collection`: leaves are the right members; assert only the leaves the log knows changed; express each change as a leaf revision (F10).
3. `prov:wasRevisionOf`: right for versions and editions; rollback is still a revision of N; restore needs epoch-qualified IRIs and a defined `previous_inventory` (F7, F11).
4. `stc:` typing: undefined; define under the hub domain, owned by sdmxlib, as subclasses of `prov:Activity`, with a fallback for unknown kinds (F6).
5. Times: do not take start and end from `created_at`; use `generatedAtTime` and `invalidatedAtTime`, monotone in `seq` (F8).
6. `reason`: one output, `stc:reason` under `rdfs:comment`; a reason is not a Plan (F9).
7. Actor and producer: `hadRole` needs a qualified association; actor `prov:Agent`, producer `SoftwareAgent` acting on its behalf (F4, F5).
8. Tombstone: invalidate the last state, not the edition; `retired` holds this version's tombstones only (F2, F3).
9. PREMIS: `linkingAgentIdentifier`, not `linkingAgent`; informative only (F12).
10. DCAT-AP 3 / StatDCAT-AP / `lineage`: no shared IRIs yet; join through the product as a `dcat:Dataset` (F13).
11. Testability: PROV-JSON validation tests syntax only; use a golden Turtle file and constraint checks (F14).
