"""Download pinned official BGE assets and verify their published content hashes."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'backend/.runtime_reports/rag-model-manifest.json'
MODELS = {
    'bge-m3': ('5617a9f61b028005a4858fdac845db406aefb181', 'embeddings', (
        'config.json', 'config_sentence_transformers.json', 'modules.json',
        'sentence_bert_config.json', '1_Pooling/config.json',
        'sentencepiece.bpe.model', 'special_tokens_map.json', 'tokenizer.json',
        'tokenizer_config.json', 'pytorch_model.bin',
    )),
    'bge-reranker-v2-m3': ('953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e', 'rerankers', (
        'config.json', 'sentencepiece.bpe.model', 'special_tokens_map.json',
        'tokenizer.json', 'tokenizer_config.json', 'model.safetensors',
    )),
}

def digest(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()

def valid(path, info):
    if not path.is_file() or path.stat().st_size != info['size']:
        return False
    expected = info.get('lfs', {}).get('sha256')
    if expected:
        return digest(path) == expected
    content = path.read_bytes()
    return hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() == info['blobId']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proxy', help='Optional proxy for this download process only')
    args = parser.parse_args()
    manifest = {'models': []}
    for model, (revision, category, files) in MODELS.items():
        with urllib.request.urlopen(f'https://huggingface.co/api/models/BAAI/{model}/revision/{revision}?blobs=true', timeout=45) as response:
            metadata = json.load(response)
        assert metadata['sha'] == revision
        siblings = {item['rfilename']: item for item in metadata['siblings']}
        folder = ROOT / 'data/models' / category / model
        record = {'name': model, 'revision': revision, 'files': []}
        for name in files:
            info = siblings[name]
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f'https://huggingface.co/BAAI/{model}/resolve/{revision}/{name}'
            if not valid(target, info):
                if target.exists():
                    raise RuntimeError(f'Existing unverified asset preserved: {target}')
                pending = target.with_name(target.name + '.part')
                print(f'Downloading {model}/{name}: {info["size"]:,} bytes', flush=True)
                command = ['curl.exe']
                if args.proxy:
                    command += ['--proxy', args.proxy]
                subprocess.run(command + [
                    '--fail', '--location', '--silent', '--show-error',
                    '--retry', '3', '--retry-all-errors', '--connect-timeout', '20',
                    '--speed-time', '60', '--speed-limit', '1024', '--max-time', '1800', '--continue-at', '-', '--output', str(pending),
                    url + f'?download=true&local_setup={int(time.time())}',
                ], check=True)
                if not valid(pending, info):
                    raise RuntimeError(f'Model size/hash mismatch: {pending}')
                pending.replace(target)
            record['files'].append({'name': name, 'size': info['size'], 'sha256': digest(target), 'url': url})
            print(f'Verified {model}/{name}', flush=True)
        manifest['models'].append(record)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('All local BGE assets verified.', flush=True)

if __name__ == '__main__':
    main()
