import { cp, mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { build } from "esbuild";

const extension = resolve("extensions/vscode");
await mkdir(resolve(extension, "dist"), { recursive: true });
await build({
  entryPoints: [resolve(extension, "src/extension.ts")],
  outfile: resolve(extension, "dist/extension.cjs"),
  bundle: true,
  platform: "node",
  format: "cjs",
  external: ["vscode"],
  target: "node20",
});
await rm(resolve(extension, "resources"), { recursive: true, force: true });
await mkdir(resolve(extension, "resources"), { recursive: true });
await cp(
  "skills/cloud-servers/scripts",
  resolve(extension, "resources/runtime"),
  {
    recursive: true,
    filter: (source) =>
      !source.includes("__pycache__") &&
      !source.includes(".egg-info") &&
      !source.includes("web_dist") &&
      !source.endsWith(".pyc"),
  },
);
await cp(
  "skills/cloud-servers/scripts/cloud_servers/web_dist",
  resolve(extension, "resources/web"),
  { recursive: true },
);
console.log("VS Code runtime and shared UI packaged.");
