# Inventory: carry each version's changes in its root, and expire old versions into history segments

* **Author:** Gabriel Gellner
* **Date:** 2026-11-04
* **Status:** Draft, revision 5.
    - Revision 1 had an EGM review
      ([report](egm/inventory-history-log/review_report.md): 7 Blocker, 17
      Major, 10 Nit). The owner then decided three points
      (GH-19, [comment](https://github.com/StatCat-Suite/statcat-suite.github.io/issues/19#issuecomment-6618189422)).
    - Revision 2 had a second review
      ([report](egm/inventory-history-log/round-2/review_report.md): 6 Blocker,
      13 Major, 14 Nit). The owner then decided two more points
      (GH-19, [comment](https://github.com/StatCat-Suite/statcat-suite.github.io/issues/19#issuecomment-6622856856)):
      the change list drops `from_seq`, and expiry deletes leaves under writer
      exclusion.
    - Revision 3 had a third review
      ([report](egm/inventory-history-log/round-3/review_report.md): 1 Blocker,
      8 Major, 9 Nit). The owner then decided three more points on
      2026-11-04: the history fields are defined by their presence and take
      Inventory 1.2 where a number is needed (H19); the root-major fallback is
      dropped in favour of the rollback-window gate (H20); and Phase 5 fills
      `LeafEntry.artefacts` ([Sizes](#sizes)).
    - Revision 4 applied those decisions and the round-3 fixes. The table
      [Review response](#review-response) maps each finding of all three
      rounds to its change.
    - This revision takes three changes from statcatlib's Phase 5 design
      (StatCat-Suite/statcatlib#52, `docs/design/release-job.md`), which the
      owner accepted on 2026-11-10: the leaf-set cache lives on a persistent
      volume (S23); a restore tombstones the editions only its discarded roots
      recorded, and the fold holds registrations older than the restore (S25);
      and a `CatalogAdmin` call waits at most 120 s for the release job's
      lease (S26). sdmxlib's spec carries the same text.
    - The specification PR is StatCat-Suite/sdmxlib#361, and statcatlib's work
      is StatCat-Suite/statcatlib#125. This is a suite design: sdmxlib owns the
      formats, schemas and reader; statcatlib's Inventory writer and release job
      write them; sdmxlib-rest picks up the reader change through its sdmxlib
      floor.
* **Based on:** `main` of each repository, re-read for revision 4 on
  2026-11-04:
    - sdmxlib `b6c79892` (0.84.0), unchanged since revision 2: specification
      `docs/design/sharded-bundle-catalog.md` (Inventory format 1.0), plan
      `docs/design/sharded-bundle-catalog-plan.md`, package
      `src/sdmxlib/inventory/`;
    - statcatlib `2655e871` (0.13.0), the merge of statcatlib#126. Revision 3
      read `95fd7ad`; the merge changes none of the files cited here
      (`src/statcatlib/store/inventory.py`, `src/statcatlib/admin.py`,
      `src/statcatlib/store/EGM.md`). The local checkout's `origin/main` still
      named `95fd7ad`, so revision 4 read `2655e871` through the GitHub API;
    - sdmxlib-rest `f1582e4` (0.9.2), unchanged: `pyproject.toml`,
      `src/sdmxlib_rest/app.py`;
    - hub `main` at `17d6e5d`.

    Every `file:line` below is at these commits.
* **Evidence:** [`egm/inventory-history-log/`](egm/inventory-history-log/review_report.md)
  holds revision 1's lens reports,
  [`round-2/`](egm/inventory-history-log/round-2/review_report.md) holds
  revision 2's, and [`round-3/`](egm/inventory-history-log/round-3/review_report.md)
  holds revision 3's. Sizes come from the corpus of statcatlib's Phase 4 bench
  (StatCat-Suite/statcatlib#126, `bench/corpus-results.md`): 2,521 one-table
  CODR products, 2,979 Inventory versions.

## Terms

- **Inventory version:** one root, `inventory/<seq>.json`, which names one leaf
  per product (specification §6.2, §6.3).
- **Base version:** root `seq - 1`, the head a writer read and won the
  create-if-absent against (§6.6). The chain, the change list and the
  `created_at` rule follow it.
- **Built from:** the root's existing `previous_inventory`. It equals
  `seq - 1` except for a `correct` version, which names an older,
  known-good version (`_format.py:138-140`; `_rules.py:481, 511`).
- **Change list:** the root's new `changes` field. It records what this version
  changed relative to its base version.
- **Root chain:** each root's new `previous_root_sha256`, the SHA-256 of the
  base version's stored bytes.
- **History fields:** `changes` and `previous_root_sha256`. Every rule in this
  design tests for their presence and none tests `format_version` (H19).
- **Retained root:** a root under `inventory/`.
- **Head chain:** the roots and segment lines linked by `previous_root_sha256`
  from the head down to version 1. After a restore to root S it runs through
  S and skips the roots the restore discarded.
- **Checkpoint:** a root that expiry never removes. Root N is a checkpoint when
  N is `history.since_seq`, when N is the first root of its `restore_epoch`, or
  when the UTC month of N's `created_at` is later than root N-1's.
- **Expiry:** the release job's step, or `CatalogAdmin.prune`'s, that moves
  expired roots into history segments and then deletes those roots and the
  leaves no retained root names.
- **History segment:** an append-only JSON Lines object under
  `history/<restore_epoch>/`. It holds a header and one line per root that
  expiry or a restore removed.
- **`expired_through`:** the highest `seq` that expiry has removed from the
  head chain, whatever the root's epoch, held in `inventory/HISTORY`. Every
  root on the head chain above it exists. Below it are checkpoints and the
  roots older than `history.since_seq`.
- **Catalog lock:** the writer exclusion that expiry, opt-in, restores and
  every Inventory write run under. Locally it is an OS advisory lock on
  `<catalog>/LOCK`; on Azure Blob Storage it is a blob lease on
  `inventory/HISTORY` ([Exclusion](#exclusion)).

## Problem

Every Inventory version writes a full root. In the statcatlib#126 corpus a root
holds 222 bytes per product (560,125 bytes for 2,521 products), so at 7,000
products a root is about 1.6 MB. A server writes 3 to 10 versions a day, one
for each fold, release, rollback, embargo change and `describe`, so
`inventory/` grows by 1.7 to 5.7 GB a year. Nothing may delete it:
specification §10.1 gives no principal delete on `inventory/`, and the
Phase 2a design's P7 keeps roots, leaves and tombstones until Phase 4.

Readers stay fast, since a reader goes from `CURRENT` to the newest root and
probes forward without a LIST (§6.6). The cost falls on everything that scans
`inventory/` (the plan's Phase 9 restore tooling, unbuilt), on backups (§10.3)
and on storage.

A root is also a poor audit record. An audit asks what a version changed, who
changed it and why. A root answers only after a diff against the root before
it, and that root may be gone. §11.6 already names an "Inventory version
retention" and says "objects reachable from the newest K roots are never
deleted". Both assume an expiry that nothing performs.

## Goals

1. Each Inventory version records what it changed, who changed it and why, in
   the version itself.
2. The record can be verified. From one trusted root hash and one trusted
   segment hash, a reader can show that no version was altered or removed.
3. On a catalog that opts in, old roots and leaves expire after a retention
   window, so `inventory/` holds the newest K roots, those within the window,
   one checkpoint a month, and the roots from before the opt-in.
4. The Inventory record carries every Inventory fact a W3C PROV-O export
   needs, so a later exporter loses nothing to expiry. A product joins the
   export to DCAT as the `dcat:Dataset` each edition `prov:specializationOf`.
   An edition's seal time and producer are manifest facts (§4.2), and the
   export asserts neither (decision H15).
5. The release job is the only principal that gains a right: delete on
   expired `inventory/` objects. Nothing ever deletes under `history/`.

## Non-goals

- A normative PROV-O mapping, its `stc:` vocabulary and its IRI rules. This
  design gives the data the mapping needs and an informative field-to-term
  table. The vocabulary, IRIs and golden files come with the first exporter, in
  stage 3 (owner decision).
- A PREMIS crosswalk.
- An exporter to PROV-JSON, OpenLineage, Apache Atlas or Microsoft Purview.
  Exporters belong to statcat-serve, later.
- Rebuilding an Inventory from change lists (§6.7). The data allows it, and a
  later design for the Phase 9 restore tooling can specify it.
- Lineage of datasets or observations. statcatlib's `lineage` table covers
  datasets.
- A Merkle log (RFC 9162) with inclusion and consistency proofs, and signed
  roots. The root chain leaves room for both.
- Server expiry on S3 or GCS in stage 2 (H21).

## Design

### Root history fields

The root gains two fields. A writer that has them always writes both, and a
1.x reader ignores them (§6.3 versioning; `decode_root` refuses only another
major, `_format.py:274`).

| field | meaning |
| --- | --- |
| `previous_root_sha256` | SHA-256 of the stored bytes of the base version, root `seq - 1`, or `null` for version 1. After a restore, root `seq - 1` is the root the restore kept (see [Restores](#restores)). |
| `changes` | The change list: one item per product whose leaf hash differs from the base version's, sorted by `product_id`. |

The fields are defined by their presence (H19). `since_seq`, the opt-in
refusal, expiry's stop rule and `verify-catalog` each test whether a root
carries both, so the fields ship independently of sdmxlib#348's routing
fields. One constant versions roots and leaves (`INVENTORY_FORMAT`,
`_format.py:22-23`), and sdmxlib#348 claims Inventory 1.1 for the routing
fields. Where a number is needed (`INVENTORY_FORMAT`, the schemas), this
design takes Inventory 1.2.

`previous_inventory` keeps its meaning, the version this one was built from.
For every kind except `correct` it equals `seq - 1`. The chain and the change
list follow `seq - 1`, so a correction at 41 built from 39 still links root 40
and diffs against it.

A change item:

| field | meaning |
| --- | --- |
| `product_id` | The product. |
| `leaf_sha256` | `{from, to}`. `from` is `null` for a new product. `to` is `null` for a product removed from the Inventory. |
| `entries` | One item per edition whose entry or tombstone differs between the base leaf and the new leaf, sorted by `edition_id`. |

An entry item:

| field | meaning |
| --- | --- |
| `edition_id` | The edition. |
| `from` | Its state in the base version (`embargoed`, `live`, `superseded`, `withdrawn`), `tombstone` when the base version's `retired` list holds it, or `null` when the base version has neither. |
| `to` | The same values for this version. `null` means this version drops the edition's tombstone from `retired`. |
| `entry` | The new `LeafEntry`'s `edition_id`, `previous`, `state`, `manifest_sha256`, `schema_version`, `state_changed_at` and `release_at` (§6.3). It is absent when `to` is `tombstone` or `null`. |

Rules for items:

- An item whose `from` equals `to` records an entry that changed and kept its
  state, such as a rescheduled `release_at`.
- `tombstone` marks the `retired` list and is not a fifth state. §6.4's
  "Retirement is a tombstone, never a state" stands. A tombstone comes from a
  `retire` version, or from the `restore` version for an edition only the
  discarded roots recorded; `reinstate` gives `from: tombstone, to: superseded`.
- Nothing removes a tombstone from `retired` today (`prune` "never expires a
  tombstone", statcatlib `admin.py:538`). A later writer that does writes
  `to: null`, so a replay of `retired` stays exact.
- `entry` omits `structure_source`, `artefacts` and any later optional
  `LeafEntry` field. `manifest_sha256` pins what the manifest holds, and a
  format minor that wants a later field in `entry` says so.

Writer rules that come with the history fields:

- A writer computes the change list and `previous_root_sha256` from the base
  version and its leaves, and reads no other version. A writer that loses the
  race for a `seq` re-reads the head and computes both again, as it already
  re-evaluates its preconditions (§6.6).
- `created_at` is at least the base version's `created_at` plus one
  millisecond, across epochs as well. A writer whose clock reads earlier
  writes that instant.
- A writer refuses a base whose `created_at` is more than 5 minutes ahead of
  its own clock, and names the base's time in the error. One fast clock then
  cannot pin `created_at` for every later writer.
- A server writer takes its time from the storage `Date` header under §6.4's
  skew bound, as the release clock already does (§6.4, line 451).
- On a catalog that opts in (below), a writer refuses a base at or below
  `HISTORY.expired_through`. Expiry frees the names of the roots it deletes,
  and create-if-absent would otherwise let a stale writer reuse one. The
  writer checks after it takes the catalog lock, against a fresh read of
  `HISTORY`, so an expiry between its head read and the lock cannot reopen a
  name.

Event kinds. The kind `reinstate`, which `reinstate` (`_rules.py:425-461`;
Phase 4 work in the plan, line 333) records, arrives in Inventory 1.2 with
the history fields (H24). A
server fold of `pending/` records `seal`. The owner's Phase 7 kind `search`
(GH-19) arrives in its own minor version.

The hash is over each root's stored bytes, which is how `CURRENT` and
`products[].leaf_sha256` already hash. No canonical JSON is needed.

### Sizes

Measured on the statcatlib#126 corpus, compact JSON, one-table products. A
release item has two entry items (the new edition `embargoed` to `live`, the
old one `live` to `superseded`).

Phase 5 fills `LeafEntry.artefacts`, and the cross-product rules read the
artefact records from leaves instead of opening manifests (owner,
2026-11-04). The filled column is the expected case. It assumes the 9
artefact records each corpus manifest holds (1,884 bytes per entry). The
empty column is today's writer, which leaves the field empty.

| Object | Expected: `artefacts` filled (Phase 5) | Today: `artefacts` empty |
| --- | --- | --- |
| Root at 7,000 products | 1.6 MB | 1.6 MB |
| One-edition leaf | 2,579 bytes | 665 bytes |
| Change item for a release (this design's `entry`) | 920 bytes | 920 bytes |
| Change list, release of 200 tables | 185 KB | 185 KB |
| Change list, republish of 7,000 products | 6.5 MB | 6.5 MB |
| Change list, republish, if `entry` were the whole `LeafEntry` | 33 MB | 7.0 MB |

The leaf row is measured (StatCat-Suite/statcatlib#137): the average leaf as
written, in indented JSON, with one dataflow URN and `pull_bytes`, and with 10
artefact records in the filled column. The other rows are the original
estimates.

Under this design's `entry`, filling `artefacts` changes leaves only. A leaf
keeps every edition until it is retired, so a leaf with n editions is about
n times the entry size.

### Write order

Unchanged from §6.6: leaves, then the root (create-if-absent), then `CURRENT`.
The root is the record and the commit point, so a version can never exist
without its record.

### The reader

The reader change ships in stage 1, before any catalog can opt in. It changes
nothing on a catalog that never expires.

- With `CURRENT` present and naming a root that verifies, nothing changes, and
  the reader reads no new object. Expiry never removes the root `CURRENT`
  names (step 1).
- When `CURRENT` is missing or names a root that fails, the reader reads
  `catalog.json`, and on a 2.x document `inventory/HISTORY`:
    - it takes the epoch from `HISTORY.restore_epoch`, or from `catalog.json`'s
      `restore_epoch` on a 1.x catalog. Today's reader assumes epoch 0 when
      `CURRENT` is missing (`_reader.py:128`), which this fixes;
    - its lower bound is the larger of the `seq` it holds in that epoch and
      `expired_through` (0 on a 1.x catalog);
    - its walk back stops at the lower bound, and its forward probe starts one
      above it;
    - it drops a held root at or below `expired_through`;
    - it fails closed when it finds no root above the lower bound and holds
      none, and when a 2.x catalog has no `HISTORY`.
- The reader's `catalog.json` decode accepts majors 1 and 2. The writer's
  check keeps its own rule (see [Catalogs that expire](#catalogs-that-expire)).

The fallback costs one or two GETs, only on the path where `CURRENT` has
failed. §10.1 gives pods no read of `catalog.json` today (specification
697-704); the specification PR adds a pod read of `catalog.json` and
`inventory/HISTORY`.

### Catalogs that expire

Expiry is opt-in per catalog.

- `catalog.json` gains `history: {"since_seq": N}`, and its `format_version`
  becomes `"2.0"`. `since_seq` is the lowest `seq` from which every root
  carries both history fields. Opt-in refuses a catalog where a root without
  them follows a root with them, and a catalog whose head lacks them. Roots
  below `since_seq` never expire.
- The 2.0 document locks out writers. statcatlib's `try_commit` decodes
  `catalog.json` on every commit (`store/inventory.py:426`, through
  `catalog_document()` at `:315`), and `decode_catalog` refuses another major
  (`_format.py:284-290`). A writer accepts 2.x only from the statcatlib
  release that takes the catalog lock and checks `expired_through` (stage 2).
- Before stage 1, no serving reader reads `catalog.json`. `_Chain.refresh`
  reads only `CURRENT` and roots (`_reader.py:119-155`). sdmxlib-rest's `src/`
  reads no Inventory object, and in a pod the reader is the consumer's
  `CatalogProvider`. The stage-1 reader and the [Expiry gates](#expiry-gates)
  cover serving readers.
- Opt-in runs under the catalog lock. It writes `HISTORY` with
  `expired_through: 0` before it rewrites `catalog.json`, so a 2.x catalog
  without `HISTORY` is an error. §6.1 today allows a `catalog.json` rewrite
  "only to bump `restore_epoch`" (line 328); the specification PR adds the
  opt-in. Locally the rewrite uses read, compare and rename, and refuses if
  `restore_epoch` changed since the read. On blob storage it is a conditional
  write.
- An old writer can decode `catalog.json` before the rewrite and create a root
  after it, with no lock (`store/inventory.py:426-432`). The first expiry
  therefore runs in a later call than the opt-in, and expiry stops at any root
  at or above `since_seq` that lacks the history fields (step 1).
- Local catalogs opt in and expire through `CatalogAdmin`. A server catalog
  opts in before the release job's first expiry. On a blob store other than
  Azure Blob Storage, opt-in is refused (H21).

### Expiry gates

Every server expiry run checks two gates. A run that fails either skips
expiry, alerts, and still performs its release step.

1. **Rollback window (the gate).** The release job's configuration holds
   `expiry_not_before`: the time the rollback window closes for the last pod
   image built before the stage-1 sdmxlib (§9.2 step 5, specification line
   685). The job refuses every expiry before that time. On an opted-in
   catalog, the image runbook forbids rolling the pods back to an image older
   than stage 1.
2. **Pod versions (detection).** The job reads every serving pod's sdmxlib
   version on every expiry run:
    - sdmxlib-rest raises its sdmxlib floor to the stage-1 release (today
      `sdmxlib>=0.84,<0.85`, `pyproject.toml:38`), so no later build lacks the
      fallback.
    - sdmxlib-rest adds `sdmxlib_version`, from
      `importlib.metadata.version("sdmxlib")`, to its `GET /` payload in both
      branches. A consumer's `root_payload` replaces the default payload
      today (`app.py:143, 233-241`), so the field is added after that choice.
    - The job lists the pods of every Inventory-reading Deployment from the
      Kubernetes API by label, not-Ready pods included: `hot`, `base` and
      `search` (specification line 897) and the preview deployment that runs
      `EmbargoReader`. Headless Service DNS omits not-Ready pods unless
      `publishNotReadyAddresses` is set (verify before citing), so the job
      uses the API.
    - An unreachable pod, a missing field, or a version older than stage 1
      counts as a failure.
    - Jobs that read the Inventory have no endpoint to poll: the
      pre-materialisation job runs the pods' image (specification line 737),
      and GC reads the chain (§11.4). Gate 1 covers them.
    - Where the release job cannot reach the Kubernetes API, gate 1 alone
      applies, and the run reports the pod check as not run.

An old reader skips a root it cannot decode and walks back past it
(`_reader.py:109-113, 134-136`), so no root format can make it fail closed
(H20). Expiry never removes the root `CURRENT` names (step 1), so an old pod
misbehaves only when `CURRENT` is missing or names a root that fails to
verify, and gate 1 covers that case.

Local catalogs have no pods. The opt-in documentation tells the operator to
upgrade any local sdmxlib-rest first.

### History segments

```text
<catalog>/
  LOCK                              the local catalog lock, never deleted
  inventory/<seq>.json              retained roots
  inventory/leaves/<sha256>.json    leaves that retained roots name
  inventory/HISTORY                 the epoch, expired_through and the segment pointers
  history/<restore_epoch>/<first:012d>-<last:012d>-<uuid7>.jsonl   create-only segments
```

- A segment holds roots of one `restore_epoch` and sits under that epoch's
  directory, even when a later epoch writes it. A run writes one segment per
  epoch it expires from, and splits a segment at 1,000 lines or 64 MiB,
  whichever comes first. A run writes its segments in chain order: each
  names the one before it as `previous_segment`.
- The name pads `seq` to 12 digits, as `root_path` does (`_format.py:245`),
  and a UUIDv7 suffix makes every name unique, so a rerun never collides with
  an orphan.
- The first line is the header: `{format_version: "1.0", catalog_id, kind,
  restore_epoch, first, last, previous_segment, previous_segment_sha256,
  expired_at, actor, roots, leaves, unread}`.
    - `kind` is `expiry` or `restore`. The crash rule and `expired_through`
      consider `expiry` segments only.
    - `previous_segment` is `HISTORY.newest_segment` when the segment is
      written, whatever its epoch, so all segments form one chain.
    - `roots` lists the `seq` of each root the run deletes, and `leaves` the
      hash of each leaf it deletes. The header is the plan, written before any
      deletion.
    - `unread` lists the `seq` of each root a restore deletes and could not
      read (see [Restores](#restores)). It is empty in an `expiry` segment.
- Each following line is one removed root with `products` and `retired`
  removed, plus `root_sha256`, the SHA-256 of the root's stored bytes. A line
  keeps `seq`, `previous_inventory`, `restore_epoch`, `created_at`,
  `producer`, `event`, `embargo`, `extensions`, `previous_root_sha256` and
  `changes`. A line is compact JSON in the root's field order, ended by one
  `\n`.
- Segments are written create-if-absent and never rewritten or deleted. The
  specification recommends object lock on `history/` for servers (see
  [Alternatives considered](#alternatives-considered)).
- `inventory/HISTORY` is `{format_version: "1.0", catalog_id, restore_epoch,
  expired_through, newest_segment, newest_segment_sha256, cleaned_through}`.
  `cleaned_through` names the newest segment whose roots and leaves are
  deleted (steps 5 and 6). `HISTORY` is written under the catalog lock:
  conditionally and with the lease ID on Azure, and locally with read,
  compare and rename.

A reader finds segments without a LIST by following `newest_segment` and each
header's `previous_segment`.

### Expiry

Expiry runs in the release job's identity, after the release step of the same
run and never inside it, and in `CatalogAdmin.prune`.

#### Exclusion

Expiry, opt-in, restores and every Inventory write run under the catalog lock.

Locally:

- The lock is `fcntl.flock(LOCK_EX)` on POSIX and `LockFileEx` on Windows, on
  `<catalog>/LOCK`. The writer creates the file once and never deletes it.
  The OS releases the lock when the process exits, so a crash leaves no stale
  lock. The specification already documents network shares as unsupported
  (line 497), which an advisory lock needs.
- `InventoryWriter.try_commit` takes the lock, since it is public
  (`store/EGM.md:152`) and holds the leaf writes and the root create
  (`store/inventory.py:415, 432`). It holds the lock from the first leaf
  existence check to `CURRENT` (`:436`). `commit` reads the head before any
  lock (`:472`), so the stale-base refusal runs inside `try_commit`, after the
  lock is taken.
- The lock is per call and not reentrant. `prune` commits its `retire`
  version through `commit` (`admin.py:663`) and releases the lock before it
  takes the lock for expiry. Code that holds the lock and writes a root (a
  restore) calls the writer's internal commit, which assumes the lock.
- The local writer skips a leaf it finds present (`store/inventory.py:339-344`).
  Under the lock no expiry runs between that check and the root, so the
  skipped leaf survives.

On Azure Blob Storage:

- The release job runs one instance at a time. On an opted-in catalog it holds
  a lease on `inventory/HISTORY` for its whole run. A second run, started by
  hand or by a second schedule, fails to take the lease and writes nothing.
  statcatlib's blob writer takes the same lease: an operator's `CatalogAdmin`
  call under the release job's identity waits up to 120 s for it, then fails
  and names the runbook that breaks a lease. The release job expires only in
  runs scheduled for expiry, at times with no release, so a run at a release
  time holds the lease for the seconds its other steps take.
- The lease lasts 60 s and the holder renews it every 20 s. Before each
  destructive call (a segment write, a `HISTORY` write, a root or leaf
  delete) the holder checks that its last successful renewal is less than
  40 s old, and stops expiry otherwise. A failed renewal stops the run's
  expiry; the next run's crash rule finishes it. Azure's lease limits (15 to
  60 s, or infinite) are marked verify before citing.
- A lease fences writes to `HISTORY` only, and a paused holder (a frozen VM,
  a partition) can still call delete after its lease lapsed. Leaf deletes
  therefore carry `If-Match` with the ETag read at step 6's final check, and
  the blob writer writes each leaf of its version with an unconditional Put
  of the same bytes. In either order the leaf survives: a Put before the
  delete changes the ETag and the delete fails; a Put after it recreates the
  leaf. A carried-forward leaf is safe because its base root is the head,
  which expiry keeps. This amends the plan's create-only rule for leaves
  (plan line 330); roots stay create-only.
- A run holds the lease for at most 30 minutes, then releases it and alerts.
  A runbook breaks a lease only after the holding job's pod has stopped, so a
  hung holder cannot block an emergency withdraw or rollback for longer.

S3 and GCS have no blob lease. Server expiry is Azure-only in stage 2 (H21).

#### Steps

0. **Advance `CURRENT`.** Bring `CURRENT` up to the head, as the release job
   already does on startup (specification line 495). `prune` does the same.
1. **Choose.** Walk the roots in `seq` order from the larger of
   `expired_through + 1` and `since_seq`. Step over a checkpoint, which stays.
   Take a root when it is below `CURRENT.seq`, outside the newest K (K ≥ 2,
   default 10), and its successor's `created_at` is older than the retention
   window W by the storage clock. Stop at the first root that is neither a
   checkpoint nor taken, and at the first root that lacks the history fields;
   `verify-catalog` reports the latter. The candidates are therefore a
   contiguous run of `seq`, checkpoints excepted, never below `since_seq` and
   never at or above `CURRENT.seq`. `created_at` is the fifth field in field
   order (`_format.py:153-157`), so a ranged GET of a root's first 1 KiB reads
   it.
2. **Verify.** Check the chain over the candidates, from the newest segment's
   last line (or the checkpoint below the candidates) to the first retained
   root above them, over stored bytes. Refuse to continue on a mismatch. The
   full walk is `verify-catalog`'s job.
3. **Write the segments.** LIST `history/` first. A segment that `HISTORY`
   does not name is a crash's orphan. Adopt orphans only when the first one's
   `previous_segment` is `HISTORY.newest_segment` and each later one links to
   the one before, the first one's first line is the lowest candidate, every
   line lies within the current candidates, and each line matches its root's
   bytes. Report and leave any other orphan. Then write the remaining
   segments create-if-absent, in chain order, with the header's `roots` and
   `leaves`, and check each line's `root_sha256` against the root's bytes.
4. **Advance `HISTORY`** to the new `expired_through` and newest segment.
5. **Delete the candidate roots.** Delete each one only after the SHA-256 of
   its stored bytes matches `root_sha256` on its line.
6. **Delete leaves** that no retained root names. LIST `inventory/*.json`
   and read every retained root: the reader's range from `expired_through + 1`
   misses the roots below `since_seq`, the checkpoints and the unmatched roots
   kept below `expired_through`. Delete each leaf in the headers' `leaves`
   that no retained root names, with `If-Match` on Azure.
7. **Advance `cleaned_through`** in `HISTORY` to the newest segment.
8. **Log.** The deletion log records each object deleted. A dry run performs
   steps 1 and 2 and reports what steps 3 to 7 would do.

**Cost of step 6.** In the statcatlib#126 corpus, 2,979 roots at 560 KB to
1.6 MB each come to 1.7 to 4.7 GB read per run, at 3 to 10 runs a day. The
release job caches each root's SHA-256 and leaf set, keyed by the root's path
and the ETag the LIST returns. The cache lives on a persistent volume the job
mounts (`--state-dir`), so it survives between runs, and it holds root paths,
ETags, SHA-256s and leaf hashes only. Roots never change, so after the first
run a run reads only the roots written since the last one (3 to 10 a day, 5 to
16 MB). An ETag that differs from the cached one forces a re-read. Without the
volume, every run pays the first run's read.

**Crashes.** A crash before step 4 leaves orphan segments; the next run adopts
them in step 3. A crash after step 4 leaves the plans in the headers of the
`expiry` segments after `cleaned_through`, up to `newest_segment`. The next
run processes only those headers. It deletes a root they list only when its
bytes match a line in those segments, and it repeats step 6 for their
leaves. Any other root at or below `expired_through` is reported and kept: a
checkpoint, a root older than `since_seq`, or a root a stale writer created.

Leaves that a crashed commit wrote before its root appear in no header, so
expiry never deletes them. The leak is safe, since no root names them, and
bounded by one version's changed leaves per crash.

#### Bounds

The specification PR replaces §11.6's retention text:

- W is at least the `data/` GC window plus one day, both measured from the
  superseding root's `created_at` in storage time. §11.6 already orders backup
  retention at or below the GC window (line 768), so W covers backups too.
- The pod-staleness alert (§11.6, line 774) fires well inside W, since a pod
  stuck on one root for W loses its uncached leaves (`_reader.py:177-184`).
- K ≥ 2, default 10. K keeps the fallback walk's reach when `CURRENT` and the
  head both go bad: at 3 to 10 versions a day, 10 versions is 1 to 3 days.
  A 5 s pod poll bounds W, which any W counted in days meets, and leaves K
  free.
- GC stops its walk at `expired_through`, fails closed on a missing root above
  it, and never touches `inventory/` or `history/` (§11.4).

### Restores

- On an opted-in catalog, every restore bumps `restore_epoch` (§6.1). A
  storage-level rollback that keeps the epoch (the conformance suite's
  `restore_to`, `conformance.py:110-112`) is unsupported there: under object
  lock the newer segments survive it, and `(restore_epoch, seq)` would be
  reused. `restore_to` stays for catalogs that have not opted in.
- A restore to root S runs under the catalog lock, in this order:
    1. it writes the roots after S, checkpoints included, into a `restore`
       segment of the old epoch. After a failover some of them may be
       unreadable; the segment holds the lines it can read and lists the rest
       in `unread`;
    2. it writes `HISTORY` with the new epoch, `expired_through` set to the
       smaller of its old value and S, and `newest_segment` set to the
       restore segment;
    3. it bumps `restore_epoch` in `catalog.json`;
    4. it deletes the roots above S;
    5. it writes root S + 1 of the new epoch, whose `previous_root_sha256`
       hashes root S, through the writer's internal commit. Its `retired`
       holds root S's tombstones and a tombstone for each edition that a
       discarded root it could read records in a leaf and that root S records
       in neither a leaf nor `retired`. GC then keeps those editions' files
       while the tombstones are within the window, and `reinstate` can bring
       one back;
    6. it writes `CURRENT`.
- A crash after step 2 leaves readers whose `CURRENT` fails with the new
  epoch and no root in it, so they fail closed until root S + 1 exists. A
  rerun resumes from the epoch in `HISTORY`.
- A restore deletes no leaves. The leaves only its discarded roots named
  leak as orphan leaves do, until a later design adds their collection.
- A restore only adds segments under `history/` and never deletes or
  overwrites one.
- On a restore epoch above 0, the fold records a `pending/` registration last
  modified before the `created_at` of the epoch's first root, whose edition
  the head does not record, with `release_at: null`, so only an explicit
  release publishes a registration that predates the restore (spec §11.2
  step 2).
- Backups copy in this order (§10.3): `data/`, edition directories, leaves,
  roots, `inventory/HISTORY`, `history/`, then `CURRENT`. A root missing at
  copy time was deleted after its segment and `HISTORY` were written, so the
  later copies hold its line.

### `verify-catalog`

`verify-catalog` checks:

1. the root chain over the union of retained roots and segment lines, keyed
   by `(restore_epoch, seq)`. The chain branches at each restore's S, and a
   key present in both a root and a line must have the same `root_sha256`;
2. every retained root's leaves;
3. the segment links and kinds, `HISTORY` (every root on the head chain above
   `expired_through` exists, no `expiry` line on the head chain lies above
   it, and `cleaned_through` lies on the segment chain at or below
   `newest_segment`), that every root at or above `since_seq` carries the
   history fields, and the checkpoint rule recomputed from roots and lines.
   It reports unlinked, orphan and overlapping segments.

Checkpoints are audit records. GC deletes retired editions' directories
(§11.4), so an old checkpoint's leaves can name manifests that are gone, and
`verify-catalog` checks a checkpoint's leaves only.

### What a reader can answer

| Question | From |
| --- | --- |
| What changed in version N, who changed it and why | root N's `changes` and `event`, or its segment line |
| What was live at time T | the checkpoint at or before T, then the change lists forward to T in `seq` order |
| Was a version altered or removed | the chain, from one trusted root hash and one trusted segment hash, which the release job can publish outside the catalog |
| A rolled-back catalog's history | every `withdrawn` transition and every restore's `restore` segment |

### Embargo and access

- A change list names embargoed editions and their `release_at`, as a root
  does. `history/` therefore gets the access row `inventory/` has in §10.1. A
  backup copies `history/` in the order above.
- A full export (`CatalogAdmin.export`, §6.1 line 333, unbuilt in statcatlib)
  copies `inventory/` and `history/` unchanged and keeps `catalog_id`. A
  live-only export writes a new chain, so it takes a new `catalog_id`; the
  specification PR amends §6.1 line 333 for that case.
- A live-only export carries only transitions into or out of `live`. For an
  `embargoed` to `live` item it keeps the start of the live state and drops
  the end of the embargoed one, so the embargoed state's identity does not
  leak.
- A local `event.actor` is `<os user>@<hostname>` (`store/inventory.py:214-220`),
  which is personal data. It stays in segments for good, so an operator who
  needs another identity sets the actor explicitly.

### Data for a PROV-O export (informative mapping)

The change list, the segment header and the root's existing fields carry the
facts below. These data requirements are normative with the history fields.
The mapping beside them is informative and becomes normative in stage 3, with
the `stc:` vocabulary, the IRI rules, a golden Turtle file checked with
rdflib, and constraint checks.

| Record | PROV-O term (informative) |
| --- | --- |
| `event` | a `prov:Activity`, typed by its kind, with the reason. It carries no start or end time. |
| `event.actor` | a `prov:Agent` in a qualified association with an actor role, plus `prov:wasAssociatedWith` |
| `producer` | a `prov:SoftwareAgent` with a writer role, and a qualified delegation to the actor scoped to the activity (`prov:qualifiedDelegation` with `prov:hadActivity`; verify before citing) |
| The Inventory version | a `prov:Entity`, `prov:wasGeneratedBy` the activity at `created_at`, `prov:wasRevisionOf` the version it was built from (`previous_inventory`), with its changed leaves as members on every export |
| Leaf bytes | an entity named by the leaf hash. The export asserts no generation or revision on bytes, since a correction or restore can put the same bytes back |
| An edition | a `prov:Entity` that `prov:specializationOf` its product and `prov:wasRevisionOf` its `previous`. The Inventory export asserts no generation time or producer for it and never invalidates it |
| An entry item | the state interval it ends `prov:wasInvalidatedBy` the activity at `created_at`; the interval it starts `prov:wasGeneratedBy` the activity at `created_at`, carries the state, and `prov:specializationOf` the edition |
| An embargoed state | its `release_at` |
| `embargo`, `extensions` on a version | attributes of the version entity, so `embargo-change` and `describe` versions, whose change lists are empty (statcatlib `admin.py:483, 514`), still export their effect |
| A segment header's `expired_at` and `actor` | an expiry activity |

The rules behind the table:

- A state interval is one entity (H7). PROV-CONSTRAINTS allows at most one
  generation and one invalidation per entity (the unique-generation and
  unique-invalidation constraints; verify before citing), and states recur
  after a rollback or `reinstate`.
- The exporter numbers state intervals by replaying the change lists from
  `since_seq` in `seq` order (owner decision). The interval an item ends is
  the one the edition's most recent earlier item started. An entry whose
  state began before `since_seq` gets a baseline interval from the
  `since_seq` checkpoint, with no generation asserted.
- State entities take their times from `created_at`, never from
  `state_changed_at`. The two come from separate clock reads (statcatlib
  `admin.py:325`, `store/inventory.py:422`).
- An edition's seal time and producer are its manifest's `created_at` and
  `producer` (§4.2, line 141). `LeafEntry` copies neither, a server seal runs
  on a build node before the fold, and GC deletes retired editions'
  manifests. The export therefore makes no claim about an edition's
  generation (H15).
- The root chain fields and `root_sha256` are integrity data, and the export
  leaves them unmapped apart from naming the version's bytes.

Stage 3 carries the vocabulary, IRIs and a worked example that parses.
Revision 2's linked Turtle example is withdrawn: it uses `/` and `…` in
prefixed names, which Turtle 1.1's `PN_LOCAL` rejects, and it drifted from the
mapping. The stage-3 design starts from these requirements:

- a fixed default IRI base, recorded in `catalog.json` if another is allowed;
- lowercase `urn:uuid` for editions (RFC 9562), unpadded base64url for
  `ni:///sha-256;` names (RFC 6920), and uppercase percent-encoding of actors
  (verify each before citing);
- a rule for a producer version of `"unknown"` (`store/inventory.py:210`);
- the product IRI a DCAT exporter mints as the `dcat:Dataset`;
- `stc:reason` declared an `owl:AnnotationProperty` if it stays a
  sub-property of `rdfs:comment`, and an `owl:versionIRI`;
- the hub's reservation of `https://statcat-suite.github.io/ns/inventory#` and
  `/id/`.

## Decisions

| # | Decision | Reason |
| --- | --- | --- |
| H1 | A version records its changes in its root. | The root is already the commit point, so a record and its root can never disagree, and no extra object is written (owner, 2026-11-03). |
| H2 | Expired roots move into append-only segments keyed by `restore_epoch`. Nothing under `history/` is deleted. | Bounded `inventory/`, a permanent audit record, and no delete right on the history (owner, 2026-11-03). |
| H3 | The root chain hashes stored bytes. | It matches how `CURRENT` and leaves hash, and the suite has no RFC 8785 implementation. |
| H4 | Checkpoints are `since_seq`, the first root of each epoch, and the first root of each UTC month by `created_at`. | "Live at T" replays at most a month of change lists, a replay never crosses a restore, and version 1 is the first root of epoch 0. |
| H5 | Expiry runs in the release job, after its release step, and in `prune`. | The release job already holds the only server write path to `inventory/`. |
| H6 | Expiry is opt-in, through `catalog.json` 2.0. The 2.0 document locks out writers before stage 2. | Old writers decode `catalog.json` on every commit and would write roots without the history fields or the lock. Answers round-2 Question 1. |
| H7 | A PROV state entity is one interval in one state. | PROV-CONSTRAINTS allows one generation and one invalidation per entity, and states recur after rollback and `reinstate`. |
| H8 | The PROV-O mapping is informative until an exporter exists. The data is normative now. | The model can be corrected against a real consumer without a format change (owner, 2026-11-03). |
| H9 | The Inventory stays a root-and-leaf log; §6.6's escape route is reviewed and not taken. | See [The §6.6 escape route](#the-66-escape-route). |
| H10 | The chain, the change list and the `created_at` rule follow root `seq - 1`. `previous_inventory` stays "built from". | A correction built from an older version would otherwise leave a root unlinked and a change list against the wrong state (round-2 Blocker 1). |
| H11 | The change list has no `from_seq`, and `LeafEntry` gains no fields. The exporter numbers state intervals by replay. | The writer reads one version and cannot know the `seq` that started a state; the identifier serves stage 3 only (owner, 2026-11-03). |
| H12 | Expiry deletes leaves under writer exclusion: an OS advisory lock on `<catalog>/LOCK`, taken in `try_commit`, locally; one release-job instance holding a 60 s renewed lease on `inventory/HISTORY`, with `If-Match` leaf deletes, on Azure. Step 6 deletes leaves no retained root names, with no recreate. | A grace period cannot protect a reused leaf, which is old by any timestamp (owner, 2026-11-03). The OS lock leaves no stale lock after a crash, and `If-Match` keeps leaf safety independent of lease timing (round-3 Majors 3, 4). |
| H13 | The reader's `HISTORY` fallback ships in stage 1. | Serving readers never read `catalog.json`, so the 2.0 document cannot lock them out; H20 gives the expiry gates. |
| H14 | `entry` carries seven `LeafEntry` fields and omits `structure_source`, `artefacts` and later optional fields. | `manifest_sha256` pins them, and the change list keeps its size when Phase 5 fills `artefacts` ([Sizes](#sizes)). |
| H15 | The Inventory export asserts no generation for an edition. | Its seal time and producer are manifest facts the Inventory does not carry, and GC deletes retired editions' manifests (round-2 Blocker 3, option a). |
| H16 | `catalog_id` lives in `catalog.json`, the segment header and `HISTORY`, and stays out of the root. | A root lives inside its catalog; a segment or an export names the catalog through its header. |
| H17 | K = 10 by default, K ≥ 2. | The pod poll bounds W and leaves K free; 10 versions keep 1 to 3 days for the fallback walk. Answers round-2 Question 3. |
| H18 | A change list marks the `retired` list with `tombstone`, distinct from the four states. | §6.4 says retirement is a tombstone and never a state, and the marker keeps that sentence true. |
| H19 | `changes` and `previous_root_sha256` are defined by their presence. Every rule tests for them, and where a number is needed they take Inventory 1.2. | They ship independently of sdmxlib#348's routing fields, which claim 1.1 (owner, 2026-11-04). Answers round-3 Question (a). |
| H20 | No root-major lock-out. Every server expiry waits until the §9.2 rollback window of the last pre-stage-1 pod image has closed, and checks every pod's `sdmxlib_version` on every run, counting an unknown version as a failure. | An old reader skips an undecodable root and walks back (`_reader.py:109-136`), so a root major makes old pods serve stale versions from the opt-in (owner, 2026-11-04; round-3 Blocker 1). Answers round-3 Question (b). |
| H21 | Server expiry is Azure-only in stage 2. Opt-in on another blob store is refused. | S3 and GCS have no blob lease; a lock object with a TTL needs its own fencing design. |
| H22 | On an opted-in catalog every restore bumps the epoch, and an epoch-keeping rollback is unsupported. | Under object lock, newer segments survive an epoch-keeping rollback and `(restore_epoch, seq)` would be reused (round-3 Major 7). |
| H23 | H21 stands: stage 2 adds no server expiry for S3 or GCS. | The deployment target is Azure. S3 support needs a conditional lock object with a TTL and fencing through `If-Match` on `HISTORY`, designed when a deployment needs it (owner, 2026-11-04). |
| H24 | Inventory 1.2 adds the `reinstate` kind, with the history fields. | One minor bump carries both, whichever specification PR merges first (owner, 2026-11-04). |

### The §6.6 escape route

§6.6 says a need for "checkpoints, leaf compaction or more tree levels" in the
Inventory triggers a review of replacing it with a Delta table of Inventory
rows (statcatlib RFC decision 31). This design adds checkpoints and expiry, so
the review is due. Its result:

- **A Delta table lists its log.** A Delta reader finds commits after
  `_last_checkpoint` by listing `_delta_log/`. The Inventory reader probes
  forward without a LIST (§6.6), which keeps pod polling cheap on blob storage
  and works through a `fetch(path)` callable with no client library.
- **Delta's log retention deletes history.** `logRetentionDuration` removes old
  commits after checkpointing, so a Delta-backed Inventory would still need a
  permanent audit log beside it.
- **Delta has no per-product sharing of state.** A leaf is content-addressed
  and shared by every root that didn't change that product. A Delta table of
  rows rewrites or tombstones rows per commit, so the same changes cost more
  objects.
- **The prototype stays.** GH-252's conformance suite runs against the
  Delta-backed prototype, so the route stays open if a later need (a LIST-based
  reader, leaf compaction, or more tree levels) arises.

The specification PR amends §6.6: checkpoints kept by expiry, and history
segments, do not trigger the route; the remaining triggers are leaf compaction
and more tree levels.

## Alternatives considered

- **A separate history record per version** (revision 1). Rejected. A crash or
  a lost race leaves a record that describes a different root (round-1
  Blocker 1), and it costs an extra object per version.
- **Keep every root and tier old objects to cool or archive storage.**
  Rejected by the owner. Storage stays unbounded.
- **GC expires old versions.** Rejected. It gives GC a write path to
  `inventory/`.
- **A grace period on leaf deletion** (round-2 storage review). Rejected by
  the owner. A writer can reuse an old leaf it finds present, and age says
  nothing about that.
- **`LeafEntry.state_seq` and `state_epoch`, copied into `from_seq`.** Rejected
  by the owner. It adds two leaf fields to serve a stage-3 identifier that
  replay can compute.
- **`sealed_at` and `sealed_by` on new-entry items.** Not taken. H15 asserts no
  generation instead, and stage 3 can add the fields against a real consumer.
- **An Inventory major for opted-in roots** (revision 3's fallback). Rejected
  by the owner (H20). An old reader skips the undecodable root and serves the
  last 1.x root as the head from the opt-in on.
- **A lock-out through an undecodable `CURRENT`.** Not taken. It would make
  old readers fail closed, and it stops every old pod at the opt-in.
- **Sharing Inventory 1.1 with sdmxlib#348.** Rejected by the owner (H19). It
  ties stage 1 to Phase 4's specification PR, whose scope is still open
  (plan line 326).
- **A reentrant local lock.** Not taken. Ordering `prune`'s `retire` commit
  before expiry keeps the lock simple.
- **A conditional lock object with a TTL for S3 and GCS.** Deferred (H21).
- **Object lock (Azure immutable blob storage, S3 Object Lock) on
  `history/`.** Compatible, and it makes deleting or overwriting history
  impossible for every identity, the release job's included. The
  specification recommends it for servers. Local catalogs have no
  equivalent, so it stays optional.
- **Signed roots.** Signing the chain's newest root and segment hashes would
  anchor them outside the catalog. Left for a later design, with RFC 9162.
- **A state as a PROV attribute or a qualified generation of the edition.**
  Rejected. An entity's attributes describe its fixed aspects (PROV-DM §5.1.1;
  verify before citing), and an edition is one entity.
- **The state as the leaf entry within a version.** Rejected. Leaves expire,
  and a change list holds only the changed entries.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Expiry deletes a leaf a new root names | Writer exclusion (H12): the local lock in `try_commit` from its first leaf check to `CURRENT`; on Azure the `HISTORY` lease, `If-Match` leaf deletes and unconditional leaf Puts. `verify-catalog` checks every retained root's leaves. |
| A paused lease holder deletes after its lease lapsed | Renewal every 20 s with a 40 s margin before each destructive call; `HISTORY` writes carry the lease ID; leaf deletes carry `If-Match`. |
| A hung holder blocks an emergency withdraw | The 30-minute cap on a run's lease, and the break runbook. |
| Expiry deletes a root no segment records | Step 5 and the crash rule delete a root only when its bytes match a line in a segment the crash rule covers; any other root is reported and kept. |
| An old pod without `CURRENT` takes a checkpoint for the head | The stage-1 reader fallback, the sdmxlib-rest floor, the rollback-window gate and the image runbook (H20). The pod check on every run detects an old or unknown pod and skips expiry. |
| A lagging `CURRENT` names an expired root | Step 0 advances `CURRENT`, and step 1 never takes a root at or above `CURRENT.seq`. |
| An old writer races the opt-in | The first expiry runs in a later call, and expiry stops at a root above `since_seq` that lacks the history fields. |
| A stale writer recreates an expired `seq` | A writer refuses a base at or below `expired_through`, checked under the lock, and expiry keeps any root that matches no segment line. |
| A restore reuses a `seq` | Every restore on an opted-in catalog bumps the epoch and writes the roots it discards into a `restore` segment; `verify-catalog` keys by `(restore_epoch, seq)`. |
| The release job's identity overwrites a segment | Without object lock the identity can overwrite `history/`, and only the segment chain and an external anchor detect it. The specification recommends object lock on servers, and the release job publishes the newest root and segment hashes outside the catalog. |
| Step 6 reads every retained root | The release job's leaf-set cache; the first run reads 1.7 to 4.7 GB on the statcatlib#126 corpus, later runs only the new roots. |
| One fast clock pins `created_at` | A writer refuses a base more than 5 minutes ahead of its clock; servers use the storage clock. |
| A full republish makes one root large | 6.5 MB of change list once per republish, beside a 1.6 MB root. |

## Cross-repo contract

- **sdmxlib** owns:
  - the history fields `previous_root_sha256` and `changes`, defined by their
    presence and numbered Inventory 1.2 where a number is needed; the item
    fields; the writer rules; and the `reinstate` kind, in Inventory 1.2
    (H24);
  - `catalog.json` 2.0 with `history`, a reader decode that accepts majors 1
    and 2, and a writer decode that accepts 2.x only for a writer that
    declares stage-2 support;
  - `inventory/HISTORY` 1.0 with `cleaned_through`, and the segment format
    1.0 with `kind` and `unread`, the segment naming, line bytes and header
    plan;
  - the catalog lock: `<catalog>/LOCK` with an OS advisory lock, never
    deleted; on Azure the `HISTORY` lease's duration, renewal margin, cap and
    `If-Match` leaf deletes;
  - the expiry steps, crash rules and restore order;
  - the JSON Schemas for all of these;
  - the reader fallback;
  - `verify-catalog`'s chain, segment and checkpoint checks, through the
    conformance suite;
  - in stage 3, the `stc:` vocabulary and the normative mapping.
- **statcatlib** writes the history fields in every root, opted in or not. In
  stage 2 it adds the catalog lock in `try_commit`, opt-in, segments, expiry
  in `CatalogAdmin.prune` and, on Azure, in the release job (Phase 5) with the
  `HISTORY` lease, the expiry gates and the leaf-set cache, and restores that
  bump the epoch.
- **sdmxlib-rest** raises its sdmxlib floor to the stage-1 release, reports
  `sdmxlib_version` in every `GET /` payload, and writes nothing.
- **The hub** reserves `https://statcat-suite.github.io/ns/inventory#` and
  `/id/` in stage 3, and publishes the vocabulary file sdmxlib supplies.

## Staging

1. **Change lists and the reader.** The specification PR (sdmxlib#361) with
   every format in this design. The next sdmxlib release ships the history
   fields, the writer rules, the reader fallback and the decodes for
   `catalog.json` 2.0 and `HISTORY`. The next statcatlib release writes the
   history fields. sdmxlib-rest raises its floor and reports
   `sdmxlib_version`. The operator records the last pod image built before
   stage 1, whose rollback window sets `expiry_not_before`. Nothing expires
   yet, and none of this waits for Phase 5 or sdmxlib#348.
2. **Expiry.** The catalog lock, opt-in, segments, expiry, restores and the
   `verify-catalog` checks. Local expiry through `prune` ships when it is
   ready. Server expiry ships with the Phase 5 release job, on Azure only, and
   its first run waits for `expiry_not_before`.
3. **Export.** The normative PROV-O mapping, the vocabulary, golden files and
   the exporter, in statcat-serve.

## Handoff

### sdmxlib (StatCat-Suite/sdmxlib#361)

Specification sections:

- §6.1 (`catalog.json` 2.0, `history`, the opt-in rewrite under the lock, on
  an opted-in catalog every restore bumps the epoch and an epoch-keeping
  rollback is unsupported, a live-only export takes a new `catalog_id`);
- §6.2 (the root history fields defined by presence, Inventory 1.2, the
  `reinstate` kind in Inventory 1.2, the fold records `seal`);
- §6.3 (the change item and entry item);
- §6.6 (the reader fallback, the writer rules with the stale-base refusal
  under the lock, and the escape-route amendment);
- a new §6.9 (segments with `kind`, `HISTORY` with `cleaned_through`, the
  catalog lock and the lease, expiry steps 0 to 8, crash rules, checkpoints,
  the restore order);
- §9.2 (an opted-in catalog's pods never roll back to a pre-stage-1 image;
  `expiry_not_before`);
- §10.1 (the release job's delete on expired `inventory/` objects, the
  `history/` row, and the pods' read of `catalog.json` and
  `inventory/HISTORY` for the fallback);
- §10.3 (backup order; restores only add segments under `history/`);
- §11.4 (GC stops at `expired_through` and fails closed on a missing root);
- §6.5 (the release job reads each incoming edition's manifest to verify
  `manifest_sha256`, and reads every other edition's artefact records from
  its leaf's filled `artefacts`);
- §11.2 step 2 (the fold skips a registration whose edition the Inventory
  already records) and §11.4 (GC deletes folded `pending/` registrations
  after the retention window);
- §11.6 (W, K and the staleness alert).

Acceptance:

- schemas for a root with the history fields, `catalog.json` 2.0, `HISTORY`,
  the segment header and the segment line, each with valid and invalid
  examples;
- conformance cases:
  - a correction built from an older version links root `seq - 1` and diffs
    against it;
  - a lost race rebuilds its change list;
  - `created_at` stays monotone across an epoch change, and a base more than
    5 minutes ahead is refused;
  - an entry that changes and keeps its state, a retire, a reinstate;
  - the reader with `CURRENT` missing on a 1.x catalog, on a 2.x catalog,
    and on a 2.x catalog without `HISTORY` (fails closed);
  - a reader holding a root at or below `expired_through`;
  - the reader takes the epoch from `HISTORY` or `catalog.json`;
  - a 2.x catalog refused by a writer without stage-2 support;
  - opt-in refused when a root without the history fields follows one with
    them;
  - a writer refuses a base at or below `expired_through`, read after the
    lock;
  - `CURRENT` lagging by more than K: step 0 advances it and step 1 takes no
    root at or above it;
  - expiry stops at a root above `since_seq` that lacks the history fields;
  - an expiry crash after each step, in a run of several segments, with
    linked orphans adopted, an unlinked orphan left, and `cleaned_through`
    limiting the crash rule;
  - a root below `expired_through` with no matching line, kept;
  - a restore that bumps the epoch writes a `restore` segment, and a crash
    after its `HISTORY` write fails closed until root S + 1 exists;
  - `verify-catalog` keys by `(restore_epoch, seq)` across a restore;
  - an edited segment line and a deleted root, each detected;
- `just ci`.

### statcatlib (StatCat-Suite/statcatlib#125)

- Stage 1: the history fields in `InventoryWriter` for every version, the
  `created_at` rules and the forward-skew refusal.
- Stage 2:
    - the catalog lock on `<catalog>/LOCK` (`fcntl.flock`, `LockFileEx` on
      Windows), taken in `try_commit`; `prune` commits `retire` before it
      takes the lock for expiry;
    - the stale-base refusal inside `try_commit`, after the lock;
    - opt-in through `CatalogAdmin`, which writes `HISTORY` and then
      `catalog.json` 2.0, refused on a blob store other than Azure;
    - expiry with step 0, its dry run, header plan, `cleaned_through` and
      deletion log, in `prune`;
    - with Phase 5, expiry in the release job: the `HISTORY` lease (60 s,
      renewed every 20 s, 30-minute cap, break runbook), the expiry gates
      (`expiry_not_before` and the pod check on every run), the step-6
      leaf-set cache, `If-Match` leaf deletes, and the blob writer's
      unconditional leaf Put (amending plan line 330);
    - restores that bump the epoch, in the order of [Restores](#restores);
    - `verify-catalog` and `doctor` reporting.

Acceptance:

- "What was live at time T" gives the same answer after expiry as from the
  full roots before it.
- Expiry never deletes a leaf a retained root names, checked by an independent
  reachability computation.
- A seal that races `prune` on a local catalog either commits before expiry
  chooses or waits for it, and every leaf its root names exists.
- A process killed while it holds the local lock leaves `LOCK` in place, and
  the next commit proceeds.
- `prune` with expiry commits its `retire` version and expires in one call
  without deadlock.
- A second release-job run fails to take the `HISTORY` lease and writes
  nothing.
- A failed lease renewal stops expiry before its next destructive call.
- A leaf rewritten after step 6's final check survives the `If-Match`
  delete.
- The pod check with an unreachable pod or a missing `sdmxlib_version` skips
  expiry, and the release step still runs.
- `just ci`.

### sdmxlib-rest

An issue once sdmxlib releases stage 1: raise the sdmxlib floor to that
release; add `sdmxlib_version`, from `importlib.metadata.version("sdmxlib")`,
to the `GET /` payload in both branches (`app.py:233-241`), so a consumer's
`root_payload` keeps it. sdmxlib-rest reads no Inventory object, so the
reader fallback is tested in sdmxlib (StatCat-Suite/sdmxlib#361).

## Review response

### Round 1

| Finding | Change in revision 2 |
| --- | --- |
| B1 orphan record race | H1: no separate record. The root is the record. |
| B2 restore reuses `seq` | Segments keyed by epoch; `previous_root_sha256` after a restore; epoch in IRIs. |
| B3 reader stops at gaps | Floor in `HISTORY`; reader change. Revision 2 also claimed `catalog.json` 2.0 locks out old readers, which round 2 showed false (round-2 Blocker 5). |
| B4 expiry races writers on leaves | The single writer on a server; a lock locally; step 6's re-read and recreate. Revision 3 replaces these (round-2 Blocker 6). |
| B5 escape route | H9 and its section; §6.6 amendment. |
| B6 untestable normative mapping | H8: informative now. |
| B7 no migration | H6: opt-in through `catalog.json` 2.0, `since_seq`. |
| Major 8, 9, 11, 13 (PROV) | H7, tombstones in the change list, times, the reason, Goal 4 rewritten. |
| Major 10 qualified association | Mapping table. |
| Major 12 missing data | `entry` holds the `LeafEntry`; `catalog_id`; `from_seq`. Revision 3 trims `entry` and drops `from_seq` and the root's `catalog_id`. |
| Major 14 embargo boundary | Embargo and access section. |
| Major 15 delete rights on history | H2: no deletes under `history/`; object lock recommended. |
| Major 16 retention window | Expiry step 1: K, the age rule and W's bounds. |
| Major 17 hash input | H3: stored bytes. |
| Major 18 segment discovery | `HISTORY` and the `previous_segment` links. |
| Major 19 expiry order and crashes | Expiry steps and the crash rules. |
| Major 20 checkpoint clock | H4. |
| Major 21 under-specified fields, sizes | Field tables; size of a full republish. |
| Major 22 citations | P7 quoted with "until Phase 4"; the Phase 9 restore tooling named as planned. |
| Major 23 backups, layout, handoff | Layout, §10.3, a Handoff with acceptance for each repository. |
| Major 24 staging and alternatives | Staging; object lock and signed roots added. |
| Nits 25 to 34 | Terms section, style, PREMIS crosswalk corrected, `prov:Attribute` dropped, expiry records `expired_at` and `actor`, size range corrected, GH-19 form, the Evidence line. |

### Round 2

| Finding | Change in revision 3 |
| --- | --- |
| Blocker 1 chain against `previous_inventory` | H10: `previous_root_sha256`, `changes` and the `created_at` rule follow root `seq - 1`; `previous_inventory` is "built from"; a correction conformance case. |
| Blocker 2 `from_seq` | H11: dropped; the exporter numbers intervals by replay; "most recent earlier item" rule; writer rules corrected. |
| Blocker 3 seal fact | H15: the export asserts no generation time or producer for an edition; Goal 4 says so. |
| Blocker 4 crash rule deletes unrecorded roots | Steps 1 and 5 and the crash rule: a contiguous run never below `since_seq`; a root is deleted only after its bytes match a linked line; `expired_through` redefined. |
| Blocker 5 lock-out claim | Catalogs that expire: 2.0 locks out writers only; H13: reader fallback in stage 1, the first-expiry pod check, root major as fallback. Revision 4 replaces the last two (H20). |
| Blocker 6 leaf deletion lock | H12: catalog lock for `commit` and `prune`, release-job lease on `HISTORY`; step 6 without recreate; planned deletions in the segment header; Handoff and conformance case. |
| Major 1 epochs | `HISTORY.restore_epoch`; one segment per epoch; one global chain; Restores section (every restore bumps the epoch and saves discarded roots); reader epoch from `HISTORY` or `catalog.json`; export `catalog_id` rule; fixed IRI base moved to stage-3 requirements. |
| Major 2 floor cases | Renamed `expired_through`; the reader section gives when it reads `HISTORY`, the lower bound, the held-root rule and fail-closed cases; opt-in writes `HISTORY` first. |
| Major 3 segment naming and crash | UUIDv7 suffix, 12-digit padding, LIST and adopt in step 3, line bytes defined, local `HISTORY` under the lock. |
| Major 4 segment lines bound only by the chain | Goal 2 takes a trusted segment hash; step 3 checks `root_sha256`; object lock recommended and the risk row says what holds without it. |
| Major 5 clocks | Storage clock for servers and expiry; 5-minute forward-skew refusal; exact checkpoint rule in Terms, recomputed by `verify-catalog`. |
| Major 6 backup order | Restores section gives the §10.3 order. |
| Major 7 W bounds and GC | Bounds: W ≥ GC window + 1 day in storage time; backup bound dropped as implied; staleness alert below W; GC stops at `expired_through` and fails closed. |
| Major 8 rebuild from change lists | Non-goal; §6.7 dropped from the Handoff. |
| Major 9 expired names reopened | Writer refuses a base at or below `expired_through`; expiry keeps unmatched roots. |
| Major 10 `entry` size | H14: seven fields; the Sizes table gives figures with `LeafEntry.artefacts` empty and filled. The no-home index was then open; revision 4 records the owner's choice to fill `artefacts`. `to` is kept, since it carries `tombstone` and `null` and costs about 15 bytes. |
| Major 11 PROV section is stage-3 material | Section cut to data requirements and a field-to-term table; vocabulary, IRIs and example moved to stage 3; Turtle link withdrawn; PREMIS crosswalk dropped; namespace reservation moved to stage 3. `stc:Search` drops with the term list; the owner's Phase 7 `search` kind (GH-19) arrives in its own minor. |
| Major 12 agent, leaf and membership rules | Qualified delegation with `prov:hadActivity`; no generation or revision on leaf bytes; changed members on every export; states `prov:specializationOf` the edition. |
| Major 13 staging | Stage 1 holds the reader fallback and sdmxlib-rest's floor, and waits for no phase. |
| Nit 1 row reads backwards | The entry-item row puts the state entity first. |
| Nit 2 `reinstate` kind, fold kind | `reinstate` kind added; the fold records `seal`. The kind-to-class rule moves to stage 3. |
| Nit 3 `retired` as a state | H18: `tombstone` marker; §6.4 unchanged. |
| Nit 4 times | State entities take `created_at`; activities have no start or end time. |
| Nit 5 IRI minting | Stage-3 requirements list; personal data in `actor` noted under Embargo and access. |
| Nit 6 empty change lists, extension digests | Segment lines keep `extensions` whole; `embargo` and `extensions` are version attributes in the table. |
| Nit 7 "never invalidated" | Phrased as an export rule (H15); expiry activity row added. |
| Nit 8 H7 and alternatives wording | PROV-CONSTRAINTS constraint names given, marked verify before citing; PROV-DM §5.1.1 wording. |
| Nit 9 `since_seq` | Defined from the lowest `seq` with the history fields; opt-in refuses otherwise; §6.1 amended for the rewrite. |
| Nit 10 step 2 cost, log order, segment size | Step 2 verifies the candidates and boundary links only; the header is the plan; segments split at 1,000 lines. |
| Nit 11 checkpoints, tombstone ageing | Checkpoints are audit records; dropping a tombstone writes `to: null`. |
| Nit 12 simplifications | Checkpoint rule has three kinds with version 1 inside the epoch rule; `catalog_id` out of the root (H16); `verify-catalog` has three checks; "adds two root fields". |
| Nit 13 embargo filter | Embargo and access says a live-only export drops the embargoed state's end. |
| Nit 14 DCAT join, PREMIS | DCAT product IRI and `owl:AnnotationProperty` in stage-3 requirements; PREMIS crosswalk dropped. |

### Round 3

| Finding | Change in revision 4 |
| --- | --- |
| Blocker 1 root-major fallback does not fail closed | H20: the root major is removed from the reader section, H13, Alternatives and Risks. [Expiry gates](#expiry-gates): the §9.2 rollback window gates every expiry, and the image runbook forbids rolling back to a pre-stage-1 image. |
| Major 1 pod check runs once | The pod check runs on every expiry run, lists every serving Deployment's pods through the Kubernetes API with not-Ready pods, reads `sdmxlib_version` from `importlib.metadata`, added in both `GET /` branches, and counts unreachable or unknown as failure. Jobs fall under the time gate. |
| Major 2 lagging `CURRENT` | Step 0 advances `CURRENT`; step 1 takes no root at or above `CURRENT.seq`; conformance case. |
| Major 3 local lock | `flock` or `LockFileEx` on `<catalog>/LOCK`, never deleted; taken in `try_commit`; stale-base refusal after the lock; `prune` commits `retire` before taking the lock; opt-in and restores take it. |
| Major 4 lease | 60 s lease, 20 s renewal, 40 s margin before each destructive call, 30-minute cap, break runbook; `If-Match` leaf deletes with unconditional leaf Puts; server expiry Azure-only (H21). |
| Major 5 multi-segment crash recovery | Segments written in chain order; orphan adoption checks the link to `newest_segment`, the lowest candidate and the candidate range; `HISTORY.cleaned_through` limits the crash rule. |
| Major 6 step 6 retained set and cost | Step 6 LISTs and reads every retained root; the release job caches leaf sets by path and ETag; 1.7 to 4.7 GB per run without the cache, stated. |
| Major 7 restores | `expired_through` defined on the head chain across epochs; `verify-catalog` keys by `(restore_epoch, seq)`; segment `kind`; `unread` for a failover; epoch bump required on opted-in catalogs (H22); restore order given. |
| Major 8 `since_seq` tied to 1.1 | H19: every rule tests for the history fields; Inventory 1.2 where a number is needed; expiry stops at a root above `since_seq` without them. |
| Nit 1 `catalog.json` readers | Catalogs that expire states that no serving reader reads `catalog.json` before stage 1. |
| Nit 2 §10.1 row for the fallback | Reader section and the §10.1 Handoff item add the pods' read of `catalog.json` and `HISTORY`. |
| Nit 3 lock location | `<catalog>/LOCK`. |
| Nit 4 segment size | Split at 1,000 lines or 64 MiB. |
| Nit 5 adoption range | Step 3 adopts only orphans whose lines lie within the current candidates. |
| Nit 6 opt-in race | The first expiry runs in a later call than the opt-in; the stop rule from Major 8. |
| Nit 7 orphan leaves | The crash rules state that they leak, safely and bounded. |
| Nit 8 step 1 cost | Ranged GET of the first 1 KiB for `created_at`. |
| Nit 9 verify before citing | Kubernetes not-Ready pods, Azure lease limits and Delete Blob `If-Match` added. |
| Question (a) | H19. |
| Question (b) | H20. |

## Questions for review

None are open. The owner answered revision 4's two questions in H23 and H24.

## Verify before citing

- PROV-CONSTRAINTS: the names of the unique-generation and
  unique-invalidation constraints.
- PROV-O: `prov:qualifiedDelegation` and `prov:hadActivity` on
  `prov:Delegation`.
- PROV-DM §5.1.1: the "fixed aspects" wording.
- RFC 6920 §3 (`ni:///sha-256;` with unpadded base64url) and RFC 9562
  (lowercase `urn:uuid`).
- Turtle 1.1: `PN_LOCAL` needs `\/` for a slash and excludes U+2026.
- Azure Blob Storage: lease durations (15 to 60 s, or infinite), renewal and
  break; writes to a leased blob require the lease ID; Delete Blob honours
  `If-Match`; object lock for `history/`.
- Kubernetes: a headless Service's DNS omits not-Ready pods unless
  `publishNotReadyAddresses` is set; whether `concurrencyPolicy: Forbid`
  covers a manually created Job (the lease makes the design independent of
  the answer).
- `fcntl.flock` and `LockFileEx` release on process exit on every supported
  platform.
