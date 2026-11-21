import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

const KEY = "chat-width";
export const CHAT_DEFAULT = 440;
const CHAT_MIN = 320;
const MAP_MIN = 320;
const STEP = 24;

/** Giới hạn bề rộng chat: không hẹp hơn CHAT_MIN, chừa cho bản đồ ít nhất MAP_MIN. */
export function clampChatWidth(width: number, total: number): number {
  const max = Math.max(CHAT_MIN, total - MAP_MIN);
  return Math.round(Math.min(max, Math.max(CHAT_MIN, width)));
}

function readSaved(): number {
  try {
    const value = Number(localStorage.getItem(KEY));
    return Number.isFinite(value) && value > 0 ? value : CHAT_DEFAULT;
  } catch {
    return CHAT_DEFAULT;
  }
}

/**
 * Bề rộng khung chat kéo được bằng thanh chia (chuột, cảm ứng, phím mũi tên), nhớ trong localStorage.
 * Leaflet chỉ đo lại khung khi có sự kiện resize nên mỗi lần đổi bề rộng phát một sự kiện resize.
 */
export function useChatWidth() {
  const layoutRef = useRef<HTMLElement>(null);
  const [width, setWidth] = useState(readSaved);
  const [dragging, setDragging] = useState(false);

  const total = () => layoutRef.current?.clientWidth ?? window.innerWidth;

  const apply = useCallback((next: number) => {
    setWidth(clampChatWidth(next, layoutRef.current?.clientWidth ?? window.innerWidth));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, String(width));
    } catch {
      /* chế độ riêng tư: bỏ qua, chỉ không nhớ được */
    }
    window.dispatchEvent(new Event("resize"));
  }, [width]);

  // Cửa sổ thu nhỏ thì kéo chat về trong giới hạn.
  useEffect(() => {
    const onResize = () => setWidth((w) => clampChatWidth(w, total()));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const onPointerDown = (e: PointerEvent<HTMLElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
  };
  const onPointerMove = (e: PointerEvent<HTMLElement>) => {
    if (!dragging) return;
    const left = layoutRef.current?.getBoundingClientRect().left ?? 0;
    apply(e.clientX - left);
  };
  const onPointerUp = (e: PointerEvent<HTMLElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    setDragging(false);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    const moves: Record<string, number> = { ArrowLeft: -STEP, ArrowRight: STEP };
    if (e.key in moves) apply(width + moves[e.key]);
    else if (e.key === "Home") apply(CHAT_MIN);
    else if (e.key === "End") apply(total());
    else return;
    e.preventDefault();
  };

  return {
    layoutRef,
    width,
    dragging,
    splitter: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: onPointerUp,
      onKeyDown,
      onDoubleClick: () => apply(CHAT_DEFAULT),
      min: CHAT_MIN,
      max: Math.max(CHAT_MIN, total() - MAP_MIN),
    },
  };
}
