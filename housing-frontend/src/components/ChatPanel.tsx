import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import type { ListingHit, Mode } from "../api";
import type { ChatMessage } from "../useChat";
import { MessageBubble } from "./MessageBubble";

interface Props {
  mode: Mode;
  onMode: (mode: Mode) => void;
  messages: ChatMessage[];
  loading: boolean;
  selected: string | null;
  shown: ListingHit[];
  onSend: (text: string) => void;
  onReset: () => void;
  onSelect: (hit: ListingHit, group: ListingHit[]) => void;
}

const MODES: [Mode, string][] = [
  ["recommendation", "Gợi ý"],
  ["prediction", "Dự đoán giá"],
];

// Câu mẫu bấm để gửi ngay khi hội thoại còn trống.
const EXAMPLES: Record<Mode, string[]> = {
  recommendation: ["Căn hộ Quận 7 dưới 3 tỷ", "Nhà riêng Gò Vấp tầm 5 tỷ", "Căn hộ 2 phòng ngủ gần bệnh viện"],
  prediction: ["Nhà riêng 60m2 Gò Vấp, 3 phòng ngủ", "Căn hộ 70m2 Quận 7, 2 phòng ngủ", "Đất 100m2 Thủ Đức, mặt tiền 5m"],
};

const COPY: Record<Mode, { intro: string; loading: string; reset: string }> = {
  recommendation: {
    intro: "Mô tả nhà bạn cần mua (khu vực, ngân sách, loại nhà…) hoặc thử một câu mẫu:",
    loading: "Đang tìm tin phù hợp…",
    reset: "Tìm lại từ đầu",
  },
  prediction: {
    intro: "Mô tả nhà cần định giá (loại nhà, quận, diện tích…) hoặc thử một câu mẫu:",
    loading: "Đang định giá…",
    reset: "Định giá căn khác",
  },
};

export function ChatPanel({ mode, onMode, messages, loading, selected, shown, onSend, onReset, onSelect }: Props) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  const copy = COPY[mode];
  // Chip câu mẫu, nút nới điều kiện, "Dự đoán giá ngay": không gửi chồng khi đang chờ phản hồi.
  const sendNow = (text: string) => {
    if (!loading) onSend(text);
  };

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
    // Cần thêm thông tin từ người dùng thì đưa con trỏ về ô nhập.
    if (last?.result?.status === "need_clarification" || last?.prediction?.status === "collecting") {
      inputRef.current?.focus();
    }
  }, [messages.length, loading, last]);

  useEffect(() => inputRef.current?.focus(), [mode]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
    setDraft("");
    onSend(text);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <section className="chat">
      <header className="chat__header">
        <h1>Trợ lý bất động sản TP.HCM</h1>
        <div className="chat__actions">
          <div role="group" aria-label="Chế độ" className="modes">
            {MODES.map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                className={`modes__btn${mode === value ? " modes__btn--on" : ""}`}
                onClick={() => onMode(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <button type="button" className="btn btn--ghost" onClick={onReset} disabled={messages.length === 0}>
            {copy.reset}
          </button>
        </div>
      </header>
      <div className="chat__list" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat__empty">
            <p>{copy.intro}</p>
            {EXAMPLES[mode].map((example) => (
              <button key={example} type="button" className="chip" onClick={() => sendNow(example)}>
                {example}
              </button>
            ))}
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            selected={selected}
            shown={shown}
            onSelect={onSelect}
            onSend={sendNow}
          />
        ))}
        {loading && (
          <p className="chat__loading">
            <span className="dots" aria-hidden="true"><i /><i /><i /></span>
            {copy.loading}
          </p>
        )}
        <div ref={endRef} />
      </div>
      <form className="chat__form" onSubmit={submit}>
        <textarea
          ref={inputRef}
          aria-label="Tin nhắn"
          rows={2}
          value={draft}
          placeholder="Nhập yêu cầu, Enter để gửi, Shift+Enter xuống dòng"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="btn" disabled={loading || !draft.trim()}>
          Gửi
        </button>
      </form>
    </section>
  );
}
