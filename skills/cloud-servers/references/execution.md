# Environments, commands and tmux

Discover existing environments without installing anything or scanning the entire filesystem:

```bash
computemate --json environment discover gpu01 --paths '["/workspace/model/.venv"]'
computemate --json environment add --id torch --data '{"name":"PyTorch","server":"gpu01","type":"conda","selector":"torch"}'
```

Supported types: `system`; `conda` (name or absolute prefix); `venv` (absolute directory); `docker` (existing container name/ID for `docker exec`). Conda/CUDA discovery uses commands available in the SSH noninteractive PATH; absent results do not imply the software is uninstalled. Docker discovery reports containers and access warnings. Environment creation, container startup and dependency installation remain explicit Agent operations.

When noninteractive SSH cannot find `conda`, set the Conda environment's optional `conda_executable` to its existing absolute remote path (for example `/home/user/miniconda3/bin/conda`). The `selector` still identifies the environment name or prefix; shell startup files need no changes.

```bash
computemate --json exec gpu01 --cwd /workspace/model --environment torch \
  -- python train.py --epochs 3
computemate --json exec gpu01 --cwd /workspace/model --script-file diagnostics.sh --timeout 120
```

Exactly one of `argv` and `script` is required. `--` passes a command and its literal arguments. Script mode intentionally interprets Bash. `cwd` for Docker refers to a path inside the existing container. Nonzero command exit returns `command_failed`, with the original exit code, stdout and stderr in `error.details`. SSH failure or timeout during an operation returns `uncertain`; it cannot guarantee that the remote process stopped.

Use native tmux for long-running commands:

```bash
computemate --json tmux start gpu01 --name train-baseline --cwd /workspace/model \
  --environment torch -- python train.py
computemate --json tmux show gpu01 --name train-baseline
computemate --json tmux logs gpu01 --name train-baseline --lines 100
computemate --json tmux stop gpu01 --name train-baseline
```

Start returns `backend`, `native_id`, and `log_path`. Generated logs live in the remote `$XDG_STATE_HOME/cloud-servers` or `~/.local/state/cloud-servers`. The session retains a dead pane on completion so tmux's native exit status remains available. Stop uses `tmux kill-session`; it does not promise termination of processes that deliberately detached from that session. Logs remain on disk after stop.

`tmux list` also lists existing native sessions. For sessions started outside the tool, `tmux logs` captures the pane unless `--path` supplies a file. Pane history is bounded and is not a substitute for a persistent log. Duplicate names are errors; no session is overwritten or silently killed on start.

Local registration of a native handle is a convenience, not a job scheduler or durable job state machine. If the client disappears after remote creation, inspect native sessions before submitting again.
