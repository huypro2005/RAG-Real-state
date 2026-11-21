import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import type { ListingHit } from "../api";
import {
  POI_LABELS, formatArea, formatDate, formatDistance, formatPrice, formatPricePerM2, listingWarnings, propertyKind,
} from "../format";
import type { PoiType } from "../api";
import { PropertyThumb } from "./PropertyThumb";

interface Props {
  hit: ListingHit;
  selected: boolean;
  onSelect: () => void;
}

const POI_ORDER: PoiType[] = ["truong_hoc", "benh_vien", "cho"];

/** Thẻ tin rao: giá là tiêu điểm, rồi giá/m² + diện tích, loại nhà + quận, địa chỉ, hàng khoảng cách tiện ích. */
export function ListingCard({ hit, selected, onSelect }: Props) {
  const ref = useRef<HTMLElement>(null);
  const warnings = listingWarnings(hit);
  const facts = [
    hit.area > 0 ? formatPricePerM2(hit.price / hit.area) : null,
    formatArea(hit.area),
    hit.bedrooms !== null ? `${hit.bedrooms} PN` : null,
  ].filter(Boolean);
  const amenities = POI_ORDER.filter((type) => hit.poi_distances[type] !== undefined);

  // Chọn từ marker trên bản đồ thì cuộn thẻ tương ứng vào tầm nhìn.
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [selected]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      onSelect();
    }
  };

  return (
    <article
      ref={ref}
      className={`card${selected ? " card--selected" : ""}`}
      tabIndex={0}
      aria-label={`Tin số ${hit.position}: ${hit.title}`}
      onClick={onSelect}
      onKeyDown={onKeyDown}
    >
      <div className="thumb">
        <PropertyThumb kind={propertyKind(hit.property_type)} />
        <span className="thumb__no" aria-hidden="true">{hit.position}</span>
      </div>
      <div className="card__body">
        <p className="card__kicker">
          {[hit.property_type, hit.district_old].filter(Boolean).join(" · ") || "Bất động sản"}
        </p>
        <p className="card__price">{formatPrice(hit.price)}</p>
        <p className="card__facts">{facts.join(" · ")}</p>
        <h3 className="card__title">{hit.title}</h3>
        {hit.old_address && <p className="card__addr">{hit.old_address}</p>}
        {hit.new_address && <p className="card__addr card__addr--new">Địa chỉ mới: {hit.new_address}</p>}
        {amenities.length > 0 && (
          <dl className="specs" aria-label="Khoảng cách tới tiện ích gần nhất">
            {amenities.map((type) => (
              <div key={type} className="specs__item">
                <dt>{POI_LABELS[type]}</dt>
                <dd>{formatDistance(hit.poi_distances[type] as number)}</dd>
              </div>
            ))}
          </dl>
        )}
        {warnings.length > 0 && (
          <p className="card__warnings">
            {warnings.map((label) => (
              <span key={label} className="warning">{label}</span>
            ))}
          </p>
        )}
        <p className="card__foot">
          <span>{hit.posted_at ? `Đăng ${formatDate(hit.posted_at)}` : ""}</span>
          <a
            href={hit.listing_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => event.stopPropagation()}
          >
            Xem tin gốc <span aria-hidden="true">→</span>
          </a>
        </p>
      </div>
    </article>
  );
}
