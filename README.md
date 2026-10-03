# sprite-contract-check

**Did the art change, or did the atlas merely move?**

An offline Python CLI for comparing two Aseprite PNG + JSON exports. It matches
named frames, reconstructs trimmed sprites on their source canvas, and separates
packing changes from pixels, timing, tags, and missing frames. No Aseprite install,
server, API key, or game-engine plugin is needed.

[简体中文](README.zh-CN.md) · [Comparison contract](docs/contract.md) ·
[Original eight-frame demo](examples/demo/repacked-report.html)


## What a repack should not hide

A raw PNG or JSON diff changes when an atlas is repacked, even if every named
sprite is identical. This checker compares the export contract after placing
trimmed frames back on their source canvas.

| Included synthetic case | Content mode | What the report shows |
| --- | --- | --- |
| Same 8 sprites, reordered and repacked | Pass, exit 0 | 8 packing changes; 0 pixel changes |
| One pixel changed, one duration changed, one frame deleted | Changed, exit 1 | Pixel, timing, missing-frame and tag changes |
| Repack with `--mode coordinates` | Changed, exit 1 | Atlas positions and sheet dimensions changed |

These are reproducible fixtures, not a customer case study. A change is a review
signal, not necessarily a bug. Original demo art is included under the MIT license.

## Two-minute quickstart

Requires Git, Python 3.10+ and Pillow 12.2–12.x. Dependency download time varies.
No Aseprite installation is required. Install from source; no package-registry
release is claimed.

```sh
git clone https://github.com/BohaoWorks/sprite-contract-check.git
cd sprite-contract-check
python -m venv .venv
```

Activate the environment with `source .venv/bin/activate` on macOS/Linux, or
`.venv\Scripts\Activate.ps1` in Windows PowerShell. Then:

```sh
python -m pip install .
python -m sprite_contract_check examples/demo/before.json examples/demo/before.png examples/demo/repacked.json examples/demo/repacked.png --old-indices examples/demo/before-indices.json --new-indices examples/demo/repacked-indices.json --json repacked.json --html repacked.html
```

Open `repacked.html` in your browser. Expected: **compatible**, all 8 frames
matched, 8 packing changes and 0 pixel changes. The command exits **0**.

Now compare the deliberately changed export:

```sh
python -m sprite_contract_check examples/demo/before.json examples/demo/before.png examples/demo/changed.json examples/demo/changed.png --old-indices examples/demo/before-indices.json --new-indices examples/demo/changed-indices.json --json changed.json --html changed.html
```

Open `changed.html`. Expected: **changed**, one removed frame, one pixel-change
frame, one duration-change frame and one tag change. Exit **1** is the expected
comparison result, not an installation failure. In PowerShell, inspect
`$LASTEXITCODE`; in macOS/Linux shells, use `echo $?` immediately after the command.

Both reports are self-contained HTML files that work offline. The sidecars in
these examples provide explicit source indices for animation tags; see below
before substituting your own exports.

To run and verify both expected outcomes with one command after installation:

```sh
python examples/quickstart.py --output-dir demo-output
```

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
