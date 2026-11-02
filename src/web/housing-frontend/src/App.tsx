import { useEffect, useState } from "react";
import type { Mode } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { Dashboard } from "./components/dashboard/Dashboard";
import { MapView } from "./components/MapView";
import { useChat } from "./useChat";
import { useTheme } from "./useTheme";

type View = "chat" | "dashboard";

const VIEWS: [View, string][] = [
  ["chat", "Chat"],
  ["dashboard", "Dashboard mô hình"],
];

export function App() {
  const [view, setView] = useState<View>("chat");
  const [mode, setMode] = useState<Mode>("recommendation");
  const { theme, toggle } = useTheme();
  // Mỗi mode giữ hội thoại riêng; đổi mode không mất lịch sử của mode kia.
  const recommend = useChat("recommendation");
  const predict = useChat("prediction");
  const chat = mode === "prediction" ? predict : recommend;

  // Chat luôn được giữ trong DOM (ẩn bằng `hidden`) để không mất bản nháp/cuộn/bản đồ; Leaflet cần
  // sự kiện resize để đo lại khung khi hiện trở lại.
  useEffect(() => {
    if (view === "chat") window.dispatchEvent(new Event("resize"));
  }, [view]);

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="topbar__brand">Trợ lý bất động sản TP.HCM</h1>
        <nav className="tabs" aria-label="Màn hình">
          {VIEWS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`tabs__btn${view === value ? " tabs__btn--on" : ""}`}
              aria-current={view === value ? "page" : undefined}
              onClick={() => setView(value)}
            >
              {label}
            </button>
          ))}
        </nav>
        <button
          type="button"
          className="icon-btn"
          onClick={toggle}
          aria-label={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
          title={theme === "dark" ? "Giao diện sáng" : "Giao diện tối"}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            {theme === "dark" ? (
              <>
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
              </>
            ) : (
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
            )}
          </svg>
        </button>
      </header>
      <main className="layout" hidden={view !== "chat"}>
        <ChatPanel
          mode={mode}
          onMode={setMode}
          messages={chat.messages}
          loading={chat.loading}
          selected={recommend.selected}
          shown={recommend.listings}
          onSend={chat.send}
          onReset={chat.reset}
          onSelect={recommend.select}
        />
        <MapView
          listings={recommend.listings}
          pois={recommend.pois}
          selected={recommend.selected}
          onSelect={recommend.setSelected}
        />
      </main>
      <main className="page" hidden={view !== "dashboard"}>
        <Dashboard active={view === "dashboard"} />
      </main>
    </div>
  );
}
