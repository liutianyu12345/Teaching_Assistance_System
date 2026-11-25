export type Row = Record<string, any>;
export type User = {
  id: string;
  username: string;
  name: string;
  role: string;
  group_id: string;
  classes: string[];
};
export const roleNames: Record<string, string> = {
  teacher: "任课教师",
  lead: "教研组长",
  student: "学生",
  reviewer: "资源审核员",
  admin: "系统管理员",
};
export async function api(path: string, method = "GET", body?: unknown) {
  const options: RequestInit = { method, credentials: "same-origin" };
  if (body instanceof FormData) options.body = body;
  else if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const response = await fetch("/api" + path, options);
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    if (response.status === 401 && !["/me", "/login"].includes(path))
      window.dispatchEvent(new Event("session-expired"));
    const detail = data.detail;
    throw Object.assign(
      new Error(
        typeof detail === "string"
          ? detail
          : detail?.message || "请检查填写的内容",
      ),
      { detail, status: response.status },
    );
  }
  return response.json();
}
export async function task(
  kind: string,
  input: Row,
  progress?: (j: Row) => void,
) {
  const { id } = await api("/jobs/" + kind, "POST", input);
  return new Promise<Row>((resolve, reject) => {
    const stream = new EventSource("/api/jobs/" + id + "/stream");
    let retry: ReturnType<typeof setTimeout>;
    function finish(j: Row) {
      progress?.(j);
      if (["完成", "失败", "已取消"].includes(j.state)) {
        stream.close();
        clearTimeout(retry);
        if (j.state === "完成") resolve(j);
        else reject(new Error(j.error || j.state));
        return true;
      }
      return false;
    }
    stream.onmessage = (e) => finish(JSON.parse(e.data));
    stream.onerror = () => {
      stream.close();
      const poll = async () => {
        try {
          if (!finish(await api("/jobs/" + id))) retry = setTimeout(poll, 800);
        } catch (e) {
          reject(e);
        }
      };
      void poll();
    };
  });
}
export const dateText = (s: string) =>
  new Date(s).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
export const token = () => crypto.randomUUID();
