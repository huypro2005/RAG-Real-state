import { useEffect, useRef } from "react";
import type { MutableRefObject } from "react";
import L from "leaflet";
import type { Marker as LeafletMarker } from "leaflet";
import { Circle, CircleMarker, MapContainer, Marker, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { GOONG_TILES_KEY } from "../api";
import type { ListingHit, MapFeature, PoiType } from "../api";
import { POI_LABELS, formatArea, formatDistance, formatPrice, formatPriceShort } from "../format";

interface Props {
  listings: ListingHit[];
  pois: MapFeature[];
  selected: string | null; // listing_id
  onSelect: (listingId: string) => void;
}

const HCM_CENTER: L.LatLngTuple = [10.7769, 106.7009];
const POI_COLORS: Record<PoiType, string> = {
  // Màu đất, tách khỏi màu nhấn xanh rêu của ghim tin: trường xanh đá, bệnh viện đỏ gạch, chợ vàng đất.
  truong_hoc: "#2f5f86",
  benh_vien: "#a3311f",
  cho: "#9a6a12",
};

// Goong nếu có key map tiles riêng của frontend, ngược lại OpenStreetMap bản Đức (không cần key).
// Không dùng tile.openstreetmap.org vì một số mạng VN chặn tên miền này; CARTO thì đòi API key.
export const TILES = GOONG_TILES_KEY
  ? {
      url: `https://tiles.goong.io/assets/goong_map_web/{z}/{x}/{y}.png?api_key=${GOONG_TILES_KEY}`,
      attribution: "&copy; Goong",
    }
  : {
      url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
      attribution: "&copy; OpenStreetMap contributors",
    };

/** Ghim kiểu tin rao: số thứ tự + giá ngắn ("3,1 tỷ"), đuôi nhọn chỉ đúng tọa độ. Kích thước 0 để CSS tự co theo chữ. */
function priceIcon(position: number, price: string, reliable: boolean, active: boolean): L.DivIcon {
  const cls = ["pin", reliable ? "" : "pin--unreliable", active ? "pin--active" : ""].filter(Boolean).join(" ");
  return L.divIcon({
    className: "pin-anchor",
    html: `<div class="${cls}"><b>${position}</b><span>${price}</span></div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
    popupAnchor: [0, -34],
  });
}

/** Tự fitBounds khi bộ tin đổi, và bay tới marker khi người dùng bấm thẻ. */
function MapController({ listings, selected, markers }: {
  listings: ListingHit[];
  selected: string | null;
  markers: MutableRefObject<Map<string, LeafletMarker>>;
}) {
  const map = useMap();

  useEffect(() => {
    map.closePopup(); // bộ tin đổi (hoặc reset): bỏ popup của tin cũ
    const points = listings.flatMap((hit) =>
      hit.latitude !== null && hit.longitude !== null ? [[hit.latitude, hit.longitude] as L.LatLngTuple] : [],
    );
    if (points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 16 });
    }
  }, [listings, map]);

  useEffect(() => {
    const hit = listings.find((item) => item.listing_id === selected);
    if (!hit || hit.latitude === null || hit.longitude === null) return;
    map.flyTo([hit.latitude, hit.longitude], Math.max(map.getZoom(), 16), { duration: 0.8 });
    markers.current.get(hit.listing_id)?.openPopup();
  }, [selected, listings, map, markers]);

  return null;
}

export function MapView({ listings, pois, selected, onSelect }: Props) {
  const markers = useRef(new Map<string, LeafletMarker>());
  const drawable = listings.filter((hit) => hit.latitude !== null && hit.longitude !== null);
  const missing = listings.length - drawable.length;

  return (
    <section className="map" aria-label="Bản đồ">
      <MapContainer center={HCM_CENTER} zoom={12} className="map__canvas">
        <TileLayer url={TILES.url} attribution={TILES.attribution} maxZoom={19} />
        <MapController listings={listings} selected={selected} markers={markers} />
        {pois.filter((item) => item.properties.kind === "place").map((place) => {
          const [lng, lat] = place.geometry.coordinates;
          return (
            <Circle
              key={`place-${place.properties.name}`}
              center={[lat, lng]}
              radius={place.properties.radius_m ?? 5000}
              pathOptions={{ color: "#b4531c", weight: 1.5, fillOpacity: 0.05 }}
            >
              <Tooltip>
                {place.properties.name} (bán kính {formatDistance(place.properties.radius_m ?? 5000)})
              </Tooltip>
            </Circle>
          );
        })}
        {pois.filter((item) => item.properties.kind === "place").map((place) => {
          const [lng, lat] = place.geometry.coordinates;
          return (
            <CircleMarker
              key={`place-pin-${place.properties.name}`}
              center={[lat, lng]}
              radius={9}
              pathOptions={{ color: "#fff", weight: 2, fillColor: "#b4531c", fillOpacity: 1 }}
            >
              <Tooltip>{place.properties.name}</Tooltip>
            </CircleMarker>
          );
        })}
        {pois.filter((item) => item.properties.kind === "poi").map((poi, index) => {
          const [lng, lat] = poi.geometry.coordinates;
          const type = poi.properties.poi_type ?? "cho";
          return (
            <CircleMarker
              key={`${poi.properties.name}-${index}`}
              center={[lat, lng]}
              radius={7}
              pathOptions={{ color: "#fff", weight: 1.5, fillColor: POI_COLORS[type], fillOpacity: 0.95 }}
            >
              <Tooltip>
                {POI_LABELS[type]}: {poi.properties.name}
                {poi.properties.distance_m !== undefined && ` (${formatDistance(poi.properties.distance_m)})`}
              </Tooltip>
            </CircleMarker>
          );
        })}
        {drawable.map((hit) => (
          <Marker
            key={hit.listing_id}
            position={[hit.latitude as number, hit.longitude as number]}
            icon={priceIcon(hit.position, formatPriceShort(hit.price), hit.coords_reliable, hit.listing_id === selected)}
            zIndexOffset={hit.listing_id === selected ? 1000 : 0}
            eventHandlers={{ click: () => onSelect(hit.listing_id) }}
            ref={(marker) => {
              if (marker) markers.current.set(hit.listing_id, marker);
              else markers.current.delete(hit.listing_id);
            }}
          >
            <Popup className="popup">
              <span className="popup__no">Tin {hit.position}</span>
              <strong className="popup__price">{formatPrice(hit.price)}</strong>
              <span className="popup__facts">{formatArea(hit.area)}{hit.district_old ? ` · ${hit.district_old}` : ""}</span>
              <span className="popup__title">{hit.title}</span>
              {!hit.coords_reliable && <em className="popup__warn">Vị trí có thể không chính xác</em>}
              <a href={hit.listing_url} target="_blank" rel="noopener noreferrer">Xem tin gốc →</a>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      {listings.length === 0 && (
        <p className="map__note">Gửi yêu cầu ở khung chat, các tin gợi ý sẽ hiện trên bản đồ.</p>
      )}
      {missing > 0 && (
        <p className="map__note">{missing} tin không có tọa độ nên không hiện trên bản đồ.</p>
      )}
      <ul className="legend">
        {(Object.keys(POI_COLORS) as PoiType[]).map((type) => (
          <li key={type}>
            <span className="legend__dot" style={{ background: POI_COLORS[type] }} />
            {POI_LABELS[type]}
          </li>
        ))}
        <li><span className="legend__dot legend__dot--pin" />Tin đề xuất</li>
        <li><span className="legend__dot legend__dot--unreliable" />Tọa độ chưa đáng tin</li>
        <li><span className="legend__dot" style={{ background: "#b4531c" }} />Địa điểm bạn chọn</li>
      </ul>
    </section>
  );
}
