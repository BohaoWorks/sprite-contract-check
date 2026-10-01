"""Self-contained, script-free HTML. Untrusted text is always escaped."""

from __future__ import annotations

import base64
import html
import io
import json

from PIL import Image

from .core import Atlas, ContractError, pixel_diff

MAX_PREVIEW_FRAMES = 128
MAX_HTML_BYTES = 16 * 1024 * 1024

CSS = """
:root{color-scheme:dark;--bg:#0c1018;--panel:#141b27;--line:#293347;--muted:#94a4bd;--ink:#edf3fc;--mint:#69e6c0;--red:#ff8299}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1160px;margin:auto;padding:52px 28px 36px}.eyebrow{font:12px/1.4 ui-monospace,monospace;letter-spacing:.15em;color:var(--mint);text-transform:uppercase}
header{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:26px}
h1{font-size:clamp(30px,4vw,48px);line-height:1.12;letter-spacing:-.045em;margin:14px 0}h2{font-size:22px;letter-spacing:-.02em;margin:0 0 10px}
p{margin:10px 0;color:var(--muted)}.verdict{white-space:nowrap;border:1px solid var(--mint);color:var(--mint);border-radius:6px;padding:8px 14px;font:600 12px ui-monospace,monospace;margin-top:6px}
.verdict.changed,.verdict.invalid{color:var(--red);border-color:var(--red)}.lead{font-size:18px;max-width:770px;color:var(--ink)}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:26px 0}.metric{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px 20px}.metric strong{display:block;font:600 30px/1.2 ui-monospace,monospace}.metric span{color:var(--muted);font-size:12px}
.scope{border-left:2px solid var(--mint);padding:2px 18px;margin:24px 0 32px}.scope p{margin:4px 0}.scope strong{color:var(--ink)}
.frames{display:grid;gap:14px}.frame{border:1px solid var(--line);border-radius:8px;background:var(--panel);overflow:hidden}.frame-head{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:15px 20px;border-bottom:1px solid var(--line)}
.frame-head h3{font:600 14px/1.5 ui-monospace,monospace;overflow-wrap:anywhere;margin:0}.badge{font:11px ui-monospace,monospace;border-radius:4px;padding:5px 8px;background:#20382f;color:var(--mint);flex-shrink:0}.badge.breaking{background:#3d2634;color:var(--red)}
.previews{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:18px 20px}.preview-label{display:block;font:11px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.checker{height:148px;border:1px solid var(--line);border-radius:4px;display:flex;align-items:center;justify-content:center;background-color:#1a2332;background-image:conic-gradient(#253045 25%,transparent 0 50%,#253045 0 75%,transparent 0);background-size:16px 16px}
.checker img{image-rendering:pixelated;max-width:90%;max-height:128px;object-fit:contain;width:128px;height:128px}.empty{color:var(--muted);font:12px ui-monospace,monospace}
.frame-foot{padding:0 20px 17px;font:12px/1.6 ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere}.frame-foot b{color:var(--ink);font-weight:500}
details{border:1px solid var(--line);border-radius:6px;margin:24px 0;padding:14px 18px}summary{cursor:pointer;color:var(--ink)}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:var(--muted);font:12px/1.6 ui-monospace,monospace}
footer{border-top:1px solid var(--line);margin-top:32px;padding-top:18px;color:var(--muted);font:11px/1.7 ui-monospace,monospace}
@media(max-width:650px){main{padding:28px 16px}header{display:block}.verdict{display:inline-block;margin:14px 0 0}.metrics{grid-template-columns:repeat(2,1fr)}.previews{gap:8px;padding:14px 12px}.checker{height:106px}.checker img{width:88px;height:88px}.frame-head{padding:12px;display:block}.badge{display:inline-block;margin-top:8px}.frame-foot{padding:0 12px 14px}}
"""


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def _thumbnail(image: Image.Image | None) -> str:
    if image is None:
        return '<span class="empty">No frame</span>'
    thumb = image.copy()
    thumb.thumbnail((96, 96), Image.Resampling.NEAREST)
    stream = io.BytesIO()
    thumb.save(stream, format="PNG", optimize=False)
    data = base64.b64encode(stream.getvalue()).decode("ascii")
    return f'<img alt="Reconstructed sprite preview" src="data:image/png;base64,{data}">'


def _document(body: str) -> str:
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<title>Sprite Contract Check · Comparison</title>'
            f'<style>{CSS}</style></head><body><main>{body}'
            '<footer>sprite-contract-check · Local comparison · No scripts, uploads, or external assets<br>'
            'The baseline must be reviewed and trusted. A passing comparison is not proof of a correct original export.</footer>'
            '</main></body></html>\n')


def render_html(result: dict, before: Atlas | None = None, after: Atlas | None = None) -> str:
    status = result["status"]
    if status == "invalid":
        error = result["error"]
        return _document('<header><div><div class="eyebrow">Sprite Contract Check</div><h1>Input needs attention.</h1></div>'
                         '<div class="verdict invalid">INVALID · EXIT 2</div></header>'
                         f'<p class="lead">{_text(error["message"])}</p><p>Error code: {_text(error["code"])}</p>')
    assert before is not None and after is not None
    s = result["summary"]
    art = s["pixels_changed"] + s["added"] + s["removed"]
    lead = "Art unchanged. Coordinates moved." if result["compatible"] and s["packing_changed"] else ("The sprite contract changed." if not result["compatible"] else "The sprite contract is unchanged.")
    subtitle = "Every named sprite is reconstructed on its original canvas before pixels are compared."
    body = f'<header><div><div class="eyebrow">Sprite Contract Check / {_text(result["mode"])} contract</div><h1>{lead}</h1><p>{subtitle}</p></div><div class="verdict {status}">{status.upper()} · EXIT {0 if result["compatible"] else 1}</div></header>'
    body += '<div class="metrics">'
    for value, label in ((f'{s["matched"]}/{s["frames_before"]}', "frames matched"), (art, "pixel / presence changes"), (s["duration_changed"] + s["tags_changed"], "timing / tag changes"), (s["coordinates_moved"], "atlas rectangles moved")):
        body += f'<div class="metric"><strong>{_text(value)}</strong><span>{label}</span></div>'
    body += '</div><div class="scope">'
    body += f'<p><strong>Contract mode:</strong> {_text(result["mode"])}. Packing changes {"fail" if result["mode"] == "coordinates" else "are informational"}.</p>'
    body += '<p>Only meta.app, meta.version and meta.image are ignored exporter provenance. Explicit PNG inputs bind the image.</p></div>'
    body += '<h2>Frame inspection</h2><p>Before / after show reconstructed sprites. Coral marks any changed RGBA pixel.</p><div class="frames">'
    records = sorted(result["frames"], key=lambda r: (not r["incompatible"], not bool(r["changes"]), r["before"] or r["after"]))
    for record in records[:MAX_PREVIEW_FRAMES]:
        a = before.frames.get(record["before"])
        b = after.frames.get(record["after"])
        old, new = a.pixels if a else None, b.pixels if b else None
        diff = pixel_diff(old, new)[0] if old is not None and new is not None else (old or new)
        name = record["before"] or record["after"]
        if a and b and a.name != b.name:
            name = f"{a.name} → {b.name}"
        badge = "CONTRACT CHANGE" if record["incompatible"] else ("PACKING ONLY" if record["changes"] else "UNCHANGED")
        body += f'<article class="frame"><div class="frame-head"><h3>{_text(name)}</h3><span class="badge {"breaking" if record["incompatible"] else ""}">{badge}</span></div><div class="previews">'
        for label, picture in (("Before", old), ("After", new), ("Diff", diff)):
            body += f'<div><span class="preview-label">{label}</span><div class="checker">{_thumbnail(picture)}</div></div>'
        body += '</div><div class="frame-foot">'
        body += f'<b>{_text(", ".join(record["changes"]) or "unchanged")}</b>'
        if a and b:
            body += f'<br>rect {_text(list(a.rect))} → {_text(list(b.rect))} · duration {a.duration} → {b.duration} ms · changed pixels {record["changed_pixel_count"]}'
        body += '</div></article>'
    body += '</div>'
    if len(records) > MAX_PREVIEW_FRAMES:
        body += f'<p>Preview limited to {MAX_PREVIEW_FRAMES} of {len(records)} frames. JSON includes every frame.</p>'
    body += f'<details><summary>Contract details and summary</summary><pre>{_text(json.dumps({"summary": s, "changes": result["changes"]}, sort_keys=True, indent=2, ensure_ascii=True))}</pre></details>'
    document = _document(body)
    if len(document.encode("utf-8")) > MAX_HTML_BYTES:
        raise ContractError("resource_limit", "HTML report exceeds the 16 MiB limit")
    return document
