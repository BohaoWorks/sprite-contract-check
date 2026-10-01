# Contract v1

## Matching and verdicts

Frame names are exact Unicode strings (no normalization). Array order and object
order are irrelevant. An explicit one-to-one old-to-new rename map assists pairing;
renaming still fails the contract. No filename parsing recovers source indices.
Frames are reconstructed with `spriteSourceSize` at the declared `sourceSize`.
Exact RGBA and canvas dimensions form the pixel digest. Fully transparent RGB is
normalized to zero; every nonzero alpha and its RGB channels are exact. Images
are compared as decoded channel values, with no ICC/gamma color management.

Content mode treats atlas rectangle, equivalent trimming, and sheet-size changes
as informational. Coordinate mode fails on packing or sheet-size changes too.
Duration, presence, names, canvas dimensions, indices, tag metadata and unknown
root/meta/frame fields affect both modes. JSON numeric types are not coerced.
The report's `changed_pixel_count` can be zero for a canvas-size-only change.

Tags require unique explicit nonnegative source indices for every frame. Every
index in each inclusive tag range must exist; missing/excluded source frames are
not silently skipped. Direction accepts forward, reverse, pingpong, and
pingpong_reverse. Missing direction means forward; missing repeat means 0.
Tag members follow explicit source-index order. Tag names are unique. Extra tag
fields are compared. This is deliberately narrower than all possible Aseprite
exports (for example, multiple layers sharing source indices are unsupported).

## Metadata treatment

Only meta.app, meta.version, and meta.image are ignored provenance. meta.size is
validated against the explicit PNG and handled as sheet dimensions. frameTags
are normalized as described above. scale must equal string "1" (or be absent).
layers and slices must be absent or empty arrays. Missing and empty layers/slices
are equivalent. Empty and missing frameTags are equivalent. A hash key substitutes
for filename; if filename is present it must agree. Rotated must be false, and
trimmed must be a Boolean. Other fields are conservatively compared, including
meta.format. PNG compression, ancillary metadata, and palette representation are
not part of the contract; decoded RGBA channels are.

## Boundaries and security

- PNG with 1/2/4/8-bit samples only (valid PNG color types, including palette);
  16-bit samples are rejected before decoding to avoid lossy RGBA8 reduction
- APNG, rotations, scaled exports, nonempty layers/slices rejected
- Each JSON at most 4 MiB, maximum nesting 32; duplicate keys and nonfinite values rejected
- Each PNG at most 32 MiB; sheet sides at most 8192, total at most 16,777,216 pixels
- 1–2048 frames; names 1–256 characters, no NUL
- Source canvas sides at most 2048 and 1,048,576 pixels per frame
- At most 16,777,216 reconstructed pixels per input atlas
- Durations 1–3,600,000 ms; indices 0–1,000,000; repeat 0–65,535
- HTML at most 16 MiB, with at most 128 previews; JSON includes all frames

Use regular local files in a trusted directory. Explicit output paths are writable
by design; the program rejects input/output aliases and duplicate output paths.
Do not allow untrusted users to supply output paths in a privileged service. This
is a local CLI, not a hostile multi-tenant sandbox. It does not fetch URLs or
execute exported strings. Reports embed images, escape text, contain no script,
and declare a restrictive content security policy. Finite limits bound common
resource hazards but are not a formal hard memory/CPU limit.

JSON schema_version 1 has `status` (pass/changed/invalid), `compatible`, summary,
frame records with before/after contracts, tag changes and metadata changes.
Invalid results instead have an error code and a non-path-bearing message.
Argument-parser failures use stderr rather than report JSON. Each output write
is atomic, but multiple output files are not transactional. Treat process exit
status/stdout as authoritative if report output fails.

A baseline must be independently reviewed. Identical wrong exports can pass;
valid bounds alone cannot detect a mislabeled source sprite. No .ase/.aseprite
parsing, rendering, atlas generation, or automatic baseline approval is provided.
