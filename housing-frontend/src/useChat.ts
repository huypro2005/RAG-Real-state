import { useCallback, useRef, useState } from "react";
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

/**
 * Gom state hội thoại: tin nhắn, bộ tin đang hiện trên bản đồ, tin được chọn.
 * Tin được chọn định danh bằng `listing_id` (không phải `position`): các lượt khác nhau
 * đều có tin số 1–5, chọn thẻ của lượt cũ thì bản đồ chuyển về đúng bộ tin của lượt đó.
 */
export function useChat(mode: Mode) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(() => loadConversationId(mode));
  const [loading, setLoading] = useState(false);
  const [listings, setListings] = useState<ListingHit[]>([]);
  const [pois, setPois] = useState<MapFeature[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const nextId = useRef(0);
  // Tăng mỗi lần reset; phản hồi của lượt gửi trước reset sẽ bị bỏ qua.
  const generation = useRef(0);

  const append = useCallback((message: Omit<ChatMessage, "id">) => {
    const id = nextId.current++;
    setMessages((current) => [...current, { ...message, id }]);
  }, []);

  const showOnMap = useCallback((hits: ListingHit[], id: string | null) => {
    const current = generation.current;
    setListings(hits);
    setPois([]);
    fetchMap(hits.map((hit) => hit.listing_id), id)
      .then((data) => {
        if (generation.current !== current) return;
        // POI quanh tin + địa điểm có tên đang lọc (vẽ vòng bán kính)
        setPois(data.features.filter((feature) => feature.properties.kind !== "listing"));
      })
      .catch(() => {
        // Bản đồ vẫn có marker tin; chỉ thiếu POI.
      });
  }, []);

  /** Chọn một tin; nếu nó thuộc lượt khác với bộ đang hiện thì đổi bản đồ sang bộ đó. */
  const select = useCallback(
    (hit: ListingHit, group: ListingHit[]) => {
      if (!listings.some((item) => item.listing_id === hit.listing_id)) {
        showOnMap(group, conversationId);
      }
      setSelected(hit.listing_id);
    },
    [conversationId, listings, showOnMap],
  );

  const remember = useCallback(
    (id: string) => {
      setConversationId(id);
      saveConversationId(mode, id);
    },
    [mode],
  );

  const send = useCallback(
    async (text: string) => {
      const current = generation.current;
      append({ role: "user", text });
      setLoading(true);
      try {
        if (mode === "prediction") {
          const turn = await sendPrediction(text, conversationId);
          if (generation.current !== current) return;
          remember(turn.conversation_id);
          // answer chứa câu hỏi/hướng dẫn tiếp theo; summary chỉ là dòng tóm tắt trường đã biết
          append({ role: "assistant", text: turn.answer, prediction: turn });
        } else {
          const result = await sendChat(text, conversationId);
          if (generation.current !== current) return;
          remember(result.conversation_id);
          append({ role: "assistant", text: result.summary, result });
          if (result.listings.length > 0) {
            setSelected(null);
            showOnMap(result.listings, result.conversation_id);
          }
        }
      } catch (error) {
        if (generation.current !== current) return;
        const reason = error instanceof Error ? error.message : "Lỗi không xác định.";
        append({ role: "assistant", text: `Không gửi được tin nhắn. ${reason}`, isError: true });
      } finally {
        if (generation.current === current) setLoading(false);
      }
    },
    [append, conversationId, mode, remember, showOnMap],
  );

  const reset = useCallback(async () => {
    generation.current += 1;
    const id = conversationId;
    saveConversationId(mode, null);
    setConversationId(null);
    setMessages([]);
    setListings([]);
    setPois([]);
    setSelected(null);
    setLoading(false);
    if (id) {
      try {
        await (mode === "prediction" ? resetPrediction : resetConversation)(id);
      } catch {
        // Dù /reset lỗi, giao diện đã xóa để người dùng bắt đầu lại.
      }
    }
  }, [conversationId, mode]);

  return { messages, loading, listings, pois, selected, setSelected, select, send, reset };
}
