import type { Envelope } from "./bridge";

type Row = Record<string, any>;

export function statusOf(server: Row) {
  const observation = server.observations?.hardware;
  return observation?.error
    ? "连接异常"
    : observation?.stale
      ? "已过期"
      : observation
        ? "可达"
        : "未探测";
}

export function presentResult(value: Envelope) {
  const payload = value.data as Row | null;
  const probeFailed = value.ok && payload?.reachable === false;
  const error = probeFailed ? payload?.observations?.hardware?.error : value.error;
  const failed = !value.ok || probeFailed;
  const data = (failed ? error?.details : payload) as Row | null;
  return {
    failed,
    data,
    title: error?.code === "uncertain"
      ? "执行结果不确定"
      : probeFailed
        ? "连接失败"
        : failed
          ? "操作未完成"
          : data?.preview
            ? "预览完成，尚未传输文件"
            : "操作完成",
    message: error?.message as string | undefined,
    guidance: error?.code === "uncertain"
      ? "远端操作可能已执行，请先查询原生会话、作业或目标文件，再决定是否重试。"
      : error?.code === "connection_failed"
        ? "请先在运行 ComputeMate 的机器上用 ssh 连接该地址，检查网络、密钥和主机指纹。"
        : undefined,
  };
}
