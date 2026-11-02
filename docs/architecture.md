# Architecture

## One store, two schema owners

Each edition of a product (below) keeps its metadata in one DuckDB file,
`metadata.duckdb`, holding two schemas:

- **`sdmx`**, owned by sdmxlib: the SDMX structural model. Codelists, data
  structure definitions, dataflows, constraints, hierarchies and reference
  metadata are rows keyed by URN.
- **`statcat`**, owned by statcatlib: the catalog star schema. Datasets,
  agents, themes, keywords, distributions and lineage, in DCAT-AP and
  StatDCAT-AP terms.

statcatlib copies nothing that sdmxlib already stores. A catalog dataset
built from SDMX carries `sdmx_dataflow_urn`, a foreign key into
`sdmx.dataflow`, and structural queries ("datasets with a `GEO` code under
Ontario") are SQL joins from `statcat.dataset` into sdmxlib's tables. Both
libraries share one connection, so those joins need no ATTACH.

Observations live beside the store, in a DuckLake catalog (`tables.ducklake`)
over Parquet files. statcatlib's search index, when built, is a LanceDB
directory (`search/`) with one table per language, each stemmed for that
language. [Domain model](domain-model.md) describes what the two schemas
hold, and [Storage and deployment](storage.md) how the files are laid out
and served.

## Products, editions and the Inventory

A **catalog** is a directory of **products**. A product is the unit of
publication: a set of dataflows released together, with their structures,
observations, catalog records and search index. Each release of a product
seals a new **edition**, a directory named by its **edition id**, a UUIDv7.
A sealed edition is never rewritten; a change is a new edition. The
**Inventory** records every product's editions and which one is live:

```text
<catalog>/
  catalog.json                 the catalog's id and restore epoch
  CURRENT                      names the newest Inventory version, as a hint
  inventory/<seq>.json         one root per Inventory version
  inventory/leaves/<sha256>.json   one leaf per product, named by its hash
  products/<product_id>/
    data/                      Parquet data files, shared by every edition of the product
    <edition_id>/
      metadata.duckdb          the sdmx and statcat schemas
      tables.ducklake          the DuckLake catalog for observations, over ../data/
      search/                  statcatlib's search index
      manifest.json            the manifest (format 3.0), written last
```

Each project owns one part of the contract:

| Part | Owner | Specification |
| --- | --- | --- |
| Edition layout, `manifest.json`, overlays, checks | sdmxlib | [The edition format](https://statcat-suite.github.io/sdmxlib/edition/) |
| Inventory documents (`catalog.json`, `CURRENT`, roots, leaves), their state rules and reader | sdmxlib | [Sharded catalog spec §6](https://statcat-suite.github.io/sdmxlib/design/sharded-bundle-catalog/#6-the-inventory-format-10) |
| The Inventory writer, the manifest's `statcat` section, the root's `extensions.statcat` catalog description, the `statcat` schema, `search/` | statcatlib | [Catalog format](https://statcat-suite.github.io/statcatlib/catalog-format/) |
| Serving an edition over SDMX-REST | sdmxlib-rest | [Serving an edition](https://statcat-suite.github.io/sdmxlib-rest/serving/) |

The manifest records the edition id, the `previous` edition it extends, and
the size and SHA-256 of every file, data files included. Caches and HTTP
`ETag`s key on the edition id. Each Inventory version is an immutable root
naming one leaf per product, and a leaf gives each edition one of four
states: `embargoed`, `live`, `superseded` or `withdrawn`. A release, a
rollback or a change of embargo writes one new Inventory version.

## Lifecycle

```mermaid
graph LR
    I[ingest into a working copy<br/>statcatlib + sdmxlib] --> S[seal<br/>statcatlib + sdmxlib]
    S --> K[check<br/>sdmxlib + statcatlib]
    K --> R[release, roll back<br/>statcatlib]
    R --> V[serve the live edition<br/>sdmxlib-rest]
```

1. **Ingest.** `Catalog.create(path)` creates a catalog, and
   `cat.product(id).working_copy()` starts the product's one unsealed
   edition. statcatlib's `ingest_sdmx` has sdmxlib write the structures into
   its `sdmx` schema, then writes one catalog dataset per dataflow. Other
   sources, such as CKAN portals, write catalog records directly.
2. **Seal.** `WorkingCopy.seal()` rebuilds the search index, has sdmxlib's
   `seal` write the manifest with statcatlib's `statcat` section, and records
   the edition in a new Inventory version: `live`, or `embargoed` while the
   catalog's embargo is on.
3. **Check.** `statcat verify-catalog` checks the Inventory and every edition
   it records. `sdmxlib.edition.check_edition` checks one edition directory,
   running statcatlib's `check_catalog` as its `statcat` extension. Run the
   checks where an edition is built or received, never on the serving path.
4. **Release and roll back.** statcatlib's `CatalogAdmin` releases or cancels
   an embargoed edition, rolls a product back to the edition it superseded,
   records the catalog's description and prunes old editions. Each change
   writes one Inventory version.
5. **Serve.** sdmxlib-rest serves a registry opened over one edition with
   `LocalRegistry.edition(path)`, which opens it read-only. The deployment
   reads the Inventory to choose the live edition and passes its directory.
   statcatlib's `Catalog.open(path)` reads the live editions the same way.

statcatlib's [Upgrading](https://statcat-suite.github.io/statcatlib/upgrading/)
page maps each name from the 0.11 catalog and the sdmxlib 0.72 bundle to its
replacement.

## Version checks

Each format an edition or the Inventory holds records its version, and a
reader that meets a version it does not read refuses the document instead of
misreading it. The versions below are those of sdmxlib 0.81.0, statcatlib
0.12.0 and sdmxlib-rest 0.9.0:

| Recorded in | Version of | At | Refused by |
| --- | --- | --- | --- |
| `manifest.json`'s `format_version` | sdmxlib's edition manifest | `"3.0"` | sdmxlib, which reads any `3.x` (`ManifestError`) |
| `sdmx._meta` and the manifest's `schema_version` | sdmxlib's store schema | `"2.52"` | sdmxlib (`StoreSchemaError`), and through it statcatlib's `Product.view()` |
| `catalog.json`'s `format_version` | sdmxlib's catalog document | `"1.0"` | sdmxlib's Inventory reader, which reads any `1.x` (`InventoryError`) |
| Each Inventory root's and leaf's `format_version` | sdmxlib's Inventory format | `"1.0"` | sdmxlib's Inventory reader, which reads any `1.x` (`InventoryError`) |
| The manifest's `extensions.statcat.format` | statcatlib's `statcat` section | `3` | statcatlib's `check_catalog` |
| `statcat._meta` | statcatlib's catalog schema | `"2.2"` | statcatlib's `Product.view()` and `Product.working_copy()` |
| `search/index.json`'s `version` | statcatlib's search index manifest | `3` | statcatlib's `Product.view()` and `Product.working_copy()` |

A minor version of the manifest or the Inventory format only adds optional
fields. Any other change to these versions means sealing new editions at the
new version, and deploying the new library to every reader before it serves
one. sdmxlib's
[sharded catalog spec §9.2](https://statcat-suite.github.io/sdmxlib/design/sharded-bundle-catalog/#92-rollout-procedure-for-a-schema-bump)
gives the rollout for a store schema change.
