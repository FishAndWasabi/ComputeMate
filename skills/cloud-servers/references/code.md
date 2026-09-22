# Remote code and transfers

Register a project with explicit server placements:

```bash
computemate --json project add --id model --data '{"name":"Model","local_path":"/home/me/model","placements":[{"server":"gpu01","path":"/workspace/model","environment":"torch"}]}'
computemate --json project status model --server gpu01
computemate --json fs list gpu01 --path /workspace/model --limit 50
computemate --json fs search gpu01 --path /workspace/model --pattern 'def train' --limit 30
computemate --json fs read gpu01 --path /workspace/model/train.py --start 1 --end 100
```

Remote paths are literal Shell-escaped paths; prefer absolute paths. `~` is not expanded inside quoted paths. Search uses `rg`, falling back to recursive `grep`. Large outputs are bounded; `truncated` indicates incomplete results. Directory listings use Linux `find`.

`fs read` returns the requested text and SHA-256 of the entire file when available. `fs patch` uses `git apply --check` followed by application under a cooperative project lock. It also works in a non-Git directory for contextual patches. Optional `--expected-revision` compares the Git HEAD; `--expected-hashes` maps paths to expected hashes. Checksum/revision mismatch, conflicting context, or an existing patch lock returns `conflict`.

```bash
computemate --json fs patch gpu01 --cwd /workspace/model --patch-file change.patch \
  --expected-hashes '{"train.py":"<sha256-from-read>"}'
```

The cooperative lock coordinates this tool's patch operations. Other editors do not honor it. Inspect and re-read when another tool changes the same files; the patch operation does not claim exclusive ownership of the repository.

Rsync is one-way and defaults to preview. A trailing slash on a directory means its contents. Declare exclusions appropriate to the project; the tool does not silently exclude datasets or weights you requested.

```bash
computemate --json sync gpu01 --local ./model/ --remote /workspace/model/ \
  --direction push --exclude '[".git/",".venv/","data/","outputs/"]'
computemate --json sync gpu01 --local ./model/ --remote /workspace/model/ \
  --direction push --exclude '[".git/",".venv/","data/","outputs/"]' --apply
computemate --json transfer get gpu01 --path /workspace/model/metrics.json --local ./metrics.json
computemate --json transfer put gpu01 --local ./config.yaml --path /workspace/model/config.yaml
```

`--delete` is available only as an explicit rsync option. Omit it to preserve destination extras. Transfers use SSH options from the registered server. No automatic bidirectional merge or transfer retry is performed.
