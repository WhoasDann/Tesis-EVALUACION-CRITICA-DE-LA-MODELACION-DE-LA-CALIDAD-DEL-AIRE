from pathlib import Path
import hashlib,json
def verificar(root):
    root=Path(root).resolve()
    for rel,digest in json.loads((root/'manifest.json').read_text(encoding='utf-8'))['files'].items():
        path=(root/rel).resolve();path.relative_to(root)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError(f'Hash incompatible: {rel}')
