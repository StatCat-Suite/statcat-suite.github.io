# Style review: Inventory history log

**Target:** `docs/design/inventory-history-log.md` (lines 1-276, hub `17d6e5d` plus the uncommitted draft)
**Lens:** `egm-style`, against the "Writing style" section of the hub `CLAUDE.md`
**Result:** 9 Major, 34 Nit. No Blocker.

## Major

**M1. Goal 5 contradicts the expiry section** (lines 59-60, 160-163). Goal 5 says no principal gains a write or delete path on `inventory/`; lines 162-163 give the release job delete on `inventory/` and `history/`. Rewrite: "The release job's identity gains delete on `inventory/` and `history/` (§10.1). No other principal gains a write or delete path on either prefix." Say which principal writes `history/`.

**M2. Three terms for the end of an edition** (lines 35, 115, 173-174, 192): tombstone, `retired`, `withdrawn`. Add a Terms entry for each word kept, and use one word per concept. Say that `withdrawn` is a state in `entries[].to`, and that a tombstone is an item of `retired`.

**M3. "Inventory version" and "root" are used for one thing; W has two age rules** (lines 1, 18-26, 55, 151-159). Define a version as "the root `inventory/<seq>.json` and the leaves it names"; use "root" only for the file. State one age rule, for example "a root's age is the time since the next root's `created_at`".

**M4. Goal 3 claims a bound the design does not give** (lines 55-56). Checkpoints accrue forever. Rewrite: "so `inventory/` holds the versions inside the retention window, the newest K roots, and one checkpoint per month and per restore epoch."

**M5. The record-validity rule is circular** (lines 141-142). Rewrite: "A record for `seq` N is valid when `inventory/N.json` exists and its SHA-256 equals `root_sha256`. A record stays valid after expiry deletes the root that matched it."

**M6. Four uses of "it" in the retry rule** (lines 142-146). Rewrite as numbered steps with the writer as subject; define "orphan record" and ETag.

**M7. The expiry paragraph runs in reverse of execution order** (lines 156-159). Rewrite as a numbered procedure (compact, verify chain, delete per-record objects, delete roots, delete unreachable leaves). Define "closed range", "retained root" and K.

**M8. The normative PROV-O mapping offers a choice** (line 187): `rdfs:comment` or `prov:Plan`. Pick one.

**M9. Line 191 makes the record the actor.** Rewrite: "`prov:wasGeneratedBy` the activity that moved the edition into that state, and `prov:wasInvalidatedBy` the activity that moved it out."

## Nits

- N1 (line 1): the title says "expire old versions"; the body expires roots and leaves. "Inventory: add a history log with a PROV-O mapping; expire old roots and leaves".
- N2 (line 5): expand EGM once.
- N3 (lines 9-11): "A suite design: sdmxlib owns ..." is a colon setup; "write and expire it" has no clear referent.
- N4 (lines 25-26): the Expiry term omits checkpoints and the newest K.
- N5 (Terms): add `restore_epoch`, K, orphan record, closed range, segment, retained root.
- N6 (line 30): "Every Inventory version writes a full root" makes the version the actor.
- N7 (lines 32, 236): define or link fold, `describe`, seal.
- N8 (lines 32-33): 1.3 MB x 3 x 365 is about 1.4 GB; state 1.4 to 4.7 GB a year.
- N9 (lines 33-35): "nothing may delete it" is negative form; link Phase 2a P7.
- N10 (lines 37-40): "Readers do not slow down" is negative form; storage does not "scan".
- N11 (lines 42, 214): "a poor audit record" is a judgment; state what a root lacks.
- N12 (lines 42-44): two different "it"s in one clause.
- N13 (lines 44-46): "an expiry that nothing performs" alludes; write "No job deletes Inventory objects today."
- N14 (line 50): "small, permanent record" is vague, and per-record objects are later deleted.
- N15 (line 57): expand PROV-O, DCAT-AP, StatDCAT-AP at first use.
- N16 (lines 67-69): the Purview clause describes what Purview lacks; "Fabric" is undefined. Drop it or state the fact.
- N17 (lines 70-71): "The format leaves room for one" alludes; name the mechanism.
- N18 (lines 85-86): "Azure append blobs differ from block blobs" alludes; state that append works only on append blobs, a separate blob type.
- N19 (lines 94-118): explain `embargo`, `restore_epoch`, `previous_inventory` and the `kind` values, one bullet each.
- N20 (lines 121-125, 173-174): "record" used as noun and verb; "entry" collides with product entry and `LeafEntry`.
- N21 (line 136): "then the record" lacks a verb; "then builds the record".
- N22 (lines 146-147): "whose `seq` is above the newest root" compares a number with a file.
- N23 (lines 152-153): "never expired" is passive and negative.
- N24 (lines 154-155): give W's value or the setting that holds it.
- N25 (lines 160-163): "never inside one" and "and no new principal" end on negations; "GC never touches either prefix" is negative.
- N26 (line 165): the heading "What a reader can answer" is close to a hook; "Reader queries".
- N27 (lines 167-176): bold labels are questions answered in place; use noun phrases.
- N28 (line 170): "a known hash" vs line 235's "a hash held outside the catalog"; use one wording.
- N29 (lines 172-176): "refuses" has no object; "a later version of `rebuild-inventory`" overloads "version".
- N30 (lines 180-181): "The specification gives this mapping as normative" states a proposal as fact; `stc:` has no namespace IRI.
- N31 (lines 186, 188, 190): "the activity `prov:wasAssociatedWith` it" uses a predicate as a verb.
- N32 (lines 194-196): expand PREMIS; "where they fit" is vague; "optional" has no subject.
- N33 (Decisions): H1 "Record deltas, not roots." is contrast by negation ("Record each version's changes in a history log."); H3 passive; H4 overstates detection (it cannot detect removed trailing records); H6 has a trailing fragment; H8 "proven practice" is unverifiable.
- N34 (Alternatives onward): line 215 "Rejected by the owner." is passive; "RFC" used in two senses (statcatlib RFC, IETF RFC 8785); line 232 "has a dry run" should say what it lists; line 235 "the stronger answer" is vague; line 236 "local catalogs expire" gives the wrong verb; line 247 "reads neither" lacks a referent; lines 255-256 name "the example record" and "the PROV-JSON schema"; line 261 names no actor; line 270 `prov:Attribute` is no PROV-O class; line 274 cite §6.3 for `LeafEntry`.

## Term consistency

| Concept | Terms in the target | Use |
| --- | --- | --- |
| End of an edition | tombstone, retired, withdrawn | one per concept, defined (M2) |
| Inventory snapshot | Inventory version, version, root | version = root plus its leaves; root = the file (M3) |
| Log item | history record, record, entry | "record"; write `entries[]` items explicitly |
| Software release | "version", "release" overloaded | "Inventory version", "release job", "future `rebuild-inventory`" |
