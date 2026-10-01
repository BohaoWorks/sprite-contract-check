# Contributing

Keep this a small offline export-contract checker. Please include a minimized
synthetic PNG/JSON pair and a regression test for parser or comparison changes.
Never submit proprietary artwork, credentials, or private production exports.

Install with `python -m pip install -e .`, then run
`python -m unittest discover -s tests -v` and `python examples/generate_demo.py`.
Document changes to verdicts, resource limits, or ignored fields in docs/contract.md.
Do not silently infer frame indices, normalize unknown metadata, or accept
unsupported export modes. New packing algorithms and image-editor features are
outside the project scope. No paid services or runtime network access are needed.
