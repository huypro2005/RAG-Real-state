import { useCallback, useState } from "react";
import { fetchMap, resetConversation, resetPrediction, sendChat, sendPrediction } from "./api";
import type { ChatTurnResult, ListingHit, MapFeature, Mode, PredictionTurn } from "./api";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  result?: ChatTurnResult;
  prediction?: PredictionTurn;
  isError?: boolean;
}

const storageKey = (mode: Mode) => `housing.conversation_id.${mode}`;

// sessionStorage có thể bị chặn (chế độ riêng tư) nên mọi truy cập đều bọc try/catch.
function loadConversationId(mode: Mode): string | null {
  try {
    return sessionStorage.getItem(storageKey(mode));
  } catch {
    return null;
  }
}

function saveConversationId(mode: Mode, id: string | null): void {
  try {
    if (id) {
      sessionStorage.setItem(storageKey(mode), id);
    } else {
      sessionStorage.removeItem(storageKey(mode));
    }
  } catch {
    // Không lưu được thì chỉ mất khả năng giữ hội thoại sau khi tải lại trang.
  }
}

/** Gom state hội thoại: tin nhắn, kết quả đang hiện trên bản đồ, tin được chọn. */
export function useChat(mode: Mode) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(() => loadConversationId(mode));
  const [loading, setLoading] = useState(false);
  const [listings, setListings] = useState<ListingHit[]>([]);
  const [pois, setPois] = useState<MapFeature[]>([]);
  const [selected, setSelected] = useState<number | null>(null);

  const append = useCallback((message: Omit<ChatMessage, "id">) => {
    setMessages((current) => [...current, { ...message, id: current.length }]);
  }, []);

  const loadPois = useCallback(async (hits: ListingHit[], id: string) => {
    try {
      const data = await fetchMap(hits.map((hit) => hit.listing_id), id);
      // POI quanh tin + địa điểm có tên đang lọc (vẽ vòng bán kính)
      setPois(data.features.filter((feature) => feature.properties.kind !== "listing"));
    } catch {
      setPois([]); // Bản đồ vẫn có marker tin; chỉ thiếu POI.
    }
  }, []);

  const remember = useCallback(
    (id: string) => {
      setConversationId(id);
      saveConversationId(mode, id);
    },
    [mode],
  );

  const send = useCallback(
    async (text: string) => {
      append({ role: "user", text });
      setLoading(true);
      try {
        if (mode === "prediction") {
          const turn = await sendPrediction(text, conversationId);
          remember(turn.conversation_id);
          // answer chứa câu hỏi/hướng dẫn tiếp theo; summary chỉ là dòng tóm tắt trường đã biết
          append({ role: "assistant", text: turn.answer, prediction: turn });
        } else {
          const result = await sendChat(text, conversationId);
          remember(result.conversation_id);
          append({ role: "assistant", text: result.summary, result });
          if (result.listings.length > 0) {
            setListings(result.listings);
            setSelected(null);
            void loadPois(result.listings, result.conversation_id);
          }
        }
      } catch (error) {
        const reason = error instanceof Error ? error.message : "Lỗi không xác định";
        append({ role: "assistant", text: `Không gửi được tin nhắn. ${reason}`, isError: true });
      } finally {
        setLoading(false);
      }
    },
    [append, conversationId, loadPois, mode, remember],
  );

  const reset = useCallback(async () => {
    if (conversationId) {
      try {
        await (mode === "prediction" ? resetPrediction : resetConversation)(conversationId);
      } catch {
        // Dù /reset lỗi vẫn xóa phía giao diện để người dùng bắt đầu lại.
      }
    }
    saveConversationId(mode, null);
    setConversationId(null);
    setMessages([]);
    setListings([]);
    setPois([]);
    setSelected(null);
  }, [conversationId, mode]);

  return { messages, loading, listings, pois, selected, setSelected, send, reset };
}
