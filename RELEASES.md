# Release notes

One entry per published chain version, newest first: the chain, the shekyl-core commit it was forged at, the artifact's digest, what the chain is for, and what moved it if it replaced an earlier version.

## shard-fill at shekyl-core `7e1f143424`

- **Digest:** `sha256:568aca6c0776228da682b71d5766262208180ad18b0a9b24a0f2e82f9b01a300`, published by the publish workflow's run 44857446184 (2026-11-21), forged at `7e1f143424e17151de3c48ea6b682c812ffa4324` (shekyl-core #1491, `CF-3`), pinned there.
- **Manifest:** [`chains/shard-fill/7e1f143424e17151de3c48ea6b682c812ffa4324/manifest.json`](chains/shard-fill/7e1f143424e17151de3c48ea6b682c812ffa4324/manifest.json) (SHA-256 `6b94820a…b888ab`, the pinned layer).
- **For:** three shards closed by real spends, at regtest's identity and difficulty 1: the chain the ingest's scenario fills and the chain store's prune and slash tests build on.
- **Moved by:** corpus layout 5 (`CF-3`). The corpus is written at the new layout, under `application/vnd.shekyl.corpus.v5`, the layers named by that commit's `forge --layers`. The blocks are the earlier version's (`blocks.txt` byte-identical) and so is the trace (`5879def7…`); only the corpus and the manifest moved.

## shard-fill at shekyl-core `8ecd609385`

- **Digest:** `sha256:1cd48e4d42bb99fffcf7cfba79385c19a9157025bc04c2f60ff7c0687f0c1296`, forged at `8ecd6093859c424ef7d1858dc894eed345009260` and published twice from that commit, by runs 44452616267 and, after the package was deleted, 44533937333 (2026-11-19): one digest both times. The chain landed in shekyl-core #1432 and its pin in #1464 (`CF-4a`).
- **Manifest:** [`chains/shard-fill/8ecd6093859c424ef7d1858dc894eed345009260/manifest.json`](chains/shard-fill/8ecd6093859c424ef7d1858dc894eed345009260/manifest.json) (SHA-256 `82aee296…bf80`, the pinned layer).
- **For:** as above, at corpus layout 4.
- **Replaced:** no earlier published version. It replaced the captured `shard-fill.bin` checked into shekyl-core, whose bytes did not regenerate.
