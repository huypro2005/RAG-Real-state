import { useEffect, useRef } from "react";
import L from "leaflet";
import type { Marker as LeafletMarker } from "leaflet";
import { Circle, CircleMarker, MapContainer, Marker, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { GOONG_TILES_KEY } from "../api";
import type { ListingHit, MapFeature, PoiType } from "../api";
import { POI_LABELS, formatDistance, formatPrice } from "../format";

interface Props {
  listings: ListingHit[];
  pois: MapFeature[];
  selected: number | null;
}

const HCM_CENTER: L.LatLngTuple = [10.7769, 106.7009];
const POI_COLORS: Record<PoiType, string> = {
  truong_hoc: "#7c3aed",
  benh_vien: "#dc2626",
  cho: "#16a34a",
};

// Goong nếu có key map tiles riêng của frontend, ngược lại OpenStreetMap bản Đức (không cần key).
// Không dùng tile.openstreetmap.org vì một số mạng VN chặn tên miền này; CARTO thì đòi API key.
const TILES = GOONG_TILES_KEY
  ? {
      url: `https://tiles.goong.io/assets/goong_map_web/{z}/{x}/{y}.png?api_key=${GOONG_TILES_KEY}`,
      attribution: "&copy; Goong",
    }
  : {
      url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
      attribution: "&copy; OpenStreetMap contributors",
    };

function numberIcon(position: number, reliable: boolean): L.DivIcon {
  const cls = reliable ? "pin" : "pin pin--unreliable";
  return L.divIcon({ className: "", html: `<div class="${cls}">${position}</div>`, iconSize: [30, 30] });
}

/** Tự fitBounds khi bộ tin đổi, và bay tới marker khi người dùng bấm thẻ. */
function MapController({ listings, selected, markers }: {
  listings: ListingHit[];
  selected: number | null;
  markers: React.MutableRefObject<Map<number, LeafletMarker>>;
}) {
  const map = useMap();

  useEffect(() => {
    const points = listings.flatMap((hit) =>
      hit.latitude !== null && hit.longitude !== null ? [[hit.latitude, hit.longitude] as L.LatLngTuple] : [],
    );
    if (points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 16 });
    }
  }, [listings, map]);

  useEffect(() => {
    const hit = listings.find((item) => item.position === selected);
    if (!hit || hit.latitude === null || hit.longitude === null) return;
    map.flyTo([hit.latitude, hit.longitude], Math.max(map.getZoom(), 16), { duration: 0.8 });
    markers.current.get(hit.position)?.openPopup();
  }, [selected, listings, map, markers]);

  return null;
}

export function MapView({ listings, pois, selected }: Props) {
  const markers = useRef(new Map<number, LeafletMarker>());
  const drawable = listings.filter((hit) => hit.latitude !== null && hit.longitude !== null);

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
              pathOptions={{ color: "#ea580c", weight: 2, fillOpacity: 0.06 }}
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
              pathOptions={{ color: "#fff", weight: 2, fillColor: "#ea580c", fillOpacity: 1 }}
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
            icon={numberIcon(hit.position, hit.coords_reliable)}
            ref={(marker) => {
              if (marker) markers.current.set(hit.position, marker);
              else markers.current.delete(hit.position);
            }}
          >
            <Popup>
              <strong>{hit.position}. {hit.title}</strong>
              <br />
              {formatPrice(hit.price)}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      <ul className="legend">
        {(Object.keys(POI_COLORS) as PoiType[]).map((type) => (
          <li key={type}>
            <span className="legend__dot" style={{ background: POI_COLORS[type] }} />
            {POI_LABELS[type]}
          </li>
        ))}
        <li><span className="legend__dot legend__dot--pin" />Tin đề xuất</li>
        <li><span className="legend__dot" style={{ background: "#ea580c" }} />Địa điểm bạn chọn</li>
      </ul>
    </section>
  );
}
