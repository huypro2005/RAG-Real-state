import type { PredictionTurn } from "../api";
import { FIELD_LABELS, formatDistance, formatField, formatPrice, formatPricePerM2, formatPriceRange } from "../format";

interface Props {
  turn: PredictionTurn;
  onSend: (text: string) => void;
}

/** Các trường đã biết / còn thiếu (lượt đang thu thập) và kết quả định giá (lượt đã dự đoán). */
export function PredictionCard({ turn, onSend }: Props) {
  const estimate = turn.prediction;
  const known = Object.entries(turn.fields).filter(
    (entry): entry is [string, string | number] => entry[1] !== null,
  );
  const area = typeof turn.fields.area === "number" ? turn.fields.area : 0;
  const range = estimate ? formatPriceRange(estimate.price_per_m2_low, estimate.price_per_m2_high, area) : null;
  if (known.length === 0 && !estimate && turn.status !== "ready") return null;

  return (
    <div className="price-card">
      {known.length > 0 && (
        <ul className="fields">
          {known.map(([key, value]) => (
            <li key={key} className="field">
              {FIELD_LABELS[key] ?? key}: <strong>{formatField(key, value)}</strong>
            </li>
          ))}
          {turn.missing.map((key) => (
            <li key={key} className="field field--missing">
              {FIELD_LABELS[key] ?? key}: còn thiếu
            </li>
          ))}
        </ul>
      )}
      {estimate && (
        <dl className="estimate">
          <dt>Giá ước tính</dt>
          <dd className="estimate__total">{formatPrice(estimate.total_price)}</dd>
          {range && (
            <>
              <dt>Khoảng tham khảo</dt>
              <dd>{range}</dd>
            </>
          )}
          <dt>Giá / m²</dt>
          <dd>{formatPricePerM2(estimate.price_per_m2)}</dd>
          {estimate.district_median_per_m2 !== null && (
            <>
              <dt>{estimate.median_by_type ? "Trung vị cùng loại trong quận" : "Trung vị quận"}</dt>
              <dd>{formatPricePerM2(estimate.district_median_per_m2)}</dd>
            </>
          )}
          <dt>Cách trung tâm</dt>
          <dd>{formatDistance(estimate.distance_to_center_km * 1000)}</dd>
        </dl>
      )}
      {estimate?.warnings?.map((warning) => (
        <p key={warning} className="warning">{warning}</p>
      ))}
      {turn.status === "ready" && (
        <button type="button" className="btn btn--small" onClick={() => onSend("ok")}>
          Dự đoán giá ngay
        </button>
      )}
    </div>
  );
}
