"""Real-file contracts for the reference downloader; no model services."""
import hashlib
import importlib.util
import json
from pathlib import Path
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
from urllib.request import Request

import pytest
from PIL import Image


def module():
    path = Path(__file__).resolve().parents[1] / "scripts/reference_library.py"
    assert path.is_file(), "reusable reference-library downloader is not implemented"
    spec = importlib.util.spec_from_file_location("reference_library", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def poster(tmp_path):
    source = tmp_path / "data/poster_references/poster-001/original.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (640, 480), "white").save(source)
    raw = source.read_bytes()
    record = {
        "id": "poster-001", "title": "Source-grounded Poster",
        "source_url": "https://neurips.cc/media/PosterPDFs/test/1.png",
        "original_path": str(source.relative_to(tmp_path)),
        "preview_path": "data/poster_references/poster-001/preview.png",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "width": 640, "height": 480,
    }
    return source, raw, record


@contextmanager
def local_http(raw):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/poster.png"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_offline_verification_rejects_hash_mismatch(tmp_path):
    lib = module()
    source, raw, record = poster(tmp_path)
    record["sha256"] = "0" * 64
    report = lib.verify_record(record, tmp_path)
    assert report["status"] == "invalid"
    assert "sha256" in report["error"].lower()


@pytest.mark.parametrize("unsafe", ["../outside.png", "/tmp/outside.png"])
def test_manifest_path_escape_is_rejected(tmp_path, unsafe):
    lib = module()
    _, _, record = poster(tmp_path)
    record["original_path"] = unsafe
    with pytest.raises(ValueError, match="(relative|outside|escape)"):
        lib.validate_record(record, tmp_path)


def test_symlink_escape_is_rejected(tmp_path):
    lib = module()
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="(outside|escape)"):
        lib.safe_path(tmp_path, "link/secret.png")


def test_metadata_excludes_normalized_benchmark_titles():
    lib = module()
    rows = [
        {"title": "A Result: Better Evidence!", "image_url": "https://icml.cc/a.png"},
        {"title": "An unrelated study", "image_url": "https://iclr.cc/b.png"},
    ]
    records = lib.records_from_metadata(rows, ["a result better evidence"], limit=50)
    assert [r["title"] for r in records] == ["An unrelated study"]
    assert records[0]["id"] == "poster-002"


def test_restore_uses_original_source_and_validates_before_write(tmp_path):
    lib = module()
    source, raw, record = poster(tmp_path)
    source.unlink()
    requested = []
    with local_http(raw) as fixture_url:
        def fetcher(source_url):
            requested.append(source_url)
            return urlopen(fixture_url).read()

        restored = lib.restore_record(record, tmp_path, fetcher=fetcher)
    assert requested == [record["source_url"]]
    assert restored["status"] == "downloaded"
    assert source.read_bytes() == raw
    assert (tmp_path / record["preview_path"]).exists()


def test_bad_download_does_not_replace_original(tmp_path):
    lib = module()
    source, raw, record = poster(tmp_path)
    record["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="sha256"):
        lib.restore_record(record, tmp_path, fetcher=lambda _: raw)
    assert source.read_bytes() == raw


@pytest.mark.parametrize("url", [
    "http://neurips.cc/a.png", "https://neurips.cc.attacker.example/a.png",
    "https://user:pass@neurips.cc/a.png", "file:///tmp/poster.png",
    "https://example.org/poster.png", "https://neurips.cc:444/a.png",
])
def test_source_policy_only_accepts_official_https_hosts(url):
    with pytest.raises(ValueError, match="(HTTPS|official|credentials|port)"):
        module().validate_source_url(url)


def test_existing_manifest_can_be_verified_without_network(tmp_path, monkeypatch):
    lib = module()
    _, _, record = poster(tmp_path)
    Image.new("RGB", (640, 480), "white").save(tmp_path / record["preview_path"])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"records": [record], "count": 1}))
    def no_network(*args, **kwargs):
        pytest.fail("verify-only attempted network access")
    monkeypatch.setattr(lib, "fetch_official", no_network)
    report = lib.run_library(tmp_path, manifest, verify_only=True)
    assert report["status"] == "verified"
    assert report["valid_count"] == 1
    assert report["downloaded_count"] == 0


def test_packaged_manifests_support_default_offline_cli(tmp_path):
    lib = module()
    _, _, record = poster(tmp_path)
    Image.new("RGB", (640, 480), "white").save(tmp_path / record["preview_path"])
    packaged = tmp_path / "references/data-manifests"
    packaged.mkdir(parents=True)
    (packaged / "poster-references.json").write_text(json.dumps({"records": [record], "count": 1}))
    (packaged / "PosterBench.jsonl").write_text(json.dumps({"title": "Different held-out paper"}) + "\n")
    assert lib.main(["--root", str(tmp_path), "--verify-only"]) == 0
    assert not (tmp_path / "data/poster_references/manifest.json").exists()


def test_redirects_cannot_leave_official_host_whitelist():
    lib = module()
    with pytest.raises(ValueError, match="official"):
        lib._OfficialRedirects().redirect_request(
            Request("https://neurips.cc/one.png"), None, 302, "Found", {},
            "https://example.org/two.png",
        )


def test_initialization_writes_runtime_manifest_not_packaged_snapshot(tmp_path, monkeypatch):
    lib = module()
    _, raw, _ = poster(tmp_path)
    packaged = tmp_path / "references/data-manifests"
    packaged.mkdir(parents=True)
    metadata = packaged / "paper2poster-100.json"
    metadata.write_text(json.dumps([{
        "title": "New paper", "image_url": "https://neurips.cc/original.png",
        "paper_url": "https://openreview.net/pdf?id=test",
    }]))
    (packaged / "PosterBench.jsonl").write_text(json.dumps({"title": "Excluded paper"}) + "\n")
    monkeypatch.setattr(lib, "fetch_official", lambda _: raw)
    assert lib.main(["--root", str(tmp_path), "--init-from-metadata", str(metadata), "--count", "1"]) == 0
    assert (tmp_path / "data/poster_references/manifest.json").is_file()
    assert not (packaged / "poster-references.json").exists()
