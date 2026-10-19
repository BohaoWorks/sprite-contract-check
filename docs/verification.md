# Verification record

## Path-resolution regression, 2026-10-19

Cloud Linux verification with Python 3.12.14 and Pillow 12.3.0:

- Reproduced input/output symbolic-link loops raising an uncaught `RuntimeError`
  and exiting 1 on the previous implementation.
- Twelve new path tests cover actual loops in all inputs, sidecars, report paths
  and parents; simulated `RuntimeError`/`OSError`; unchanged companion reports;
  new nested report directories; ordinary missing inputs; and input aliases.
  They also cover loops around missing/parent components, dangling links,
  existing parent traversal, strict-only path resolution, and simulated Windows
  normalization that would otherwise hide missing or non-directory components.
- All **71 tests passed with zero skips** from source and from an independently
  installed wheel, with installed-package imports verified outside the checkout.
- The real CLI subprocess returned structured `invalid` JSON, exit 2 and empty
  stderr for a report-path loop, without replacing the link.
- Both quickstart outcomes passed from source and installed wheel; regenerating
  the original synthetic demo left its tracked bytes unchanged.

The wheel reused the already-installed Pillow dependency. Local verification is
not a claim that all Python/OS combinations ran; check Actions for the exact
published commit's matrix results.

The first [draft-branch CI run](https://github.com/BohaoWorks/sprite-contract-check/actions/runs/39227130480)
passed the six Linux/macOS jobs but exposed two Windows parent-traversal
regressions. The follow-up checks each original prefix before `..` before whole-path
normalization; this retains the failing cases rather than skipping them.

Cloud verification on 2026-10-01 using Python 3.12 and Pillow 12.3.0:

- Built a wheel from pyproject.toml using setuptools 84
- Installed that wheel in a project-local virtual environment (existing Pillow)
- All 56 unittest cases passed, including installed-module subprocesses
- Console entry point reports sprite-contract-check 0.1.0
- All six candidate demo cases produced the expected 0/1 verdict and classifications
- Regenerating all seven synthetic exports and reports was byte-for-byte deterministic
- Source and tests compile successfully
- 16-bit PNG rejection tested for grayscale, RGB, grayscale+alpha, RGBA at samples 256 and 257

## Hosted verification

On 2026-10-02, the [2026-10-01 Actions run](https://github.com/BohaoWorks/sprite-contract-check/actions/runs/36835326012)
was verified successful for commit `4ccaa6cce17bb4aeb8d2f6534e78ac5e50f9b2e2`.
All nine Linux/Windows/macOS and Python 3.10/3.12/3.14 jobs passed, including
package installation, unit tests, demo generation and the installed command.
This result applies only to that commit; later commits need their own checks.

## Local verification limits
No registry release is claimed. Wheel installation used --no-build-isolation and
--no-deps because required build/runtime packages were already available; a
fresh online dependency installation was not tested here.

Browser screenshot verification remains pending: the cloud shell denies
Chromium's local socket creation, and the managed cloud browser permits HTTP(S)
but not local file URLs. HTML structure, escaping, embedded image sources, CSP,
and report size checks are covered by automated tests, not a visual browser pass.
