# Verification record

Cloud verification on 2026-10-01 using Python 3.12 and Pillow 12.3.0:

- Built a wheel from pyproject.toml using setuptools 84
- Installed that wheel in a project-local virtual environment (existing Pillow)
- All 56 unittest cases passed, including installed-module subprocesses
- Console entry point reports sprite-contract-check 0.1.0
- All six candidate demo cases produced the expected 0/1 verdict and classifications
- Regenerating all seven synthetic exports and reports was byte-for-byte deterministic
- Source and tests compile successfully
- 16-bit PNG rejection tested for grayscale, RGB, grayscale+alpha, RGBA at samples 256 and 257

The configured cross-platform GitHub Actions matrix has not been run locally.
No registry release is claimed. Wheel installation used --no-build-isolation and
--no-deps because required build/runtime packages were already available; a
fresh online dependency installation was not tested here.

Browser screenshot verification remains pending: the cloud shell denies
Chromium's local socket creation, and the managed cloud browser permits HTTP(S)
but not local file URLs. HTML structure, escaping, embedded image sources, CSP,
and report size checks are covered by automated tests, not a visual browser pass.
