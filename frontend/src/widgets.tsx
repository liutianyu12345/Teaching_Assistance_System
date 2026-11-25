import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type Row } from "./client";

export function useData(path: string, rev = 0) {
  const [state, setState] = useState<{
    path: string;
    data: any;
    error: string;
  }>({ path: "", data: null, error: "" });
  useEffect(() => {
    let live = true;
    if (path)
      api(path)
        .then((data) => {
          if (live) setState({ path, data, error: "" });
        })
        .catch((e) => {
          if (live) setState({ path, data: null, error: e.message });
        });
    return () => {
      live = false;
    };
  }, [path, rev]);
  return state.path === path ? state : { data: null, error: "" };
}
export type PageProps = {
  user: import("./client").User;
  rev: number;
  refresh: () => void;
  go: (page: string) => void;
  notify: (s: string) => void;
};
export function Action({
  children,
  run,
  kind = "",
  disabled = false,
}: {
  children: ReactNode;
  run: () => unknown;
  kind?: string;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      className={kind}
      disabled={disabled || busy}
      onClick={async () => {
        setBusy(true);
        try {
          await run();
        } catch (e) {
          window.dispatchEvent(
            new CustomEvent("notice", { detail: (e as Error).message }),
          );
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "处理中…" : children}
    </button>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function Pill({ v }: { v: string }) {
  return (
    <span
      className={
        "pill " +
        (["待审核", "草稿", "截止", "协作中"].includes(v)
          ? "amber"
          : ["失败", "已退回", "已撤回"].includes(v)
            ? "red"
            : "")
      }
    >
      {v}
    </span>
  );
}
export function Panel({
  title,
  tools,
  children,
}: {
  title: string;
  tools?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panelhead">
        <h2>{title}</h2>
        {tools}
      </div>
      {children}
    </section>
  );
}
export function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button aria-label="关闭" className="iconbtn" onClick={close}>
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function ErrorLine({ value }: { value?: string }) {
  return value ? (
    <p role="alert" className="err">
      {value}
    </p>
  ) : null;
}
export function Picker({
  items,
  id,
  set,
  label,
}: {
  items: Row[];
  id: string;
  set: (s: string) => void;
  label: string;
}) {
  return (
    <Field label={label}>
      <select value={id} onChange={(e) => set(e.target.value)}>
        {items.map((x) => (
          <option key={x.id} value={x.id}>
            {x.title || x.snapshot?.title} {x.class_id && " · " + x.class_id}{" "}
            {x.snapshot && " · V" + x.snapshot.lesson_rev}
          </option>
        ))}
      </select>
    </Field>
  );
}
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const shapes: Record<string, string> = {
    home: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    library: "M3 5h5v15H3z M10 5h4v15h-4z M16 6l4-1 3 14-4 1z",
    lesson: "M3 4h6q3 0 3 3v14q-1-3-4-3H3z M21 4h-6q-3 0-3 3v14q1-3 4-3h5z",
    classroom: "M3 4h18v13H3z M12 17v4 M7 22l5-3 5 3",
    practice: "M6 4h12v17H5V4z M9 3h5v3H9z M8 11l2 2 5-5 M8 17h7",
    chart: "M3 3v18h18 M7 16v-5 M12 16V6 M17 16V9",
    ai: "M12 2l2.3 6.6L21 11l-6.7 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z M20 2v4 M18 4h4",
    admin: "M12 2l8 4v5q0 7-8 11-8-4-8-11V6z M8 11l3 3 5-6",
    arrow: "M5 12h14 M14 7l5 5-5 5",
    exit: "M9 4H4v16h5 M9 12h12 M16 7l5 5-5 5",
    bolt: "M13 2L4 14h7l-1 8 10-13h-7z",
    jobs: "M4 5h16v14H4z M7 9h10 M7 13h6",
    book: "M3 4h6q3 0 3 3v14q-1-3-4-3H3z M21 4h-6q-3 0-3 3v14q1-3 4-3h5z",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinejoin="round"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d={shapes[name] || shapes.book} />
    </svg>
  );
}
