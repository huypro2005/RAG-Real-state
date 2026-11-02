import type { ListingHit } from "../api";
import type { ChatMessage } from "../useChat";
import { ListingCard } from "./ListingCard";
import { PredictionCard } from "./PredictionCard";

interface Props {
  message: ChatMessage;
  selected: string | null;
  shown: ListingHit[]; // bộ tin đang vẽ trên bản đồ; chỉ thẻ của bộ này được tô "đang chọn"
  onSelect: (hit: ListingHit, group: ListingHit[]) => void;
  onSend: (text: string) => void;
  isLast: boolean;
}

export function MessageBubble({ message, selected, shown, onSelect, onSend, isLast }: Props) {
  const { result, prediction } = message;
  const classes = ["bubble", `bubble--${message.role}`];
  if (message.isError) classes.push("bubble--error");
  if (result?.status === "need_clarification" || prediction?.status === "collecting") {
    classes.push("bubble--hint");
  }

  return (
    <div className={`message message--${message.role}`}>
      <div className={classes.join(" ")}>
        {result?.degraded && (
          <p className="banner">
            Kết quả chưa xếp theo ngữ nghĩa (dịch vụ embedding đang tắt)
          </p>
        )}
        <p className="bubble__text">{message.text}</p>
      </div>
      {prediction && prediction.status !== "out_of_scope" && (
        <PredictionCard turn={prediction} onSend={onSend} />
      )}
      {result?.listings.map((hit) => (
        <ListingCard
          key={hit.listing_id}
          hit={hit}
          selected={selected === hit.listing_id && result.listings === shown}
          onSelect={() => onSelect(hit, result.listings)}
        />
      ))}
      {result?.status === "no_results" &&
        result.relax_options.map((option) => (
          <button
            key={option.description}
            type="button"
            className="chip"
            onClick={() => onSend(option.message)}
          >
            {option.description}
          </button>
        ))}
      {/* Chip chỉ ở tin cuối: bấm thì gửi nguyên văn như người dùng gõ */}
      {isLast &&
        (message.prediction?.suggestions ?? message.result?.suggestions)?.map((text) => (
          <button key={text} type="button" className="chip" onClick={() => onSend(text)}>
            {text}
          </button>
        ))}
    </div>
  );
}
