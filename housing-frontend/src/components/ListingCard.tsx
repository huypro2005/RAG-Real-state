import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import type { ListingHit } from "../api";
import {
  POI_LABELS, formatArea, formatDate, formatDistance, formatPrice, formatPricePerM2, listingWarnings, nearestPoi,
} from "../format";

interface Props {
  hit: ListingHit;
  selected: boolean;
  onSelect: () => void;
}

export function ListingCard({ hit, selected, onSelect }: Props) {
  const ref = useRef<HTMLElement>(null);
  const poi = nearestPoi(hit.poi_distances);
  const warnings = listingWarnings(hit);
  const details = [
    formatArea(hit.area),
    hit.property_type,
    hit.bedrooms !== null ? `${hit.bedrooms} phòng ngủ` : null,
  ].filter(Boolean);

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
      <span className="badge">{hit.position}</span>
      <div className="card__body">
        <h3 className="card__title">{hit.title}</h3>
        <p className="card__price">
          {formatPrice(hit.price)}
          {hit.area > 0 && <span className="card__unit"> · {formatPricePerM2(hit.price / hit.area)}</span>}
        </p>
        <p className="card__meta">{details.join(" · ")}</p>
        {hit.old_address && <p className="card__addr">{hit.old_address}</p>}
        {hit.new_address && <p className="card__addr card__addr--new">Địa chỉ mới: {hit.new_address}</p>}
        {poi && (
          <p className="card__meta">
            {POI_LABELS[poi.type]} gần nhất: {formatDistance(poi.meters)}
          </p>
        )}
        {warnings.length > 0 && (
          <p className="card__warnings">
            {warnings.map((label) => (
              <span key={label} className="warning">{label}</span>
            ))}
          </p>
        )}
        <p className="card__meta">
          {hit.posted_at && <>Đăng {formatDate(hit.posted_at)} · </>}
          <a
            href={hit.listing_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => event.stopPropagation()}
          >
            Xem tin gốc
          </a>
        </p>
      </div>
    </article>
  );
}
