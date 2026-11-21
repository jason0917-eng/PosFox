"""Offer native PDF bounds for visual inspection before replacing a scientific figure."""
import hashlib
import json
import math
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


def inspect_figure_page(pdf_path, page_number, out_dir, render_scale=2):
    """Save a numbered page preview and unmarked candidate crops. Selection is visual."""
    if not math.isfinite(render_scale) or not .25 <= render_scale <= 16:
        raise ValueError("render_scale must be finite and between .25 and 16")
    pdf_path = Path(pdf_path)
    with fitz.open(pdf_path) as document:
        if not 1 <= page_number <= len(document):
            raise ValueError("figure page is outside PDF")
        page = document[page_number - 1]
        out = Path(out_dir) / f"figure-review-p{page_number:03d}"
        out.mkdir(parents=True, exist_ok=True)
        # Graphics clips frequently bound a whole vector illustration. Inline
        # images may instead be separate scientific figures or tiny components.
        bounds = [item["scissor"] for item in page.get_drawings(extended=True)
                  if item["type"] == "clip" and len(item["items"]) == 1
                  and item["items"][0][0] == "re"]
        bounds.extend(item["bbox"] for item in page.get_image_info())
        rectangles = []
        for raw in bounds:
            rect = fitz.Rect(raw) * page.rotation_matrix
            if rect.is_empty or not page.rect.contains(rect) or rect == page.rect:
                continue
            rectangles.append(rect)
        selected = []
        for rect in sorted(rectangles, key=lambda r: r.get_area(), reverse=True):
            if any(outer.contains(rect) for outer in selected):
                continue
            selected.append(rect)
            if len(selected) == 8:
                break
        # Keep numbering reproducible and make the overview readable in page order.
        selected.sort(key=lambda r: (r.y0, r.x0))
        preview_scale = min(1.5, 1450 / max(page.rect.width, page.rect.height))
        preview = page.get_pixmap(matrix=fitz.Matrix(preview_scale, preview_scale),
                                  colorspace=fitz.csRGB, alpha=False)
        image = Image.frombytes("RGB", (preview.width, preview.height), preview.samples)
        draw = ImageDraw.Draw(image)
        candidates = []
        for index, rect in enumerate(selected, 1):
            name = f"pdf-p{page_number:03d}-c{index}"
            pixels = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale),
                                     clip=rect, alpha=False)
            data = pixels.tobytes("png")
            (out / (name + ".png")).write_bytes(data)
            candidates.append({"id": name, "type": "figure", "page": page_number,
                               "bbox": list(rect), "path": name + ".png",
                               "sha256": hashlib.sha256(data).hexdigest(),
                               "pixels": [pixels.width, pixels.height]})
            coords = [v * preview_scale for v in rect]
            draw.rectangle(coords, outline="#d32339", width=2)
            draw.text((coords[0]+2, max(0, coords[1]-13)), str(index),
                      fill="black", stroke_width=2, stroke_fill="white")
        image.save(out / "page.png")
        manifest = {"page": page_number, "page_bounds": list(page.rect),
                    "paper_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                    "preview": "page.png", "assets": candidates}
        (out / "figure-candidates.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        return out / "figure-candidates.json"
