import { useCallback, useEffect, useRef, useState } from "react";
import { fetchDashboardModel, fetchDashboardModels } from "./api";
import type { DashboardModelDetail, DashboardModelSummary } from "./api";
import { defaultVersion } from "./dashboard";

interface Load<T> {
  status: "idle" | "loading" | "ready" | "error";
  data?: T;
  error?: string;
}

const message = (error: unknown) => (error instanceof Error ? error.message : "Lỗi không xác định.");

/**
 * Trạng thái trang dashboard: danh sách phiên bản, phiên bản đang xem và chi tiết (charts) của nó.
 * Chi tiết được cache theo id phiên bản và luôn đi kèm id của chính nó, nên khi đổi phiên bản
 * giao diện không bao giờ trộn dữ liệu của hai phiên bản. Chỉ tải khi `enabled` (tab được mở).
 */
export function useDashboard(enabled: boolean) {
  const [list, setList] = useState<Load<DashboardModelSummary[]>>({ status: "idle" });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [compareId, setCompareId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Load<DashboardModelDetail>>({ status: "idle" });
  const cache = useRef(new Map<number, DashboardModelDetail>());
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setList((previous) => ({ status: "loading", data: previous.data }));
    fetchDashboardModels()
      .then((models) => {
        if (cancelled) return;
        setList({ status: "ready", data: models });
        setSelectedId((current) => (models.some((m) => m.id === current) ? current : defaultVersion(models)));
        setCompareId((current) => (models.some((m) => m.id === current) ? current : null));
      })
      .catch((error: unknown) => !cancelled && setList({ status: "error", error: message(error) }));
    return () => { cancelled = true; };
  }, [enabled, reloads]);

  const selected = list.data?.find((model) => model.id === selectedId);
  const hasCharts = selected?.has_charts ?? false;

  useEffect(() => {
    if (selectedId === null || !hasCharts) {
      setDetail({ status: "idle" });
      return;
    }
    const cached = cache.current.get(selectedId);
    if (cached) {
      setDetail({ status: "ready", data: cached });
      return;
    }
    let cancelled = false;
    // Giữ biểu đồ cũ mờ đi trong lúc tải bản mới (không nhấp nháy, không nhảy bố cục).
    setDetail((previous) => ({ status: "loading", data: previous.data }));
    fetchDashboardModel(selectedId)
      .then((data) => {
        cache.current.set(selectedId, data);
        if (!cancelled) setDetail({ status: "ready", data });
      })
      .catch((error: unknown) => !cancelled && setDetail({ status: "error", error: message(error) }));
    return () => { cancelled = true; };
  }, [selectedId, hasCharts, reloads]);

  /** Bỏ cache và tải lại cả danh sách lẫn chi tiết (vd. sau khi server dựng lại charts). */
  const reload = useCallback(() => {
    cache.current.clear();
    setReloads((count) => count + 1);
  }, []);

  return { list, selected, compareId, detail, setSelectedId, setCompareId, reload };
}
