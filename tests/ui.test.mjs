import assert from "node:assert/strict";
import test from "node:test";
import { build } from "esbuild";

const bundle = await build({
  entryPoints: [new URL("../ui/src/presentation.ts", import.meta.url).pathname],
  bundle: true, write: false, platform: "node", format: "esm",
});
const { presentResult, statusOf } = await import(
  "data:text/javascript;base64," + Buffer.from(bundle.outputFiles[0].text).toString("base64")
);
const envelope = (data, error = null) => ({ ok: !error, data, error });

test("failed SSH probe never appears as a successful operation", () => {
  const value = presentResult(envelope({reachable: false, observations: {hardware: {
    error: {code: "connection_failed", message: "SSH connection failed", details: {stderr: "Connection refused", exit_code: 255}},
  }}}));
  assert.equal(value.failed, true);
  assert.equal(value.title, "连接失败");
  assert.equal(value.data.stderr, "Connection refused");
  assert.match(value.guidance, /ssh/);
});
test("failed remote commands expose their output and exit code", () => {
  const details = {stdout: "training started", stderr: "CUDA out of memory", exit_code: 7};
  const value = presentResult(envelope(null, {code: "command_failed", message: "Remote command exited unsuccessfully", details}));
  assert.equal(value.failed, true);
  assert.deepEqual(value.data, details);
});
test("uncertain execution tells users to inspect before retrying", () => {
  const value = presentResult(envelope(null, {code: "uncertain", message: "Disconnected"}));
  assert.equal(value.title, "执行结果不确定");
  assert.match(value.guidance, /先查询/);
});
test("sync preview is distinguished from a real transfer", () => {
  assert.equal(presentResult(envelope({preview:true, stdout:"code.py"})).title, "预览完成，尚未传输文件");
  assert.equal(presentResult(envelope({preview:false, stdout:"code.py"})).title, "操作完成");
});
test("cached status distinguishes failed probes from old successful observations", () => {
  assert.equal(statusOf({}), "未探测");
  assert.equal(statusOf({observations:{hardware:{stale:false}}}), "可达");
  assert.equal(statusOf({observations:{hardware:{stale:true}}}), "已过期");
  assert.equal(statusOf({observations:{hardware:{stale:true,error:{message:"offline"}}}}), "连接异常");
});
