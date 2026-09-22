export type Envelope<T = unknown> = {
  schema_version: number;
  ok: boolean;
  data: T;
  error: { code: string; message: string; details?: unknown } | null;
  meta: { observed_at: string };
};

declare global {
  interface Window {
    acquireVsCodeApi?: () => { postMessage: (value: unknown) => void };
  }
}

const vscode = window.acquireVsCodeApi?.();
const pending = new Map<
  string,
  { resolve: (r: Envelope) => void; reject: (e: Error) => void; timer: number }
>();
if (vscode)
  window.addEventListener("message", (event) => {
    const { id, response } = event.data || {};
    const request = pending.get(id);
    if (request) {
      clearTimeout(request.timer);
      request.resolve(response);
      pending.delete(id);
    }
  });

export function setToken(token: string) {
  sessionStorage.setItem("cloud-servers-token", token);
}
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.has("token")) {
  setToken(fragment.get("token")!);
  history.replaceState(null, "", location.pathname);
}

export const inVSCode = Boolean(vscode);

export async function invoke<T = unknown>(
  operation: string,
  args: Record<string, unknown> = {},
): Promise<Envelope<T>> {
  if (vscode) {
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(
        () => {
          pending.delete(id);
          reject(
            new Error(
              "等待接口响应超时；远端操作可能仍在运行，请先查询原生状态。",
            ),
          );
        },
        Math.max(300_000, (Number(args.timeout) || 60) * 1000 + 20000),
      );
      pending.set(id, {
        resolve: resolve as (r: Envelope) => void,
        reject,
        timer,
      });
      vscode.postMessage({ id, operation, arguments: args });
    });
  }
  const response = await fetch("/api/v1/invoke", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${sessionStorage.getItem("cloud-servers-token") || ""}`,
    },
    body: JSON.stringify({ operation, arguments: args }),
  });
  return await response.json();
}
