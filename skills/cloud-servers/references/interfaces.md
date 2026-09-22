# Results, artifacts and visual interfaces

Every operation is available in the CLI, the browser tool panel and the VS Code tool panel. Shared operation descriptions drive all three clients. Call `operations` to inspect the current names, fields, defaults and entity schemas.

Machine-readable result:

```json
{
  "schema_version": 1,
  "ok": true,
  "data": {},
  "error": null,
  "meta": {"observed_at": "2026-09-22T00:00:00+00:00"}
}
```

On failure, `ok` is false, `data` is null and `error` contains `code`, `message`, and optional `details`. CLI exits nonzero. Useful codes include `invalid_argument`, `not_found`, `conflict`, `missing_dependency`, `connection_failed`, `command_failed`, `timeout`, and `uncertain`. `probe` represents unreachable hosts in its successful result (`reachable: false`) while preserving cached observations; inspect observation-level errors too.

To bypass Shell argument construction, use JSON stdin:

```bash
printf '%s' '{"operation":"fs.read","arguments":{"server":"gpu01","path":"/workspace/model/train.py","start":1,"end":40}}' \
  | cloud-servers rpc
```

`rpc` handles one request and exits. It is also the VS Code transport. File-suffixed arguments (`--data-file`, `--script-file`, `--patch-file`, `--document-file`, `--argv-file`, `--expected-hashes-file`) read UTF-8; `-` means stdin.

Artifacts store pointers and optional metadata, not copies of large experiment files:

```bash
computemate --json artifact add --id baseline --data '{"name":"Baseline checkpoint","server":"gpu01","project":"model","path":"/workspace/model/outputs/model.pt","type":"checkpoint","native_ref":{"backend":"tmux","native_id":"train-baseline"}}'
computemate --json artifact list --server gpu01
computemate --json artifact fetch baseline --local ./model.pt
```

Use `computemate serve` for the browser interface. Open its printed `http://127.0.0.1:PORT/#token=...` URL. Web assets must be present (release archives include them; source checkouts build them with `npm ci && npm run build`). The process runs only while needed; closing it does not stop remote tmux or Slurm activity.

Start the webpage from the intended project or with `computemate --workspace /path/to/project serve`. Its database is fixed for that server process; changing terminal directories does not switch an open page. The header displays the bound project, and snapshots include `workspace`; successful operation envelopes also include `meta.scope`. VS Code selects a workspace folder explicitly when multiple roots are open and keeps each panel bound to its selected folder.

The loopback HTTP adapter exposes authenticated `GET /api/v1/operations`, `GET /api/v1/snapshot`, and `POST /api/v1/invoke` with the same request shape as RPC. Send `Authorization: Bearer TOKEN`; browser origins must match the exact printed origin. Tokens stay out of URLs sent to the server by using the fragment.

The VS Code extension bundles the same scripts and UI. It runs locally, including when the editor has a Remote SSH workspace. It reads the same default inventory and does not start the browser server. Both visual clients include all operations in their toolboxes, including code patches and inventory editing.
