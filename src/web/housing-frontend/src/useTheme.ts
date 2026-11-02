import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "housing-theme";

function stored(): Theme | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // trình duyệt chặn localStorage: chạy theo hệ điều hành
  }
}

const systemTheme = (): Theme => (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");

/** Giao diện sáng/tối: mặc định theo hệ điều hành, người dùng bấm nút thì ghi đè và nhớ lại. */
export function useTheme() {
  const [explicit, setExplicit] = useState<Theme | null>(stored);
  const [system, setSystem] = useState<Theme>(systemTheme);

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onChange = () => setSystem(systemTheme());
    query?.addEventListener("change", onChange);
    return () => query?.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (explicit) document.documentElement.dataset.theme = explicit;
    else delete document.documentElement.dataset.theme;
  }, [explicit]);

  const theme = explicit ?? system;
  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setExplicit(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // Không lưu được thì lần sau theo hệ điều hành.
    }
  }, [theme]);

  return { theme, toggle };
}
