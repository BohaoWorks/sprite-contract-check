"""CLI exit codes: 0 compatible, 1 changed, 2 invalid input/report failure."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .core import ContractError, compare, load_atlas, read_mapping
from .report import render_html


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare named Aseprite sprite contracts offline.")
    parser.add_argument("old_json", type=Path, help="reviewed baseline Aseprite JSON")
    parser.add_argument("old_png", type=Path, help="baseline PNG, explicitly supplied")
    parser.add_argument("new_json", type=Path, help="candidate Aseprite JSON")
    parser.add_argument("new_png", type=Path, help="candidate PNG, explicitly supplied")
    parser.add_argument("--mode", choices=("content", "coordinates"), default="content")
    parser.add_argument("--mapping", type=Path, help="JSON object mapping old names to new names")
    parser.add_argument("--old-indices", type=Path, help="explicit baseline name-to-source-index JSON")
    parser.add_argument("--new-indices", type=Path, help="explicit candidate name-to-source-index JSON")
    parser.add_argument("--json", type=Path, dest="json_output", help="also write deterministic JSON")
    parser.add_argument("--html", type=Path, dest="html_output", help="write a self-contained offline HTML report")
    parser.add_argument("--version", action="version", version=f"sprite-contract-check {__version__}")
    return parser


def _write(path: Path, text: str) -> None:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    except OSError:
        raise ContractError("output_error", "could not write the requested output") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _invalid(error: ContractError) -> dict:
    return {"schema_version": 1, "tool_version": __version__, "status": "invalid",
            "compatible": False, "error": {"code": error.code, "message": str(error)}}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs = [args.old_json, args.old_png, args.new_json, args.new_png, args.mapping, args.old_indices, args.new_indices]
    outputs = [p for p in (args.json_output, args.html_output) if p is not None]
    before = after = None
    safe_outputs = False
    try:
        protected = {p.resolve() for p in inputs if p is not None}
        targets = [p.resolve() for p in outputs]
        if len(set(targets)) != len(targets) or any(p in protected for p in targets):
            raise ContractError("output_collision", "outputs must be distinct from each other and every input")
        # Also protect an input from an existing hard-linked output.
        if any(p.exists() and q is not None and q.exists() and p.samefile(q) for p in outputs for q in inputs):
            raise ContractError("output_collision", "output aliases an input file")
        safe_outputs = True
        mapping = read_mapping(args.mapping) if args.mapping else None
        old_indices = read_mapping(args.old_indices, indices=True, label="old indices") if args.old_indices else None
        new_indices = read_mapping(args.new_indices, indices=True, label="new indices") if args.new_indices else None
        before = load_atlas(args.old_json, args.old_png, indices=old_indices, label="old")
        after = load_atlas(args.new_json, args.new_png, indices=new_indices, label="new")
        result = compare(before, after, mode=args.mode, mapping=mapping)
    except ContractError as exc:
        result = _invalid(exc)
    except OSError:
        result = _invalid(ContractError("output_error", "could not resolve requested file paths"))
    try:
        report = render_html(result, before, after) if args.html_output and safe_outputs else None
        if report is not None:
            _write(args.html_output, report)
        if args.json_output and safe_outputs:
            _write(args.json_output, json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    except ContractError as exc:
        result = _invalid(exc)
    # ASCII JSON keeps output identical on terminals with different encodings.
    sys.stdout.write(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    return 2 if result["status"] == "invalid" else (0 if result["compatible"] else 1)
