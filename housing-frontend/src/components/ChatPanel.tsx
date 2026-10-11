import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import type { Mode } from "../api";
import type { ChatMessage } from "../useChat";
import { MessageBubble } from "./MessageBubble";

interface Props {
  mode: Mode;
  onMode: (mode: Mode) => void;
  messages: ChatMessage[];
  loading: boolean;
  selected: number | null;
  onSend: (text: string) => void;
  onReset: () => void;
  onSelect: (position: number) => void;
}

const MODES: [Mode, string][] = [
  ["recommendation", "Gợi ý"],
  ["prediction", "Dự đoán giá"],
];

export function ChatPanel({ mode, onMode, messages, loading, selected, onSend, onReset, onSelect }: Props) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
    // Cần thêm thông tin từ người dùng thì đưa con trỏ về ô nhập.
    if (last?.result?.status === "need_clarification") {
      inputRef.current?.focus();
    }
  }, [messages.length, loading, last]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
    setDraft("");
    onSend(text);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <section className="chat">
      <header className="chat__header">
        <h1>Gợi ý bất động sản TP.HCM</h1>
        <div role="group" aria-label="Chế độ" className="modes">
          {MODES.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={mode === value}
              className={`btn btn--ghost${mode === value ? " btn--on" : ""}`}
              onClick={() => onMode(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <button type="button" className="btn btn--ghost" onClick={onReset}>
          Tìm lại từ đầu
        </button>
      </header>
      <div className="chat__list">
        {messages.length === 0 && (
          <p className="chat__empty">
            {mode === "prediction"
              ? 'Mô tả nhà cần định giá, ví dụ "Nhà 60m2 Gò Vấp, 3 phòng ngủ".'
              : 'Hãy mô tả nhà bạn cần, ví dụ "Căn hộ Quận 7 dưới 3 tỷ".'}
          </p>
        )}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            selected={selected}
            onSelect={onSelect}
            onRelax={onSend}
          />
        ))}
        {loading && <p className="chat__loading">Đang xử lý…</p>}
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
