"""Retype visually verified raster chart labels within their own white-space boxes."""
import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render_labels(source, request, font_path, output):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError("Choose a new PNG path to preserve previous evidence")
    if output.suffix.lower() != ".png":
        raise ValueError("The display derivative must be a lossless PNG")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != request["source_sha256"]:
        raise ValueError("Source hash differs from the inspected figure")
    if not request["labels"]:
        raise ValueError("No confirmed labels supplied")
    with Image.open(io.BytesIO(data)) as image:
        if image.mode not in {"L", "RGB"}:
            raise ValueError("Expected an opaque grayscale or RGB source")
        result = image.copy()
    boxes = []
    for label in request["labels"]:
        text, size, box = label["text"], label["size"], label["box"]
        if not isinstance(text, str) or not text.strip() or not text.isprintable():
            raise ValueError("Expected one verified line of text")
        if type(size) is not int or size < 1:
            raise ValueError("Label size must be a positive integer in source pixels")
        if len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError("Expected four integer pixel coordinates")
        x, y, right, bottom = box
        w, h = right-x, bottom-y
        if not (0 <= x < right <= result.width and 0 <= y < bottom <= result.height and min(w,h) >= 5):
            raise ValueError("Label box is out of bounds or too small")
        if any(x < r and right > l and y < b and bottom > t for l,t,r,b in boxes):
            raise ValueError("Label boxes overlap")
        boxes.append(box)
        patch = result.crop(box)
        # Reject a box crossing a dark mark, a coloured field, or a non-white border.
        # The reviewer verifies that there is exactly one label inside each box.
        rgb = patch.convert("RGB")
        perimeter = [*rgb.crop((0,0,w,1)).getdata(), *rgb.crop((0,h-1,w,h)).getdata(),
                     *rgb.crop((0,0,1,h)).getdata(), *rgb.crop((w-1,0,w,h)).getdata()]
        if min(min(p) for p in perimeter) < 200 or any(max(p)-min(p)>12 for p in rgb.getdata()):
            raise ValueError("Label box crosses ink or a coloured region: "+text)
        if rgb.convert("L").getextrema()[0] >= 160:
            raise ValueError("No existing dark label found: "+text)
        # Supersample only the replacement text. Keep the original one-pixel perimeter.
        scale = 4
        tile = Image.new(result.mode, ((w-2)*scale,(h-2)*scale), "white")
        draw = ImageDraw.Draw(tile)
        font = ImageFont.truetype(str(font_path), size*scale)
        l,t,r,b = font.getbbox(text, anchor="ls")
        if r-l > tile.width or b-t > tile.height:
            raise ValueError("Verified label does not fit its own box: "+text)
        align = label.get("align", "center")
        if align not in {"left","center"}:
            raise ValueError("Unsupported label alignment")
        dx = 0 if align == "left" else (tile.width-(r-l))//2
        baseline = (tile.height-(b-t))//2-t
        if "baseline" in label:
            if type(label["baseline"]) is not int:
                raise ValueError("Expected an integer baseline in source pixels")
            baseline = (label["baseline"] - y - 1) * scale
            if baseline+t < 0 or baseline+b > tile.height:
                raise ValueError("Baseline would clip label: "+text)
        draw.text((dx-l, baseline),text,font=font,fill="black",anchor="ls")
        result.paste(tile.resize((w-2,h-2),Image.Resampling.LANCZOS),(x+1,y+1))
    encoded = io.BytesIO()
    result.save(encoded, format="PNG")
    with output.open("xb") as target:
        target.write(encoded.getbuffer())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("--labels", required=True, help="Source-bound label request in original image coordinates")
    p.add_argument("--font", required=True, help="Local font file")
    p.add_argument("--out", required=True, help="New lossless display PNG")
    args = p.parse_args(argv)
    render_labels(args.source,json.loads(Path(args.labels).read_text(encoding="utf-8-sig")),args.font,args.out)


if __name__ == "__main__":
    main()
