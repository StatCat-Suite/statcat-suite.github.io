# Moving a service to products and editions

This guide is for teams that run their own SDMX-REST endpoint over StatCat
data, on Kubernetes with the data in Azure Data Lake Storage (ADLS Gen2). It
covers the move from single bundles to products, editions and the Inventory:
what to rebuild, how to publish to ADLS, and how a serving pod finds, pulls
and opens the live edition of each product.

Every step below ran end to end on 2026-11-13 against a real storage account,
with the packages installed from PyPI into a fresh environment:

| Package | Version | Cap in your `pyproject.toml` |
| --- | --- | --- |
| sdmxlib | 0.88.0 | `sdmxlib>=0.88,<0.89` |
| statcatlib | 0.19.0 | `statcatlib[blob]>=0.19,<0.20` |
| sdmxlib-rest | 0.10.3 | `sdmxlib-rest>=0.10.3,<0.11` |

Every suite library is pre-1.0, so cap each one below its next minor
([conventions](conventions.md#dependencies)), and raise a cap in the pull
request that adopts the new minor. Install with `uv add` (or `pip install`).

## What changes

| Before | Now |
| --- | --- |
| One bundle directory per dataset, served as it is | A **product** is a directory of sealed **editions** over a shared `data/` directory. Each edition is immutable and named by its UUIDv7 `edition_id`. |
| The deployment decides which bundle to serve | The **Inventory** records which edition of each product is `live`, `embargoed`, `superseded` or `withdrawn`, in a chain of immutable versions. |
| Bundles copied to wherever they are served | Editions are uploaded once to ADLS. A pod pulls the catalog files of the live edition and reads the observations from ADLS. |
| A release is a copy at the right time | `statcat release` makes embargoed editions live in one Inventory version at their `release_at`, after an access check. |

The [architecture page](architecture.md) describes the formats. Read it once
before you start.

## 1. Rebuild every bundle

sdmxlib 0.80 and later read edition manifest format 3.0 only, and refuse every
directory sdmxlib 0.79 or earlier wrote with `ManifestError`. Rebuild each
dataset as a product.

Seal with statcatlib 0.17 or later. The release job's fold reads two keys from
the manifest's `statcat` section, `kind` and `lifecycle`, and refuses an
edition that lacks them:

- a section with no product `kind` is refused with the rule `kind`;
- a new product whose section names no `lifecycle` is refused with the rule
  `lifecycle`, so an edition sealed with statcatlib 0.16 or earlier cannot be
  released on a server.

A producer fills a product's working copy and seals it through statcatlib's
`Catalog` (`Catalog.create`, `catalog.product(id).working_copy()`, `seal()`).
A seal writes the edition directory with `manifest.json`, `metadata.duckdb`,
`tables.ducklake` and the Parquet files under the product's `data/`. A second
edition of a product is sealed from a working copy of the live one, and its
manifest names the live edition as `previous`.

Structure products hold one agency's full codelists, concept schemes,
category schemes and hierarchies, and data products cut their partial
codelists from them. A structure product is sealed from
`Product.working_copy(kind="structure")`. Seal the structure products a data
product depends on before it, and upload them with it. statcatlib's [catalog
format, §3.2](https://statcat-suite.github.io/statcatlib/catalog-format/#32-structure-products-and-the-publish-check)
describes them.

## 2. Publish to ADLS

### Create the catalog once

```bash
export AZURE_STORAGE_ACCOUNT_NAME=<account>
statcat admin create az://<container>/<prefix>
```

It writes `catalog.json` with a new `catalog_id` and prints the id on standard
output. It refuses a prefix that already holds a catalog, naming its id, and a
prefix that holds catalog objects with no `catalog.json`. A new catalog's
embargo is off. Run `statcat admin embargo <url> on` after it to hold every
automatic release from the start.

### Upload each edition

```bash
statcat upload <product>/<edition_id> az://<container>/<prefix> --release-at 2026-11-20T13:30:00Z
```

The command copies only the files the store lacks, checks every listed file
against the digest the store keeps, and registers the edition in `pending/`.
No reader sees it until the release job folds it. Omit `--release-at` for an
edition that only `statcat admin release` publishes.

The upload builds its credential with `DefaultAzureCredential`, which reads a
workload identity's `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and
`AZURE_FEDERATED_TOKEN_FILE`. It refuses to run when an account key, SAS,
endpoint override or emulator variable is set, in any letter case after
`AZURE_`. Check that the `oid` it prints is the identity you meant.

### Run the release job

```bash
statcat release az://<container>/<prefix> --config /etc/statcat/jobs.toml
```

One run folds `pending/` into `embargoed` entries, releases every entry whose
`release_at` has come, and retires old superseded and withdrawn entries. A
rerun against an unchanged catalog writes nothing. Schedule it at least twice
for each release time: a pre-flight run before it, which folds, and a run just
after it, which releases. A missed run is made up by the next.

The [jobs configuration](https://statcat-suite.github.io/statcatlib/api/jobs/)
holds the retention windows and the `[access]` block the release job requires.
Keep it in one ConfigMap shared by the release and GC jobs.

### The access check

Before it releases anything, the job lists who holds a role that reads the
container's blobs and compares each principal with the configuration's
allowlist. A principal off the list stops every automatic release, logs
`access.mismatch`, and names the principal; the fold and the retirement still
run. The test run showed this with a temporary reader role: the release was
skipped until the role was removed, and the next run released.

The release identity needs one custom role at the storage account, with two
actions and nothing else:

```json
{"Name": "statcat access check", "IsCustom": true,
 "Actions": ["Microsoft.Authorization/roleAssignments/read",
             "Microsoft.Authorization/roleDefinitions/read"],
 "NotActions": [], "DataActions": [], "NotDataActions": [],
 "AssignableScopes": ["/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>"]}
```

Put on the allowlist the object id of every identity that reads the
container: the publish job, the release job, the GC job, the serving pods and
any preview deployment. List one known role assignment above the account as
a sentinel, so a listing that misses inherited assignments fails closed.

### Identities

| Identity | Needs |
| --- | --- |
| Publish job (`statcat upload`) | Read and write under `products/` and `pending/` (Storage Blob Data Contributor) |
| Release job (`statcat release`, `statcat admin`) | Read and write on `catalog.json`, `inventory/` and `CURRENT`, read on `products/` and `pending/`, and the custom role above |
| GC job (`statcat gc`) | Read on `catalog.json`, `inventory/` and `CURRENT`; list, read and delete under `products/` and `pending/` (Storage Blob Data Contributor) |
| Serving pods | Read on the container (Storage Blob Data Reader) |

No identity holds an account key or a SAS.

### Operator commands

| Command | Does |
| --- | --- |
| `statcat admin editions <url> <product>` | Lists a product's editions in every state |
| `statcat admin cancel <url> <product> <edition> --reason …` | Withdraws an embargoed edition before its release |
| `statcat admin release <url> <product> <edition> --reason …` | Makes an embargoed edition live now |
| `statcat admin rollback <url> <product> --reason …` | Withdraws the live edition and makes the superseded one live again |
| `statcat admin embargo <url> on\|off --reason …` | Holds or resumes every automatic release |
| `statcat gc <url> --config … --dry-run` | Plans what GC would delete; drop `--dry-run` to delete |

Run them under the release identity and name yourself in `--reason`; the
Inventory version records it.

## 3. Serve from a pod

A pod serves the live edition of a product in four steps. sdmxlib-rest 0.10.3
serves one edition per process. Phase 6 of the sharded catalog builds
StatCat-Suite/statcat-serve, which routes many products across pods, so keep
the code below small and replace it when statcat-serve ships.

### Read the live view

```python
import obstore
from azure.identity import DefaultAzureCredential
from obstore.auth.azure import AzureCredentialProvider
from obstore.store import AzureStore
from sdmxlib.inventory import LiveInventory
from statcatlib import TokenIdentity

store = AzureStore(
    "<container>",
    prefix="<prefix>",
    account_name="<account>",
    credential_provider=TokenIdentity(AzureCredentialProvider(DefaultAzureCredential())),
)


def fetch(path: str) -> bytes | None:
    try:
        return bytes(obstore.get(store, path).bytes())
    except FileNotFoundError:
        return None


live = LiveInventory(fetch).refresh()
entry = live.head("<product>")  # edition_id, manifest_sha256, dataflows, pull_bytes, ...
```

`LiveInventory` holds only `live` entries, so nothing embargoed reaches a pod.
`head` raises `KeyError` for a product with no live edition, such as one whose
only edition was cancelled. A cold `refresh()` reads every leaf on 64 threads:
7,000 leaves took about 1 s from a machine in the account's region. Call
`refresh()` again to see a new Inventory version.

### Pull the required tier

```python
from pathlib import Path
from sdmxlib.edition import decode_manifest, edition_files

base = f"products/<product>/{entry.edition_id}"
raw = fetch(f"{base}/manifest.json")
manifest = decode_manifest(raw, f"az://<container>/<prefix>/{base}/manifest.json")
product_dir = Path("/var/cache/editions/<product>")
for name in edition_files(manifest, tiers=("required",)):
    target = product_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(fetch(f"products/<product>/{name}"))
(product_dir / entry.edition_id / "manifest.json").write_bytes(raw)
```

`edition_files` returns paths under the **product** directory, such as
`<edition_id>/metadata.duckdb`, so join them to the product, never to the
edition. The required tier is `metadata.duckdb` and `tables.ducklake`, about
19 MB for a small table. Write `manifest.json` last, so a crash mid-pull
leaves a directory that does not open. The Parquet files stay in ADLS.

### Open the edition with its data in ADLS

```python
import sdmxlib as sl

engine = sl.EditionEngine(
    secrets=[sl.StoreSecret("azure", provider="credential_chain", options={"account_name": "<account>"})]
)
registry = sl.LocalRegistry.edition(
    product_dir / entry.edition_id,
    remote=f"az://<container>/<prefix>/{base}/",
    engine=engine,
    manifest_sha256=entry.manifest_sha256,
)
```

- `remote` names the edition directory in ADLS, and DuckDB reads the Parquet
  files from there through the engine's secret.
- `manifest_sha256` makes the open refuse a directory whose manifest is not
  the one the Inventory records, with `ManifestError`. The test opened a
  superseded edition with the new edition's hash, and it was refused.
- The test ran DuckDB's `credential_chain` under a virtual machine's managed
  identity. Check that the chain picks up your pod's workload identity before
  you rely on it.
- One `EditionEngine` can hold many editions, sharing one buffer pool and
  `memory_limit`.

### Serve it with sdmxlib-rest

```python
from sdmxlib_rest.app import RestSettings, create_app, library_routers
from sdmxlib_rest.provider import OpenedCatalog
from sdmxlib_rest.runtime import CatalogRuntime


class LiveEditionProvider:
    def open(self) -> OpenedCatalog:
        registry = open_live_edition()  # the three steps above
        return OpenedCatalog(registry=registry, meta_conn=registry.connection, on_close=registry.close)


app = create_app(
    CatalogRuntime(LiveEditionProvider()),
    RestSettings(title="my-sdmx-api", version="1.0.0"),
    routers=[*library_routers(), data_router],
)
```

`library_routers()` serves `/structure`, `/metadata` and `/availability`.
The `/data` route is yours to write, from the helpers in `sdmxlib_rest.data`
([Writing a data route](https://statcat-suite.github.io/sdmxlib-rest/data-plane/)).
In the test, a route that resolved the dataflow, filtered on the key and
streamed the rows served 200 rows from ADLS in 0.16 s. Two details:

- `key_dimension_ids` includes `TIME_PERIOD`. A dotted SDMX key covers the
  other dimensions, so drop the time dimension before you split the key.
- Every cache and the ETag key on the manifest's `edition_id`, so a new live
  edition invalidates them by itself.

### Move to a new live edition

When `refresh()` shows a new `manifest_sha256` for a product, pull its
required tier, open it, and serve from it before you close the old registry.
In the test, a revised edition stayed invisible to pods while it was
embargoed, `/data` returned its rows once it was released, and a rollback
brought the old edition back for the next pod that read the Inventory.

## Checking an edition on open

`sdmxlib.edition.check_on_open(path, stamps=, remote=)` checks a pulled
edition against its manifest once and stamps the result, so a restart runs a
quick check. In sdmxlib 0.88 it reports each missing file outside `data/`, so a pod that
pulled the required tier alone gets a finding for each lazy-tier file, such as
the search index under `search/`.
sdmxlib's next release adds `tiers=`, so a pod holding the required tier
alone calls `check_on_open(..., tiers=("required",))` before it reports ready
(StatCat-Suite/sdmxlib#384). Until then, call it on editions whose lazy tier
is empty, or pull both local tiers.

## Pitfalls the test found

| Pitfall | Do this |
| --- | --- |
| `edition_files` paths are relative to the product directory | Join them to `products/<product>/`, never to the edition directory |
| `LiveInventory` takes a `Fetch`, a callable from a path to bytes or `None` | Wrap your store as shown above. statcatlib's `_ObjectOps` is private; do not import it |
| A missing blob raises `FileNotFoundError` from `obstore.get` | Return `None` for it in your `Fetch`, so the reader takes the absence as a fact |
| `head` raises `KeyError` for a product with nothing live | Answer 404 for that product's dataflows |
| An edition sealed with statcatlib 0.16 or earlier | The fold refuses it with `lifecycle`; seal it again with 0.17 or later |

## Checklist

1. Pin sdmxlib 0.88, statcatlib 0.19 and sdmxlib-rest 0.10.3 with the caps
   above.
2. Rebuild every dataset as a product with statcatlib 0.17 or later, with its
   structure products.
3. Create the custom access-check role and the four identities.
4. Write the jobs configuration with the allowlist and a sentinel.
5. `statcat admin create` the catalog.
6. Upload, then run `statcat release` before and after each release time.
7. In the pod, read the live view, pull the required tier, open with `remote=`
   and `manifest_sha256=`, and serve with your `/data` route.
8. Test a revision, a cancel and a rollback against a test prefix before you
   publish real data.

## What comes next

- **sdmxlib 0.89** ships `tiers=` on `check_edition` and `check_on_open`.
- **statcat-serve** (Phase 6) ships the router, pulls, pools, readiness and a
  result store keyed by fingerprint, over sdmxlib-rest. It replaces the pod
  code in section 3.
- **Inventory expiry** (statcatlib's history stage 2) is opt-in and is built
  after Phase 6 starts. A catalog that does not opt in keeps every Inventory
  version, and behaves as described here.
