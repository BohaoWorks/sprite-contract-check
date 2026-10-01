# sprite-contract-check

**Did the art change, or did the atlas merely move?**

An offline Python CLI for comparing two Aseprite PNG + JSON exports. It matches
named frames, reconstructs trimmed sprites on their source canvas, and separates
packing changes from pixels, timing, tags, and missing frames. No Aseprite install,
server, API key, or game-engine plugin is needed.

[简体中文](README.zh-CN.md) · [Comparison contract](docs/contract.md) ·
[Original eight-frame demo](examples/demo/repacked-report.html)


## Install and try

Requires Python 3.10+ and Pillow 12.2–12.x. Install from this checkout (no package
registry release is claimed):

```sh
python -m pip install .
sprite-contract-check \
  examples/demo/before.json examples/demo/before.png \
  examples/demo/repacked.json examples/demo/repacked.png \
  --old-indices examples/demo/before-indices.json \
  --new-indices examples/demo/repacked-indices.json \
  --json result.json --html result.html
```

Open `result.html` locally. This example exits **0**: all eight named sprites are
unchanged, despite a different sheet shape, packing, JSON order, and array/hash
representation. Replace `repacked` with `changed` in both input paths and the
indices path to see an exit **1** report: one deleted sprite, one changed pixel,
one timing change, and a changed tag. The demo art is original synthetic art
included under this repository's MIT license.

## Use in a build

```sh
sprite-contract-check baseline.json baseline.png candidate.json candidate.png \
  --json report.json --html report.html
```

- **0**: compatible with the selected contract
- **1**: valid inputs, contract changed
- **2**: invalid/unsupported inputs or report-write failure

JSON always goes to stdout; `--json` also saves it. Argument-usage errors use
argparse's stderr and exit 2. Paths never appear in comparison JSON. Output is
deterministic for the same semantic input and options, with no timestamps.

The default `--mode content` permits repacking and equivalent trim changes.
Use `--mode coordinates` when your engine relies on fixed atlas rectangles or
sheet dimensions. Both modes fail on renamed/added/deleted frames, pixel/canvas
size changes, timing, source-index changes, tags, and unknown metadata changes.
A change is a review signal, not necessarily a bug.

### Tags and names: explicit, never guessed

Aseprite's tag ranges refer to source frame indices. Export array order and hash
order do **not** reliably identify those indices, especially with excluded empty
frames. When tags exist, supply complete name-to-source-index sidecars:

```json
{"hero/idle/0": 0, "hero/idle/1": 1}
```

Use `--old-indices old-indices.json --new-indices new-indices.json`. An explicit
integer `index` on every frame is also accepted. Sidecars must agree with embedded
indices. They must come from your known export contract, not guessed ordering.
This release rejects tags spanning omitted indices and duplicate source indices
(e.g. multi-layer source-index reuse).

Use `--mapping rename.json` with `{"old-name":"new-name"}` to pair renamed
frames for visual review. Renames remain contract changes. There is no fuzzy,
position-based, or pixel-based automatic matching.

## What it checks

- Aseprite JSON array and hash, unique names and valid PNGs (up to 8-bit samples; 16-bit rejected)
- Exact reconstructed RGBA pixels; only RGB under alpha zero is normalized
- Frame duration, source canvas size, source indices, tag ranges/direction/repeat
- Frame presence and literal names, conservative unknown-field comparison
- Bounds, trim consistency, missing files, duplicate keys, and resource limits
- Script-free HTML with embedded previews and escaped names/metadata

Only `meta.app`, `meta.version`, and `meta.image` provenance is ignored. PNG paths
are explicit; `meta.image` and frame names are never followed as filesystem paths.
See the [complete contract and limits](docs/contract.md) before relying on CI.

## Why this exists

Public Aseprite reports describe [layer-order shifts (#5626)](https://github.com/aseprite/aseprite/issues/5626),
[ambiguous source indices (#6059)](https://github.com/aseprite/aseprite/issues/6059),
[platform-only metadata noise (#5340)](https://github.com/aseprite/aseprite/issues/5340),
[atlas/data mismatches (#5663)](https://github.com/aseprite/aseprite/issues/5663), and
[missing JSON exports (#6040)](https://github.com/aseprite/aseprite/issues/6040).
These motivate export-contract validation. This is an independent tool, not an
Aseprite fix, packer, editor, or upstream-endorsed project. A passing comparison
cannot establish that an unreviewed baseline matches the original source art.

## Develop

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/generate_demo.py
```

Tests use tiny independent fixtures and cover repacking, trim equivalence,
transparency, tags, timing/pixels, malformed inputs, deterministic output,
HTML injection, path safety, resource limits, and the installed CLI. The included
GitHub Actions workflow runs the suite on Linux, Windows, and macOS with Python
3.10/3.12/3.14; local verification does not imply hosted CI has run.

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md) for the narrow project scope.
