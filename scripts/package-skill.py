#!/usr/bin/env python3
"""Package the standalone skill, including built web assets when present."""

import argparse
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
skill = root / "skills/cloud-servers"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--install-to",
    type=Path,
    help="Copy the ComputeMate Skill (cloud-servers) into this explicit skills directory; refuses to overwrite",
)
args = parser.parse_args()
if args.install_to:
    target = args.install_to.expanduser() / skill.name
    shutil.copytree(
        skill,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    print(target)
else:
    output = root / "dist/computemate-skill.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(skill.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
                and not any(part.endswith(".egg-info") for part in path.parts)
            ):
                archive.write(path, Path(skill.name) / path.relative_to(skill))
    shutil.copy2(output, root / "dist/cloud-servers-skill.zip")
    print(output)
