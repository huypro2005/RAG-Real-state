import { useState } from "react";
import type { Mode } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { MapView } from "./components/MapView";
import { useChat } from "./useChat";

export function App() {
  const [mode, setMode] = useState<Mode>("recommendation");
  // Mỗi mode giữ hội thoại riêng; đổi mode không mất lịch sử của mode kia.
  const recommend = useChat("recommendation");
  const predict = useChat("prediction");
  const chat = mode === "prediction" ? predict : recommend;

  return (
    <main className="layout">
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
  );
}
