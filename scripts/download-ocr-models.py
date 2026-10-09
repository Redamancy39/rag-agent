"""Download pinned PaddleOCR inference assets and verify published hashes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data/models/ocr/paddleocr"
REPORT = ROOT / "backend/.runtime_reports/ocr-model-manifest.json"
FILES = ("config.json", "inference.json", "inference.pdiparams", "inference.yml")
MODELS = {
    "PP-OCRv5_mobile_det": "0d63e78e2b680928f6b1747d76a08db6e645efb7",
    "PP-OCRv5_mobile_rec": "682f20538d8c086cb2128e5cfac775e6c4904e85",
}

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def git_blob_sha1(path):
    content = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    manifest = {"models": []}
    for model, revision in MODELS.items():
        api = f"https://huggingface.co/api/models/PaddlePaddle/{model}/revision/{revision}?blobs=true"
        with urllib.request.urlopen(api, timeout=45) as response:
            metadata = json.load(response)
        if metadata["sha"] != revision:
            raise RuntimeError(f"Unexpected revision for {model}")
        siblings = {item["rfilename"]: item for item in metadata["siblings"]}
        folder = ASSETS / model
        folder.mkdir(parents=True, exist_ok=True)
        record = {"name": model, "repository": "PaddlePaddle/" + model, "revision": revision, "files": []}
        for name in FILES:
            info = siblings[name]
            target = folder / name
            expected = info.get("lfs", {}).get("sha256")
            size = info["size"]
            def valid(candidate):
                return candidate.is_file() and candidate.stat().st_size == size and (
                    sha256(candidate) == expected if expected else git_blob_sha1(candidate) == info["blobId"]
                )
            url = f"https://huggingface.co/PaddlePaddle/{model}/resolve/{revision}/{name}"
            if not valid(target):
                if target.exists():
                    raise RuntimeError(f"Existing asset is not valid; preserved for inspection: {target}")
                pending = folder / (name + ".part")
                print(f"Downloading {model}/{name} ({size:,} bytes)", flush=True)
                subprocess.run(["curl.exe", "--fail", "--location", "--silent", "--show-error", "--retry", "3", "--connect-timeout", "20", "--max-time", "600", "--output", str(pending), url], check=True)
                if not valid(pending):
                    raise RuntimeError(f"Asset size or hash mismatch: {pending}")
                pending.replace(target)
            record["files"].append({"name":name,"size":size,"sha256":sha256(target),"url":url})
        manifest["models"].append(record)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Verified {model}", flush=True)
    print(f"Manifest: {REPORT}")

if __name__ == "__main__":
    main()
