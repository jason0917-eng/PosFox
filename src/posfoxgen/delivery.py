"""Byte integrity and editable-package checks, not a scientific quality judge."""

import base64
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


FORMAT = "posfoxgen-delivery-manifest-v1"
REQUIRED_FORMATS = {".html", ".svg", ".png", ".pdf"}


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(root, value, base=None):
    path = Path(value)
    if not path.is_absolute():
        path = (base or root) / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path is outside package root: {value}")
    return path


def _role(path):
    parts = {p.lower() for p in path.parts[:-1]}
    if any("review" in p or "receipt" in p for p in path.parts):
        return "review_receipt"
    if parts & {"source", "sources", "papers"}:
        return "source_evidence"
    if parts & {"assets", "images"}:
        return "source_asset"
    return "deliverable" if path.suffix.lower() in REQUIRED_FORMATS else "artifact"


def create_delivery_manifest(root, files):
    """Bind explicit package files, expanding directory entries recursively.

    Paths may be root-relative or absolute inside root. No network, model call,
    rendering or scientific review is performed. Re-running binds new bytes and
    must therefore be followed by a fresh validate_package call.
    """
    root = Path(root).resolve(strict=True)
    if not isinstance(files, (list, tuple)) or not files:
        raise ValueError("files must be a nonempty list of paths or directories")
    selected = set()
    destination = root / "manifest.json"
    for value in files:
        path = _inside(root, value)
        if not path.exists():
            raise ValueError(f"Package file does not exist: {value}")
        entries = path.rglob("*") if path.is_dir() else [path]
        for entry in entries:
            checked = _inside(root, entry)
            if checked.is_file() and checked != destination:
                selected.add(checked)
    records = []
    for path in sorted(selected):
        relative = path.relative_to(root)
        records.append({"path": relative.as_posix(), "sha256": _hash(path), "size": path.stat().st_size, "role": _role(relative)})
    result = {"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(), "files": records, "scientific_quality_pass": None}
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.editable_text = []
        self.images = []
        self.resources = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        parent = self.stack[-1] if self.stack else (False, False)
        editable = values.get("contenteditable") in {"", "true", "plaintext-only"} or parent[0]
        if values.get("contenteditable") == "false":
            editable = False
        hidden = tag in {"script", "style", "head"} or parent[1]
        if tag not in {"img", "link", "meta", "input", "br", "hr", "source", "wbr"}:
            self.stack.append((editable, hidden))
        if tag == "img":
            self.images.append(values)
        if tag in {"script", "link", "source", "iframe"}:
            ref = values.get("src", values.get("href"))
            if ref:
                self.resources.append(ref)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {"img", "link", "meta", "input", "br", "hr", "source", "wbr"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] and not self.stack[-1][1] and data.strip():
            self.editable_text.append(data.strip())


def _data_bytes(value):
    header, data = value.split(",", 1)
    if ";base64" not in header.lower():
        raise ValueError("Only base64 image data URIs are accepted")
    return base64.b64decode(data, validate=True)


def _dimension(value, basis=None):
    percentage = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)%\s*", str(value or ""))
    if percentage and basis is not None:
        return float(percentage.group(1)) * basis / 100
    found = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)(?:px|pt)?\s*", str(value or ""))
    number = float(found.group(1)) if found else None
    return number if number is not None and math.isfinite(number) else None


def _transform_area_scale(node, parents):
    scale = 1.0
    while node is not None:
        if re.search(r"(?:^|;)\s*transform\s*:", node.get("style", ""), re.I):
            return None
        transform = node.get("transform", "")
        for name, raw in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", transform):
            try:
                values = [float(x) for x in re.split(r"[ ,]+", raw.strip())]
            except ValueError:
                return None
            if not all(math.isfinite(x) for x in values):
                return None
            if name == "scale" and len(values) in {1, 2}:
                scale *= abs(values[0] * values[-1])
            elif name == "matrix" and len(values) == 6:
                scale *= abs(values[0] * values[3] - values[1] * values[2])
            elif name not in {"translate", "rotate", "skewX", "skewY"}:
                return None
        node = parents.get(node)
    return scale


def validate_package(root, manifest_path="manifest.json"):
    """Check bound bytes, image/PDF decoding and native editable structure.

    HTML source images must carry matching data-source-sha256 values and be
    manifest-bound. SVG data-asset-id images are cross-checked against those
    source hashes; an explicit SVG data-source-sha256 is checked when supplied.
    Passing establishes package properties only, never scientific correctness.
    """
    root = Path(root).resolve()
    blockers = []

    def block(code, message, path=None):
        blockers.append({"code": code, "message": message, **({"path": str(path)} if path else {})})

    result = {"pass": False, "blockers": blockers, "scientific_quality_pass": None, "checked_files": 0}
    try:
        manifest_file = _inside(root, manifest_path)
        manifest = json.loads(manifest_file.read_text())
    except (ValueError, OSError, TypeError) as exc:
        block("invalid_manifest", str(exc))
        return result
    if manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), list):
        block("invalid_manifest", "Unknown manifest format or missing files list")
        return result
    bound = {}
    for record in manifest["files"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            block("invalid_manifest_record", "Each file needs a relative path and sha256")
            continue
        raw = record["path"]
        try:
            if Path(raw).is_absolute() or ".." in Path(raw).parts:
                raise ValueError("Manifest paths must be package-relative without parent traversal")
            path = _inside(root, raw)
        except ValueError as exc:
            block("path_outside_package", str(exc), raw)
            continue
        if path in bound:
            block("duplicate_manifest_path", "A file is bound more than once", raw)
        if not path.is_file():
            block("missing_bound_file", "Bound file does not exist", raw)
            continue
        digest = _hash(path)
        if digest != record.get("sha256") or ("size" in record and path.stat().st_size != record["size"]):
            block("hash_mismatch", "Bound file bytes changed", raw)
        bound[path] = {**record, "actual_sha256": digest}
    result["checked_files"] = len(bound)
    deliverables = [p for p, record in bound.items() if record.get("role", _role(p.relative_to(root))) == "deliverable"]
    for suffix in sorted(REQUIRED_FORMATS):
        if not any(p.suffix.lower() == suffix for p in deliverables):
            block("missing_required_format", f"Package requires a {suffix} deliverable")
    from PIL import Image
    for path in bound:
        if path.suffix.lower() == ".png":
            try:
                with Image.open(path) as image:
                    if image.format != "PNG":
                        raise ValueError("File is not PNG")
                    image.verify()
                with Image.open(path) as image:
                    image.load()
            except (ValueError, OSError, SyntaxError) as exc:
                block("invalid_png", str(exc), path.relative_to(root))
    import fitz
    for path in deliverables:
        if path.suffix.lower() == ".pdf":
            try:
                with fitz.open(path) as document:
                    if document.needs_pass:
                        raise ValueError("PDF requires a password")
                    if len(document) != 1:
                        block("pdf_page_count", "Poster PDF must contain exactly one page", path.relative_to(root))
                    for page in document:
                        page.get_text()
            except Exception as exc:
                block("invalid_pdf", str(exc), path.relative_to(root))
    source_hashes = {}
    bound_digests = {r["actual_sha256"] for r in bound.values()}

    def reference_bytes(ref, owner):
        parsed = urlsplit(ref)
        if parsed.scheme == "data":
            try:
                return _data_bytes(ref)
            except (ValueError, TypeError) as exc:
                block("invalid_embedded_image", str(exc), owner.relative_to(root))
                return None
        if parsed.scheme or parsed.netloc:
            block("external_asset_reference", "Image/resource must be packaged locally", owner.relative_to(root))
            return None
        try:
            target = _inside(root, unquote(parsed.path), owner.parent)
        except ValueError as exc:
            block("path_outside_package", str(exc), owner.relative_to(root))
            return None
        if target not in bound:
            block("unbound_asset_reference", "Referenced local asset is not bound in the manifest", owner.relative_to(root))
            return None
        return target.read_bytes()

    for path in deliverables:
        if path.suffix.lower() != ".html":
            continue
        parser = _HTML()
        try:
            parser.feed(path.read_text())
        except (ValueError, OSError) as exc:
            block("invalid_html", str(exc), path.relative_to(root))
            continue
        if not parser.editable_text:
            block("missing_editable_html_text", "HTML needs nonempty native contenteditable text", path.relative_to(root))
        if not parser.images:
            block("missing_source_images", "HTML needs source-hash-bound scientific image references", path.relative_to(root))
        for item in parser.images:
            raw = reference_bytes(item.get("src", ""), path)
            declared = item.get("data-source-sha256", item.get("data-source-hash"))
            if raw is not None:
                actual = hashlib.sha256(raw).hexdigest()
                try:
                    with Image.open(io.BytesIO(raw)) as image:
                        image.load()
                except (ValueError, OSError) as exc:
                    block("invalid_source_image", str(exc), path.relative_to(root))
                if declared != actual:
                    block("source_hash_mismatch", "HTML image lacks a matching source hash", path.relative_to(root))
                elif actual not in bound_digests:
                    block("unbound_source_image", "Embedded image source bytes are not bound as a package file", path.relative_to(root))
                else:
                    source_hashes[item.get("data-asset-id", "")] = actual
        for ref in parser.resources:
            reference_bytes(ref, path)
    for path in deliverables:
        if path.suffix.lower() != ".svg":
            continue
        try:
            svg = ET.fromstring(path.read_text())
        except (ET.ParseError, OSError) as exc:
            block("invalid_svg", str(exc), path.relative_to(root))
            continue
        if svg.tag.rsplit("}", 1)[-1] != "svg":
            block("invalid_svg", "SVG document root is required", path.relative_to(root))
        native = [n for n in svg.iter() if n.tag.rsplit("}", 1)[-1] == "text" and "".join(n.itertext()).strip()]
        if not native:
            block("missing_native_svg_text", "SVG needs real text/tspan objects", path.relative_to(root))
        width, height = _dimension(svg.get("width")), _dimension(svg.get("height"))
        viewbox = re.split(r"[ ,]+", svg.get("viewBox", "").strip())
        if len(viewbox) == 4:
            try:
                width, height = float(viewbox[2]), float(viewbox[3])
            except ValueError:
                pass
        if not width or not height or width <= 0 or height <= 0:
            block("unknown_svg_canvas", "SVG requires positive canvas dimensions", path.relative_to(root))
        parents = {child: parent for parent in svg.iter() for child in parent}
        for node in svg.iter():
            kind = node.tag.rsplit("}", 1)[-1]
            if kind == "foreignObject":
                block("non_native_svg_content", "SVG foreignObject is not native editable text", path.relative_to(root))
            if kind != "image":
                continue
            iw, ih = _dimension(node.get("width"), width), _dimension(node.get("height"), height)
            scale = _transform_area_scale(node, parents)
            if not iw or not ih or scale is None:
                block("unverified_svg_image_geometry", "SVG image geometry or transform could not be verified", path.relative_to(root))
            if width and height and iw and ih and scale is not None and iw * ih * scale >= width * height * 0.9:
                block("full_canvas_bitmap", "A canvas-wide raster cannot replace the editable poster", path.relative_to(root))
            raw = reference_bytes(node.get("href", node.get("{http://www.w3.org/1999/xlink}href", "")), path)
            if raw is None:
                continue
            actual = hashlib.sha256(raw).hexdigest()
            declared = node.get("data-source-sha256", node.get("data-source-hash"))
            asset_id = node.get("data-asset-id")
            if declared is not None and declared != actual:
                block("source_hash_mismatch", "SVG embedded image differs from its declared source hash", path.relative_to(root))
            if asset_id and asset_id in source_hashes and actual != source_hashes[asset_id]:
                block("source_hash_mismatch", "SVG and HTML source images differ for one asset ID", path.relative_to(root))
            if actual not in bound_digests:
                block("unbound_source_image", "SVG embedded image must match bound original image bytes", path.relative_to(root))
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
            except (ValueError, OSError) as exc:
                block("invalid_embedded_image", str(exc), path.relative_to(root))
    result["pass"] = not blockers
    result["status"] = "pass" if not blockers else "blocked"
    return result
