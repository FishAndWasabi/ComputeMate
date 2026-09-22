# Slurm over SSH

Register the SSH entry point with `role: "login"`. The login node's CPU, memory and GPU measurements describe that node only. Query compute resources using Slurm:

```bash
computemate --json slurm resources cluster-login
computemate --json slurm list cluster-login --user myuser
computemate --json slurm submit cluster-login --cwd /shared/model --script-file train.sbatch \
  --options '{"partition":"gpu","gpus":2,"cpus-per-task":8,"mem":"64G","time":"02:00:00"}'
```

The Agent/user authors the batch script, including environment activation and `srun` as appropriate to that cluster. The wrapper submits it through `sbatch --parsable`; if no shebang is present, it prepends `#!/bin/bash`.

Supported explicit sbatch options: `partition`, `account`, `qos`, `nodes`, `ntasks`, `cpus-per-task`, `gpus`, `mem`, `time`, `job-name`, `output`, `error`, `constraint`. Additional site-specific directives can be written in the script itself.

```bash
computemate --json slurm show cluster-login --job 12345
computemate --json slurm logs cluster-login --job 12345 --stream stdout --lines 100
computemate --json slurm cancel cluster-login --job 12345
```

Submission returns the native Job ID and optional cluster name. Queue results preserve native Slurm states. `show` queries both `scontrol` and `sacct`; unavailable accounting or a disappeared job stays unknown rather than being relabeled as success or failure. Inspect the returned evidence.

Logs come from `StdOut`/`StdErr` paths returned by `scontrol`. For completed jobs no longer known to `scontrol`, unresolved filename patterns, or logs on a filesystem inaccessible to the SSH entry node, supply an explicit accessible `--path` or perform the needed transfer.

Cancellation accepts a numeric Job ID or a numeric array task ID. Federated-cluster management is outside v1: use the appropriate registered entry point for the cluster returned by submission.

An interrupted or unparseable submission returns `uncertain` and is not retried. Query `squeue` and accounting, using your script's job name and timing to identify a possible submission. The wrapper provides no exactly-once guarantee across connection loss.
