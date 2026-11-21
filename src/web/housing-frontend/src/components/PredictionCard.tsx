import type { PredictionTurn } from "../api";
import {
  FIELD_LABELS, formatDistance, formatField, formatPrice, formatPricePerM2, formatPriceRange, priceBar,
} from "../format";

/** Số ngắn dưới thanh dải (triệu/m²): 55 -> "55", 62,46 -> "62,5". */
const formatNumberShort = (value: number) => (Math.round(value * 10) / 10).toString().replace(".", ",");

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
  const bar = estimate
    ? priceBar(estimate.price_per_m2, estimate.price_per_m2_low, estimate.price_per_m2_high, estimate.district_median_per_m2)
    : null;
  const medianLabel = estimate?.median_by_type ? "Trung vị cùng loại trong quận" : "Trung vị quận";
  if (known.length === 0 && !estimate && turn.status !== "ready") return null;

  return (
    <section className="price-card" aria-label={estimate ? "Kết quả định giá" : "Thông tin căn nhà"}>
      {estimate && (
        <div className="price-card__head">
          <p className="price-card__label">Giá ước tính</p>
          <p className="price-card__total">{formatPrice(estimate.total_price)}</p>
          <p className="price-card__sub">
            {formatPricePerM2(estimate.price_per_m2)}
            {range && <> · khoảng {range}</>}
          </p>
        </div>
      )}
      {estimate && bar && (
        <figure className="range">
          <div
            className="range__track"
            role="img"
            aria-label={`Khoảng tham khảo ${formatPricePerM2(estimate.price_per_m2_low as number)} đến ${formatPricePerM2(estimate.price_per_m2_high as number)}, ước tính ${formatPricePerM2(estimate.price_per_m2)}${estimate.district_median_per_m2 !== null ? `, ${medianLabel.toLowerCase()} ${formatPricePerM2(estimate.district_median_per_m2)}` : ""}`}
          >
            <span className="range__band" style={{ left: `${bar.low}%`, width: `${bar.high - bar.low}%` }} />
            {bar.median !== null && <span className="range__median" style={{ left: `${bar.median}%` }} />}
            <span className="range__dot" style={{ left: `${bar.estimate}%` }} />
          </div>
          <div className="range__ticks" aria-hidden="true">
            <span style={{ left: `${bar.low}%` }}>{formatNumberShort(estimate.price_per_m2_low as number)}</span>
            <span style={{ left: `${bar.high}%` }}>{formatNumberShort(estimate.price_per_m2_high as number)}</span>
          </div>
          <figcaption className="range__legend">
            <span><i className="key key--band" />Khoảng tham khảo</span>
            <span><i className="key key--dot" />Ước tính</span>
            {estimate.district_median_per_m2 !== null && <span><i className="key key--median" />{medianLabel}</span>}
          </figcaption>
        </figure>
      )}
      {estimate && (
        <dl className="estimate">
          {estimate.district_median_per_m2 !== null && (
            <div>
              <dt>{medianLabel}</dt>
              <dd>{formatPricePerM2(estimate.district_median_per_m2)}</dd>
            </div>
          )}
          <div>
            <dt>Cách trung tâm</dt>
            <dd>{formatDistance(estimate.distance_to_center_km * 1000)}</dd>
          </div>
        </dl>
      )}
      {known.length > 0 && (
        <ul className="fields" aria-label="Thông tin đã có">
          {known.map(([key, value]) => (
            <li key={key} className="field">
              <span>{FIELD_LABELS[key] ?? key}</span> <strong>{formatField(key, value)}</strong>
            </li>
          ))}
          {turn.missing.map((key) => (
            <li key={key} className="field field--missing">
              <span>{FIELD_LABELS[key] ?? key}</span> <strong>còn thiếu</strong>
            </li>
          ))}
        </ul>
      )}
      {estimate?.warnings?.map((warning) => (
        <p key={warning} className="note note--warn"><span aria-hidden="true">!</span>{warning}</p>
      ))}
      {turn.status === "ready" && (
        <button type="button" className="btn btn--small" onClick={() => onSend("ok")}>
          Dự đoán giá ngay
        </button>
      )}
    </section>
  );
}
