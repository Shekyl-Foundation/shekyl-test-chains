# shekyl-test-chains

Forged test chains for [shekyl-core](https://github.com/Shekyl-Foundation/shekyl-core)'s CI, published as OCI artifacts on GHCR (`ghcr.io/shekyl-foundation/test-chains/<chain>`).

The design is shekyl-core's [`docs/design/CHAIN_FORGE.md`](https://github.com/Shekyl-Foundation/shekyl-core/blob/dev/docs/design/CHAIN_FORGE.md), §10.4 (rulings `CF-R6`, `CF-R11`, `CF-R14`).

## What is here, and what is not

- **The chains are forged, not captured.** Each is built by shekyl-core's chain forge from a plan committed in shekyl-core (`rust/shekyl-chain-forge/plans/<chain>.toml`). The plan's seed fixes every random draw, so forging the same commit twice gives the same bytes, byte for byte, on x86_64 and aarch64 alike.
- **A hosted chain is a cache.** The source of truth is a deterministic forging at a pinned shekyl-core commit. A deleted artifact is rebuilt from its commit, never lost, and an artifact that disagrees with its forging is wrong.
- **shekyl-core's pin file decides what CI accepts.** `rust/shekyl-chain-forge/chains/hosted.toml` pins each chain by its artifact's digest and each layer's SHA-256 and size. CI pulls by digest, never by tag, and refuses a copy that differs in one byte, whoever published it. Nothing in this repository can change a pin: a pin changes only in a reviewed shekyl-core pull request.
- **This repository keeps the publishing workflow, each published chain's manifest, and the release notes.** The plans and each chain's `blocks.txt` (one line per block: height, branch, block id) stay in shekyl-core beside the code that forges them.

## An artifact

| Layer | File | Media type |
| --- | --- | --- |
| the corpus: every block with its transaction bodies, and the competing blocks a reorg offers (corpus layout 5) | `corpus.e2` | `application/vnd.shekyl.corpus.v5` |
| the trace: each block's verdict and facts from a replay | `trace.e2` | `application/vnd.shekyl.trace.v1` |
| the manifest: the plan, the seed, the schedule, the events, and the corpus's and trace's SHA-256 (format 6) | `manifest.json` | `application/vnd.shekyl.manifest.v6+json` |

The artifact type is `application/vnd.shekyl.test-chain`. A layout or format change bumps the media type with its version constant, and the publish workflow takes each layer's media type from the forged commit (`forge --layers`), so an artifact always carries the types of the commit it was forged at. The manifest's annotations are the forged commit (`org.opencontainers.image.revision`), its committer time as the creation time (`org.opencontainers.image.created`, so publishing the same commit again gives the same digest), and this repository (`org.opencontainers.image.source`).

## Publishing

Only `.github/workflows/publish.yml` publishes, run by hand from `main` with three inputs: the chain, the shekyl-core commit to forge at, and the shekyl-core branch whose history holds that commit (`pin_ref`).

1. **Forge** (read-only token). It checks out shekyl-core at the commit, builds the forge there, forges the plan, and requires the forged `blocks.txt` to be the one committed at that commit. The forge at that commit names the layers and their media types (`forge --layers`).
2. **Publish** (the `publish` environment, which needs the Foundation's approval and deploys only from `main`). It packs the artifact offline and computes its digest. If shekyl-core's pin file on `pin_ref` already pins this chain at this commit, the digest must be the pinned one; otherwise nothing is pushed. Then it pushes, reads the digest back from the registry, and prints the pin entry for shekyl-core.

The shekyl-core pull request that adds or moves a pin carries that entry. Each published version's manifest goes into `chains/<chain>/<commit>/manifest.json` here, with a note in [`RELEASES.md`](RELEASES.md), in a pull request of its own.

## Fetching a chain

From a shekyl-core checkout:

```sh
python3 scripts/ci/fetch_test_chain.py <chain>
```

It installs the `oras` release pinned in `hosted.toml` (checking its archive's SHA-256), pulls the chain by digest, checks every layer against the pin, and only then puts it in `rust/shekyl-chain-forge/chains/<chain>/hosted/`. Without the network, forge the chain instead: the command is in the script's message.
