import type { ChatMessage } from "../useChat";
import { formatDistance, formatPrice } from "../format";
import { ListingCard } from "./ListingCard";

interface Props {
  message: ChatMessage;
  selected: number | null;
  onSelect: (position: number) => void;
  onRelax: (text: string) => void;
  onSuggest: (text: string) => void;
  isLast: boolean;
}

export function MessageBubble({ message, selected, onSelect, onRelax, onSuggest, isLast }: Props) {
  const result = message.result;
  const estimate = message.prediction?.prediction;
  const classes = ["bubble", `bubble--${message.role}`];
  if (message.isError) classes.push("bubble--error");
  if (result?.status === "need_clarification") classes.push("bubble--hint");

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
      {estimate && (
        <dl className="price-card">
          <dt>Giá ước tính</dt>
          <dd>{formatPrice(estimate.total_price)}</dd>
          <dt>Giá / m²</dt>
          <dd>{formatPrice(estimate.price_per_m2)}/m²</dd>
          {estimate.district_median_per_m2 !== null && (
            <>
              <dt>Trung vị quận</dt>
              <dd>{formatPrice(estimate.district_median_per_m2)}/m²</dd>
            </>
          )}
          <dt>Cách trung tâm</dt>
          <dd>{formatDistance(estimate.distance_to_center_km * 1000)}</dd>
        </dl>
      )}
      {result?.listings.map((hit) => (
        <ListingCard
          key={hit.listing_id}
          hit={hit}
          selected={selected === hit.position}
          onSelect={onSelect}
        />
      ))}
      {result?.status === "no_results" &&
        result.relax_options.map((option) => (
          <button
            key={option.description}
            type="button"
            className="chip"
            onClick={() => onRelax(option.message)}
          >
            {option.description}
          </button>
        ))}
      {/* Chip chỉ ở tin cuối: bấm thì gửi nguyên văn như người dùng gõ */}
      {isLast &&
        (message.prediction?.suggestions ?? message.result?.suggestions)?.map((text) => (
          <button key={text} type="button" className="chip" onClick={() => onSuggest(text)}>
            {text}
          </button>
        ))}
    </div>
  );
}
