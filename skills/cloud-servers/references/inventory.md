# Inventory and observations

Initialize the intended project with `computemate init /path/to/project`; run from that directory or pass `--workspace /path/to/project`. `computemate scope` shows the selected project. IDs and all records are isolated between project databases.

Examples use `computemate`; substitute `python3 <skill-directory>/scripts/computemate.py` when using the standalone skill.

```bash
computemate --json group add --id lab --data '{"name":"GPU 实验组"}'
computemate --json server add --id gpu01 --data '{"name":"GPU 01","ssh":{"alias":"gpu-lab"},"groups":["lab"],"role":"compute","labels":["training"]}'
computemate --json server list --group lab --limit 20 --offset 0
computemate --json probe gpu01
computemate --json capabilities gpu01
computemate --json server select --group lab --min-gpus 2 --min-gpu-memory-mib 20000
```

`ssh` accepts `alias` or `host`, plus optional `port`, `user`, `identity_file` and `proxy_jump`. Normal OpenSSH config and known-host verification remain active. Noninteractive execution requires usable keys or ssh-agent authentication. First-time host trust or authentication setup can be completed with the user's normal SSH client.

Server roles are `compute`, `general` and `login`. Mark Slurm entry nodes as `login`; `server select` excludes them. `probe` samples `/proc`, `df`, optional NVIDIA tooling and available commands; it queries Slurm resources separately when `sinfo` is available. An absent GPU tool means unknown GPU information, not proof of no GPU.

Manual fields live in records; detected fields live in observations. Each observation has `observed_at`, `last_attempt`, `error`, and `stale`. Observations become stale after five minutes. Failed refreshes preserve previous data. `snapshot --refresh` explicitly connects to the listed hosts; ordinary `snapshot` reads the cache. `--watch 30 probe gpu01` polls only while that CLI process runs.

All manual collections have `add`, `get`, `list`, `update`, and `remove`. Updates merge top-level fields; nested objects/arrays replace the previous value. Use `--revision` for an explicit compare-and-swap update:

```bash
computemate --json server get gpu01
computemate --json server update gpu01 --revision 1 --data '{"purpose":"inference experiments"}'
computemate --json server remove gpu01 --revision 2
computemate --json server list --archived
```

Removal archives the record without touching the machine, files or related records. IDs cannot be reused. Export/import can restore archived entries via an explicit overwrite. Import validates references before writing, and all records commit together:

```bash
computemate --json inventory export > inventory.json
computemate --db ./new-inventory.sqlite3 --json inventory import --document-file inventory.json
```

Both the full export envelope and its `data` object can be imported. Existing IDs cause a conflict unless `--overwrite` is supplied. Exports include manual inventory, including archived entries, but exclude observations and native session references.
