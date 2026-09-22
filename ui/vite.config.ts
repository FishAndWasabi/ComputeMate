import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  base: "./",
  build: {
    outDir: fileURLToPath(
      new URL(
        "../skills/cloud-servers/scripts/cloud_servers/web_dist",
        import.meta.url,
      ),
    ),
    emptyOutDir: true,
  },
});
