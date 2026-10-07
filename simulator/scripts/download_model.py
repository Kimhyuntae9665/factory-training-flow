"""Download the official pinned optional model; no install or inference side effects."""
from pathlib import Path
import hashlib
import json
from huggingface_hub import snapshot_download

REPO='Qwen/Qwen2.5-1.5B-Instruct'
REV='989aa7980e4cf806f80c7fef2b1adb7bc71aa306'
dest=Path(__file__).resolve().parents[2]/'models/qwen2.5-1.5b'
print(f'Downloading optional model (~3.1 GB): {REPO} @ {REV} -> {dest}',flush=True)
snapshot_download(repo_id=REPO,revision=REV,local_dir=dest,
 allow_patterns=['*.safetensors','config.json','generation_config.json','tokenizer.json','tokenizer_config.json','vocab.json','merges.txt','LICENSE','README.md'],max_workers=3)
files=[]
for p in sorted(dest.glob('*')):
 if p.is_file():
  digest=hashlib.sha256()
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
  files.append({'name':p.name,'bytes':p.stat().st_size,'sha256':digest.hexdigest()})
(dest/'download_manifest.json').write_text(json.dumps({'model':REPO,'revision':REV,'files':files},indent=2),encoding='utf-8')
print('Pinned model download and SHA-256 manifest complete.',flush=True)
