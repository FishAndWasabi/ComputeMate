<div align="center">

<img src="docs/assets/computemate-icon.png" alt="ComputeMate icon" width="112" height="112" />

# ComputeMate

**English** | [简体中文](README.zh-CN.md)

**Less terminal hopping. More experiments.**

Your server sidekick. Your agent's compute toolkit.

Keep servers, code, environments, and experiment artifacts organized by project. Let your agent operate; keep the whole picture in view.

[Quick start](#quick-start) · [Ask your agent](#ask-your-agent) · [Visual interfaces](#see-whats-going-on) · [Usage guide (中文)](docs/usage.md) · [Feedback](https://github.com/FishAndWasabi/ComputeMate/issues)

`Agent Skill` · `Python 3.11+` · `SSH / tmux / Slurm` · `CLI / Web / VS Code`

</div>

## Your experiment hasn't started. You're already juggling servers.

Several machines. Several projects. Every morning, the same questions:

- Which server should I connect to? Which GPU has room?
- Is the code under `/workspace`, or that other directory from last week?
- Which Conda environment does this project use?
- Where did last night's tmux session, logs, and checkpoint end up?

**ComputeMate puts those scattered details in an inventory for each project, then gives your agent tools to act on them.**

Describe your goal. Your agent can inspect resources, access code, use existing environments, and work with native session and job tools. You can also inspect everything through the CLI, a local webpage, or VS Code.

## Six reasons to spend less time on server chores

| What you get | What it means in practice |
| --- | --- |
| 🧠 **Instructions and tools for your agent** | `SKILL.md` comes with executable scripts and JSON interfaces. Agents can inspect servers and perform operations over SSH. |
| 📁 **One project, one inventory** | Server records, environments, code locations, and artifacts stay with their project. Identical record IDs in different projects don't collide. |
| 🔌 **Bring your existing SSH setup** | Reuse aliases, keys, and jump hosts. Servers need no ComputeMate daemon. |
| 🛠️ **A common entry point for everyday work** | Read code, inspect Git, apply patches, preview syncs, retrieve files, and read logs with fewer one-off scripts. |
| 👀 **Useful to agents. Visible to you.** | CLI, web, and VS Code share the same operations. The Skill and scripts work independently of the webpage. |
| 🪶 **Start with a single server** | Local SQLite inventory; a Python core using only the standard library. Register one machine and add capabilities as you need them. |

## Ask your agent

Have an agent that can read Skills and run shell commands load the [ComputeMate Skill](skills/cloud-servers/SKILL.md). Then try requests like:

> "Check which GPU servers in this project are reachable. List candidates by available GPU memory and explain your choices."

> "Inspect the training code on gpu01. Read just the first 80 lines of the entry file, check Git status, then prepare a patch."

> "Preview the code sync. After syncing, launch the specified command in tmux using the existing environment. Give me the session name and log path."

> "Submit this Slurm script, keep the native Job ID, and check the queue and output log."

These are **example requests**. Actual operations depend on registered paths, existing environments, permissions, and the target machine's capabilities. The agent organizes experiment steps around your project requirements.

## Quick start

The client needs **Python 3.11+ and OpenSSH**. File sync uses `rsync`; Git, tmux, and Slurm are needed for their respective operations. Remote hosts use Linux and Bash. Use macOS or Linux as the client, or WSL on Windows.

### 1. Get the code and install the CLI

```bash
git clone https://github.com/FishAndWasabi/ComputeMate.git
cd ComputeMate
uv tool install .
```

This assumes `uv` is installed. If your shell cannot find `computemate`, run `uv tool update-shell` and open a new terminal.

Without `uv`, use Python's built-in virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
```

You can also skip CLI installation and run `python3 skills/cloud-servers/scripts/computemate.py --help` directly.

### 2. Give your experiment its own inventory

Run these commands in **your actual experiment project**. Replace `lab-gpu` with an SSH alias you can connect to.

For a first connection, run `ssh lab-gpu` from the same client to verify the host fingerprint and authentication, then exit back to your local shell. ComputeMate uses non-interactive SSH and does not prompt for passwords or host verification.

```bash
cd /path/to/your/experiment
computemate init
computemate server add --id gpu01 \
  --data '{"name":"Experiment node","ssh":{"alias":"lab-gpu"},"role":"compute"}'
computemate probe gpu01
computemate server list
```

The inventory lives in the project's `.cloud-servers/` directory. To work from elsewhere, select the project explicitly:

```bash
computemate --workspace /path/to/your/experiment --json snapshot
```

<details>
<summary>No server handy? Try the sample inventory</summary>

Run this from the ComputeMate repository. It imports demo records without connecting to any servers:

```bash
mkdir -p /tmp/computemate-demo
computemate init /tmp/computemate-demo
computemate --workspace /tmp/computemate-demo inventory import --document-file examples/inventory.json
computemate --workspace /tmp/computemate-demo server list
```

After building the webpage, use `/tmp/computemate-demo` as the project path in the launch command below. The sample SSH destinations are placeholders; replace them with your own connections before refreshing.

</details>

### 3. Connect the Skill to your agent

From this repository, copy the complete Skill into a directory your agent supports:

```bash
python3 scripts/package-skill.py --install-to /path/to/agent/skills
```

Alternatively, have your agent read [SKILL.md](skills/cloud-servers/SKILL.md) in the repository and use its scripts by relative path. Skill discovery depends on the agent host; the public scripts do not depend on any particular agent's tool names.

## See what's going on

| Interface | When to use it |
| --- | --- |
| **CLI** | Quick lookups and scripting. Readable text for people, `--json` for agents. |
| **Local webpage** | Browse server groups, GPU status, environments, and artifacts. Open a server's details to take action. |
| **VS Code** | View the same inventory inside your project workspace. Each project has its own binding; the Webview needs no web server. |

Build the frontend before using the webpage for the first time. Run from the ComputeMate repository with Node.js 20.19+:

```bash
npm ci
npm run build
python3 skills/cloud-servers/scripts/computemate.py \
  --workspace /path/to/your/experiment serve
```

Open the local URL printed in the terminal. The page shows the latest saved observations by default. Refresh to probe servers again; automatic refresh is optional.

If the port is occupied, add `--port 0` after `serve` to select a free port. Launch a separate page for each project; the header shows which project it belongs to.

To use the installed `computemate serve` command, reinstall after building: run `uv tool install --reinstall .` from the repository, or `python3 -m pip install --force-reinstall .` in your virtual environment. The standalone script above reads the repository's latest build directly.

Build the VS Code extension with `npm run package:vscode`, then use **Install from VSIX** to install `extensions/vscode/computemate-0.1.0.vsix`. Open your project folder and click **初始化此项目的台账** (Initialize this project's inventory) in the ComputeMate activity bar.

## From finding a machine to collecting results

```text
You / Agent
    │
    ▼
ComputeMate Skill + public scripts
    │
    ├── Project inventory: servers · environments · code paths · artifacts
    ├── SSH / rsync: queries · execution · code access · file transfers
    └── tmux / Slurm: native sessions · Job IDs · status · logs
```

| What you need | ComputeMate interfaces |
| --- | --- |
| Inspect machines and GPUs, find candidates | `server` / `probe` / `capabilities` |
| Locate code, read files, inspect Git, apply patches | `project` / `fs` |
| Discover, register, and use existing environments | `environment` / `exec` |
| Preview incremental sync, upload, or retrieve files | `sync` / `transfer` |
| Start background sessions, submit jobs, read logs | `tmux` / `slurm` |
| Record weights, checkpoints, metrics, and log locations | `artifact` |

A useful first command:

```bash
# Let your agent discover the available operations.
computemate --json operations
```

Find more commands in the [usage guide (中文)](docs/usage.md), or read the [Skill interface reference](skills/cloud-servers/references/interfaces.md) for API details.

## A few things to know

- Projects isolate **inventory records and their relationships**. Physical GPUs are still shared; candidate selection does not reserve resources.
- You or your agent organize training workflows, dependency installation, and environment creation. ComputeMate provides the server tools.
- tmux session names and Slurm Job IDs keep their native meaning. Uncertain execution or submission results are reported explicitly so you can inspect before retrying.
- Sync previews changes by default and preserves extra files at the destination. Removing a server archives its inventory record; it does not delete remote data.
- Resource records include observation timestamps. Failed connections retain the last results and flag their status, so cached data is distinguishable from fresh observations.

Validation covers core interfaces, real loopback SSH, tmux, the webpage, and a real VS Code extension host, with additional trials on Linux GPU servers. Slurm currently uses fixtures and simulated responses; see the [validation record (中文)](VALIDATION.md) for the scope of real-cluster testing.

See the [first-use review (中文)](docs/usability-review.md) for installation and interface checks.

## Help make server chores smaller

Bring your own experiment to the [issue tracker](https://github.com/FishAndWasabi/ComputeMate/issues): training across machines, paper reproduction, evaluation, or shared lab servers.

If ComputeMate saves you even one "where did that checkpoint go?" search, give it a **Star ⭐** and share it with a friend still hunting through terminal tabs.
