#!/usr/bin/env python3
"""Recover or verify the POSFOXGEN public-poster library, without model APIs.

Existing manifests pin original source URLs and SHA-256 hashes. Verified cached
originals are reused; missing previews can be rebuilt locally. New libraries may
be initialized from the downloaded Paper2Poster metadata. PosterBench titles are
excluded both during initialization and when checking an existing library.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image

OFFICIAL_HOSTS = frozenset({"neurips.cc", "icml.cc", "iclr.cc"})
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
IMAGE_SUFFIXES = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "TIFF": ".tif"}


def normalize_title(title):
    return "".join(c for c in str(title).casefold() if c.isalnum())


def safe_path(root, relative):
    """Resolve a manifest path without accepting traversal or symlink escapes."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("manifest path must be nonempty and root-relative")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {".", "..", ""} for part in relative.split("/")):
        raise ValueError("manifest path must be relative and cannot escape root")
    base = Path(root).resolve()
    result = base.joinpath(*path.parts).resolve()
    if not result.is_relative_to(base):
        raise ValueError("manifest path resolves outside root (symlink escape)")
    return result


def validate_source_url(url):
    parsed = urlsplit(str(url))
    if parsed.scheme != "https":
        raise ValueError("poster sources must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("poster source credentials are forbidden")
    if parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError("poster source is not an official whitelisted conference host")
    if parsed.port not in {None, 443}:
        raise ValueError("poster source port must be HTTPS default")
    if not parsed.path or parsed.fragment:
        raise ValueError("poster source must be an official asset URL without fragment")
    return str(url)


class _OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_source_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_official(url):
    """Download only a recorded official URL; validate every redirect as well."""
    validate_source_url(url)
    opener = build_opener(_OfficialRedirects())
    request = Request(url, headers={"User-Agent": "POSFOXGEN-reference-library/1.0"})
    with opener.open(request, timeout=60) as response:
        validate_source_url(response.geturl())
        raw = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise ValueError("official asset exceeds 80 MiB download limit")
    return raw


def validate_record(record, root, require_hash=True):
    if not isinstance(record, dict):
        raise ValueError("poster record must be an object")
    rid = record.get("id", "")
    if not re.fullmatch(r"poster-[0-9]{3,}", rid):
        raise ValueError("poster record requires a stable poster-NNN id")
    if not str(record.get("title", "")).strip():
        raise ValueError("poster record requires a title")
    validate_source_url(record.get("source_url", ""))
    original = safe_path(root, record.get("original_path"))
    preview = safe_path(root, record.get("preview_path"))
    if original.parent != preview.parent or original.parent.name != rid:
        raise ValueError("original and preview paths must share the record-id directory")
    if original.name not in {"original" + ext for ext in IMAGE_SUFFIXES.values()}:
        raise ValueError("original path must name an allowed original image file")
    if preview.name != "preview.png":
        raise ValueError("preview path must name preview.png")
    digest = record.get("sha256")
    if require_hash and not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
        raise ValueError("existing manifest record requires a pinned lowercase sha256")
    if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
        raise ValueError("invalid sha256 in record")
    return original, preview


def inspect_image(raw, expected=None):
    with Image.open(BytesIO(raw)) as image:
        image.verify()
    with Image.open(BytesIO(raw)) as image:
        image.load()
        if min(image.size) < 400:
            raise ValueError("source image is too small to be a full-poster reference")
        if image.format not in IMAGE_SUFFIXES:
            raise ValueError("unsupported poster image format")
        if expected and all(expected.get(k) for k in ("width", "height")):
            if tuple(image.size) != (expected["width"], expected["height"]):
                raise ValueError("decoded poster dimensions differ from manifest")
        return {"width": image.width, "height": image.height, "format": image.format}


def _atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    try:
        temporary.write_bytes(raw)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def make_preview(original, preview):
    with Image.open(original) as image:
        result = image.convert("RGB")
        result.thumbnail((1600, 1600))
        buffer = BytesIO()
        result.save(buffer, format="PNG")
        size = list(result.size)
    _atomic_write(preview, buffer.getvalue())
    return size


def verify_record(record, root):
    """Perform offline original hash/image and preview checks; never download."""
    try:
        original, preview = validate_record(record, root)
        raw = original.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != record["sha256"]:
            raise ValueError("original sha256 mismatch")
        properties = inspect_image(raw, record)
        if not preview.is_file():
            raise ValueError("preview is missing")
        with Image.open(preview) as image:
            image.verify()
        with Image.open(preview) as image:
            scale = min(1.0, 1600 / properties["width"], 1600 / properties["height"])
            expected_size = (round(properties["width"] * scale), round(properties["height"] * scale))
            if any(abs(a - b) > 1 for a, b in zip(image.size, expected_size)):
                raise ValueError("preview dimensions do not match contained original")
        return {"id": record["id"], "status": "valid", "sha256": actual, **properties}
    except (ValueError, OSError, KeyError, Image.DecompressionBombError) as exc:
        return {"id": record.get("id"), "status": "invalid", "error": str(exc)}


def restore_record(record, root, fetcher=None):
    """Reuse a valid original or restore its exact pinned source and preview."""
    original, preview = validate_record(record, root, require_hash=False)
    fetcher = fetcher or fetch_official
    cached = False
    if original.is_file() and record.get("sha256"):
        raw = original.read_bytes()
        cached = hashlib.sha256(raw).hexdigest() == record["sha256"]
        if cached:
            inspect_image(raw, record)
    if not cached:
        raw = fetcher(record["source_url"])
        if len(raw) > MAX_DOWNLOAD_BYTES:
            raise ValueError("official asset exceeds 80 MiB download limit")
        digest = hashlib.sha256(raw).hexdigest()
        if record.get("sha256") and record["sha256"] != digest:
            raise ValueError("downloaded original sha256 mismatch; original retained")
        properties = inspect_image(raw, record)
        if not record.get("sha256"):
            suffix = IMAGE_SUFFIXES[properties["format"]]
            original = original.with_suffix(suffix)
            record["original_path"] = original.relative_to(Path(root).resolve()).as_posix()
        _atomic_write(original, raw)
        record.update(properties, sha256=digest, bytes=len(raw))
        record["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
    record["preview_dimensions"] = make_preview(original, preview)
    _atomic_write(original.parent / "source.json", (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode())
    return {"id": record["id"], "status": "cached" if cached else "downloaded"}


def records_from_metadata(rows, excluded_titles, limit=50, library_relative="data/poster_references"):
    excluded = {normalize_title(title) for title in excluded_titles}
    excluded.add(normalize_title("AutoDesign: Meta-Harness Optimization for Long-Horizon Agentic Design"))
    records = []
    for index, row in enumerate(rows):
        if normalize_title(row.get("title", "")) in excluded:
            continue
        url = row.get("image_url", "")
        validate_source_url(url)
        rid = f"poster-{index + 1:03d}"
        suffix = Path(urlsplit(url).path).suffix.lower()
        if suffix not in IMAGE_SUFFIXES.values():
            raise ValueError("metadata poster URL must have an allowed image suffix")
        records.append({
            "id": rid, "title": row["title"], "conference": row.get("conference"),
            "year": row.get("year"), "paper_url": row.get("paper_url"),
            "source_url": url, "source_dataset": "https://huggingface.co/datasets/Paper2Poster/Paper2Poster",
            "dataset_row_index": index, "split": "development_reference",
            "type": "author_created_scientific_poster",
            "original_path": f"{library_relative}/{rid}/original{suffix}",
            "preview_path": f"{library_relative}/{rid}/preview.png",
            "access_status": "public_official_conference_asset",
            "copyright_status": "underlying_poster_rights_not_verified",
            "usage_scope": "reference-inspection-only; no poster content or redistribution rights inferred",
            "metadata_license": "MIT for dataset metadata only",
        })
        if len(records) >= limit:
            break
    return records


def _read_rows(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = json.loads(path.read_text())
    if not isinstance(result, list):
        raise ValueError("metadata JSON must contain a list")
    return result


def run_library(root, manifest_path, *, verify_only=False, excluded_titles=None, workers=4):
    root, manifest_path = Path(root).resolve(), Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("manifest requires nonempty records")
    if manifest.get("count", len(records)) != len(records):
        raise ValueError("manifest count does not match records")
    if excluded_titles is None:
        benchmark = root / "data/metadata/PosterBench.jsonl"
        if not benchmark.exists():
            benchmark = root / "references/data-manifests/PosterBench.jsonl"
        excluded_titles = [row["title"] for row in _read_rows(benchmark)] if benchmark.exists() else []
    heldout = {normalize_title(title) for title in excluded_titles}
    identifiers, paths = set(), set()
    for record in records:
        original, preview = validate_record(record, root, require_hash=verify_only)
        if record["id"] in identifiers or str(original) in paths or str(preview) in paths:
            raise ValueError("manifest contains duplicate ids or paths")
        if normalize_title(record["title"]) in heldout:
            raise ValueError(f"held-out benchmark title excluded: {record['id']}")
        identifiers.add(record["id"])
        paths.update((str(original), str(preview)))
    outcomes = []
    if not verify_only:
        def restore(record):
            try:
                return restore_record(record, root)
            except (ValueError, OSError) as exc:
                return {"id": record["id"], "status": "invalid", "error": str(exc)}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
            outcomes = list(pool.map(restore, records))
    checks = [verify_record(record, root) for record in records]
    failures = [r for r in outcomes + checks if r["status"] == "invalid"]
    digests = [record.get("sha256") for record in records]
    unique = len(set(digests)) == len(records) and None not in digests
    if not unique:
        failures.append({"status": "invalid", "error": "duplicate or missing original sha256 values"})
    if not verify_only:
        manifest["count"] = len(records)
        _atomic_write(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    return {
        "status": "verified" if not failures else "invalid",
        "mode": "offline-verify" if verify_only else "recover-and-verify",
        "count": len(records), "valid_count": sum(r["status"] == "valid" for r in checks),
        "downloaded_count": sum(r["status"] == "downloaded" for r in outcomes),
        "cached_count": sum(r["status"] == "cached" for r in outcomes),
        "unique_original_hashes": unique, "benchmark_overlap_count": 0,
        "checks": checks, "errors": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="project root; manifest asset paths are relative to it")
    parser.add_argument("--manifest", type=Path, help="manifest to recover or verify; defaults to data manifest, then references/data-manifests/poster-references.json")
    parser.add_argument("--verify-only", action="store_true", help="offline checks only: never download, alter originals, or regenerate previews")
    parser.add_argument("--init-from-metadata", type=Path, help="initialize a new manifest from Paper2Poster list JSON or JSONL; refuses overwrite")
    parser.add_argument("--exclude-metadata", type=Path, help="benchmark titles; defaults to data/metadata/PosterBench.jsonl, then packaged references/data-manifests/PosterBench.jsonl; must exist")
    parser.add_argument("--count", type=int, default=50, help="initial library size (default50)")
    parser.add_argument("--workers", type=int, default=4, help="parallel downloads, capped at8")
    parser.add_argument("--report", type=Path, help="optional local JSON verification report; prints summary regardless")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    resolve = lambda p: p if p.is_absolute() else root / p
    local_manifest = root / "data/poster_references/manifest.json"
    packaged_manifest = root / "references/data-manifests/poster-references.json"
    manifest = resolve(args.manifest) if args.manifest else (local_manifest if local_manifest.exists() else packaged_manifest)
    if args.init_from_metadata and not args.manifest:
        manifest = local_manifest
    try:
        excluded_path = resolve(args.exclude_metadata) if args.exclude_metadata else root / "data/metadata/PosterBench.jsonl"
        if not excluded_path.exists() and not args.exclude_metadata:
            excluded_path = root / "references/data-manifests/PosterBench.jsonl"
        excluded_rows = _read_rows(excluded_path)
        excluded = [r["title"] for r in excluded_rows]
        if args.init_from_metadata:
            if args.verify_only:
                raise ValueError("--verify-only cannot initialize a library")
            if manifest.exists():
                raise ValueError("initialization refuses an existing manifest; recover it without --init-from-metadata")
            if args.count < 1:
                raise ValueError("--count must be positive")
            records = records_from_metadata(_read_rows(resolve(args.init_from_metadata)), excluded, args.count)
            if len(records) != args.count:
                raise ValueError("not enough eligible non-held-out source records")
            _atomic_write(manifest, (json.dumps({"format": "posfoxgen-poster-reference-library-v1", "count": len(records), "split": "development_reference", "records": records}, ensure_ascii=False, indent=2) + "\n").encode())
        elif not args.verify_only and not args.manifest and manifest == packaged_manifest:
            # Keep the tracked snapshot stable; recovery receipts live in data/.
            _atomic_write(local_manifest, packaged_manifest.read_bytes())
            manifest = local_manifest
        report = run_library(root, manifest, verify_only=args.verify_only, excluded_titles=excluded, workers=args.workers)
        if args.report:
            _atomic_write(resolve(args.report), (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
        print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False))
        return 0 if report["status"] == "verified" else 1
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
