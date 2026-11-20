"""Bind an audited native spec to the static HTML/SVG actually being delivered.

This uses our deterministic exporter as the rendering vocabulary, then compares
actual native structures. It does not judge scientific meaning or visual quality.
"""

import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

from .logic import canonical_hash, read_object


class _Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = ET.Element("document")
        self.stack = [self.root]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = ET.SubElement(self.stack[-1], tag, dict(attrs))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_data(self, data):
        node = self.stack[-1]
        if len(node):
            node[-1].tail = (node[-1].tail or "") + data
        else:
            node.text = (node.text or "") + data


def _name(value):
    return value.rsplit("}", 1)[-1].lower()


def _clean(value):
    return " ".join((value or "").split())


def _image_digest(ref, owner):
    parsed = urlsplit(ref)
    if parsed.scheme == "data":
        header, encoded = ref.split(",", 1)
        if ";base64" not in header.lower():
            raise ValueError("Image bindings require base64 or local source files")
        content = base64.b64decode(encoded, validate=True)
    elif not parsed.scheme and not parsed.netloc:
        content = (owner.parent / unquote(parsed.path)).read_bytes()
    else:
        raise ValueError("Image bindings require locally inspectable source bytes")
    return hashlib.sha256(content).hexdigest()


def _signature(node, owner):
    """Rendering attributes and content; generated internal IDs are not evidence."""
    attrs = {}
    for key, value in node.attrib.items():
        key = _name(key)
        # A definition ID participates in url(#...) rendering. Internal cell
        # IDs are bookkeeping, while breaking a gradient ID changes pixels.
        definition_id = key == "id" and _name(node.tag) in {"lineargradient", "radialgradient", "clippath", "mask", "filter", "marker", "pattern", "symbol"}
        if (key == "id" and not definition_id) or key.startswith("aria-") or key in {"alt", "spellcheck"}:
            continue
        if key.startswith("data-") and key not in {"data-asset-id", "data-object-type", "data-source-ids"}:
            continue
        if key == "style":
            declarations = [part.split(":", 1) for part in value.split(";") if ":" in part]
            value = tuple(sorted((name.strip().lower(), _clean(item)) for name, item in declarations))
        elif key in {"src", "href"} and _name(node.tag) in {"img", "image"}:
            value = _image_digest(value, owner)
        elif key == "data-source-ids":
            value = tuple(json.loads(value))
        attrs[key] = value
    preserve_text = node.get("contenteditable") in {"true", "plaintext-only", ""} or _name(node.tag) in {"text", "tspan"}
    normalize = (lambda value: value or "") if preserve_text else _clean
    return (_name(node.tag), tuple(sorted(attrs.items())), normalize(node.text), tuple((_signature(child, owner), normalize(child.tail)) for child in node))


def validate_export_bindings(poster_spec, poster_html, poster_svg, asset_table):
    """Check actual exports against their spec and authoritative source assets.

The HTML metadata must describe exactly poster_spec. Actual panels and objects
must still exist under their correct panel, with the intended native type and
real rendered image bytes. Full static panel/SVG signatures also check text,
table cells, geometry, typography, rules, colors and source-SVG contents against
a fresh deterministic export. Internal table-cell/background/SVG IDs are not
treated as separately planned objects. Normal exports need no browser; the explicit
typography_repair mode replays local browser measurement and MathText before
comparison. No model or API is invoked.
"""
    spec, assets = read_object(poster_spec), read_object(asset_table)
    if isinstance(asset_table, (str, Path)):
        assets = {**assets, "root": assets.get("root", str(Path(asset_table).resolve().parent))}
    html_path, svg_path = Path(poster_html).resolve(), Path(poster_svg).resolve()
    blockers = []

    def block(code, message, **details):
        blockers.append({"code": code, "message": message, **details})

    try:
        actual_html = _Document(html_path.read_text()).root
        actual_svg = ET.parse(svg_path).getroot()
        metadata_nodes = [n for n in actual_html.iter() if n.get("id") == "posfoxgen-metadata"]
        if len(metadata_nodes) != 1 or canonical_hash(json.loads("".join(metadata_nodes[0].itertext())).get("spec")) != canonical_hash(spec):
            block("export_metadata_mismatch", "HTML metadata.spec must equal the actual audited poster_spec")
        from .editable import export_svg
        with tempfile.TemporaryDirectory(prefix="posfoxgen-export-binding-") as directory:
            expected_path = Path(directory)
            export_svg(spec, assets, expected_path)
            expected_html = _Document((expected_path / "poster.html").read_text()).root
            expected_svg = ET.parse(expected_path / "poster.svg").getroot()
            panels = {p["id"]: p for p in spec.get("panels", [])}
            for kind, actual, expected, actual_owner, expected_owner in (
                ("HTML", actual_html, expected_html, html_path, expected_path / "poster.html"),
                ("SVG", actual_svg, expected_svg, svg_path, expected_path / "poster.svg"),
            ):
                parents = {child: parent for parent in actual.iter() for child in parent}
                declared_panels = [n.get("data-panel-id") for n in actual.iter() if n.get("data-panel-id")]
                if len(declared_panels) != len(panels) or set(declared_panels) != set(panels):
                    block("export_panel_mismatch", f"Actual {kind} panel coverage differs from the audited spec")
                for panel_id, panel in panels.items():
                    targets = [n for n in actual.iter() if n.get("id") == panel_id and n.get("data-panel-id") == panel_id]
                    expected_panel = next(n for n in expected.iter() if n.get("id") == panel_id and n.get("data-panel-id") == panel_id)
                    if len(targets) != 1:
                        block("export_panel_mismatch", f"Actual {kind} must contain panel {panel_id} exactly once")
                        continue
                    for obj in panel.get("objects", []):
                        nodes = [n for n in actual.iter() if n.get("id") == obj["id"]]
                        expected_object = next(n for n in expected_panel.iter() if n.get("id") == obj["id"])
                        if len(nodes) != 1:
                            block("export_object_mismatch", f"Actual {kind} must contain object {obj['id']} exactly once")
                            continue
                        node = nodes[0]
                        ancestor = parents.get(node)
                        while ancestor is not None and not ancestor.get("data-panel-id"):
                            ancestor = parents.get(ancestor)
                        if ancestor is None or ancestor.get("data-panel-id") != panel_id or _name(node.tag) != _name(expected_object.tag) or node.get("data-object-type") != expected_object.get("data-object-type"):
                            block("export_object_mismatch", f"Actual {kind} object {obj['id']} has the wrong panel or native type")
                    if _signature(targets[0], actual_owner) != _signature(expected_panel, expected_owner):
                        block("export_rendering_mismatch", f"Actual {kind} panel {panel_id} differs from the audited native export in content, source bytes or rendering attributes")
                if kind == "SVG" and _signature(actual, actual_owner) != _signature(expected, expected_owner):
                    block("export_rendering_mismatch", "Actual SVG differs from the audited native export")
                if kind == "HTML":
                    actual_styles = [_clean(n.text) for n in actual.iter() if _name(n.tag) == "style"]
                    expected_styles = [_clean(n.text) for n in expected.iter() if _name(n.tag) == "style"]
                    if actual_styles != expected_styles:
                        block("export_rendering_mismatch", "Actual HTML global styles differ from the audited native export")
    except (OSError, ValueError, TypeError, KeyError, StopIteration, ET.ParseError) as exc:
        block("export_binding_invalid", str(exc))
    return {"pass": not blockers, "blockers": blockers, "scientific_quality_pass": None}
