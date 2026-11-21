import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import L from "leaflet";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { fetchPriceOptions, geocodeAddress, predictPrice } from "../api";
import type { OptionalField, PredictionTurn, PriceFormResult, PriceLocation, PriceOptions } from "../api";
import { TILES } from "./MapView";
import { PredictionCard } from "./PredictionCard";

const HCM_CENTER: L.LatLngTuple = [10.7769, 106.7009];
const OPTIONAL_ORDER: OptionalField[] = ["bedrooms", "floors", "frontage"];
const SOURCE_NOTES: Record<PriceLocation["source"], string> = {
  user: "Tọa độ bạn chọn",
  goong: "Tọa độ tìm từ địa chỉ",
  district_centroid: "Không tìm thấy địa chỉ trong quận, dùng tâm quận",
};

// Ghim tròn bằng CSS: không phụ thuộc ảnh marker mặc định của Leaflet (hay vỡ đường dẫn khi build).
const PIN = L.divIcon({ className: "pin-anchor", html: '<span class="value-pin"></span>', iconSize: [0, 0], iconAnchor: [0, 0] });

interface Form {
  property_code: string;
  district_code: string;
  address: string;
  latitude: string;
  longitude: string;
  area: string;
  bedrooms: string;
  floors: string;
  frontage: string;
}

const EMPTY: Form = {
  property_code: "", district_code: "", address: "", latitude: "", longitude: "",
  area: "", bedrooms: "", floors: "", frontage: "",
};

/** "" -> null; "4,5" và "4.5" đều là 4.5; chữ -> NaN để báo lỗi. */
function toNumber(text: string): number | null {
  const trimmed = text.trim().replace(",", ".");
  return trimmed === "" ? null : Number(trimmed);
}

/** Bấm bản đồ hoặc kéo ghim để đặt vị trí; chỉ bay tới `focus` (kết quả nút Tìm / dự đoán), không bay khi bấm. */
function MapPicker({ point, focus, onPick }: {
  point: L.LatLngTuple | null;
  focus: L.LatLngTuple | null;
  onPick: (lat: number, lon: number) => void;
}) {
  const map = useMap();
  useMapEvents({ click: (event) => onPick(event.latlng.lat, event.latlng.lng) });
  useEffect(() => {
    if (focus) map.flyTo(focus, Math.max(map.getZoom(), 15), { duration: 0.6 });
  }, [focus, map]);
  return point ? (
    <Marker
      position={point}
      icon={PIN}
      draggable
      eventHandlers={{ dragend: (event) => {
        const { lat, lng } = (event.target as L.Marker).getLatLng();
        onPick(lat, lng);
      } }}
    />
  ) : null;
}

/** Trang định giá bằng form: frontend → backend /api/v1/price → Prediction Server. */
export function ValuationPage({ active }: { active: boolean }) {
  const [options, setOptions] = useState<PriceOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [source, setSource] = useState<PriceLocation["source"] | null>(null);
  const [focus, setFocus] = useState<L.LatLngTuple | null>(null);
  const [locating, setLocating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ data: PriceFormResult; form: Form } | null>(null);

  useEffect(() => {
    if (!active || options) return;
    let cancelled = false;
    fetchPriceOptions()
      .then((data) => { if (!cancelled) { setOptions(data); setOptionsError(null); } })
      .catch((reason: unknown) => {
        if (!cancelled) setOptionsError(reason instanceof Error ? reason.message : "Không tải được danh mục.");
      });
    return () => { cancelled = true; };
  }, [active, options]);

  // Leaflet đo lại khung khi tab được mở (trang được giữ trong DOM nhưng ẩn).
  useEffect(() => {
    if (active) window.dispatchEvent(new Event("resize"));
  }, [active]);

  const used = useMemo<OptionalField[]>(
    () => (options && form.property_code ? options.fields_by_type[form.property_code] ?? [] : OPTIONAL_ORDER),
    [options, form.property_code],
  );
  const lat = toNumber(form.latitude);
  const lon = toNumber(form.longitude);
  const point = useMemo<L.LatLngTuple | null>(
    () => (lat !== null && lon !== null && Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null),
    [lat, lon],
  );

  const set = (key: keyof Form, value: string) => setForm((previous) => ({ ...previous, [key]: value }));
  const setPoint = (latitude: number, longitude: number, from: PriceLocation["source"]) => {
    setForm((previous) => ({ ...previous, latitude: latitude.toFixed(6), longitude: longitude.toFixed(6) }));
    setSource(from);
  };

  async function locate() {
    if (!form.district_code) {
      setError("Chọn quận/huyện trước khi tìm địa chỉ.");
      return;
    }
    setLocating(true);
    setError(null);
    try {
      const found = await geocodeAddress(Number(form.district_code), form.address,
        form.property_code ? Number(form.property_code) : null);
      setPoint(found.latitude, found.longitude, found.source);
      setFocus([found.latitude, found.longitude]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không tìm được địa chỉ.");
    } finally {
      setLocating(false);
    }
  }

  /** Kiểm tra phía client (backend vẫn kiểm tra lại); trả về thông báo lỗi đầu tiên. */
  function validate(): string | null {
    if (!options) return "Chưa tải được danh mục.";
    if (!form.property_code) return "Chọn loại nhà đất.";
    if (!form.district_code) return "Chọn quận/huyện.";
    const area = toNumber(form.area);
    const { bounds } = options;
    if (area === null) return "Nhập diện tích.";
    if (!(area >= bounds.area.min && area <= bounds.area.max)) {
      return `Diện tích phải từ ${bounds.area.min} đến ${bounds.area.max} m².`;
    }
    for (const key of used) {
      const value = toNumber(form[key]);
      if (value !== null && !(value >= bounds[key].min && value <= bounds[key].max)) {
        return `${bounds[key].label} phải từ ${bounds[key].min} đến ${bounds[key].max} ${bounds[key].unit} (để trống nếu không biết).`;
      }
    }
    if ((lat === null) !== (lon === null)) return "Nhập đủ cả vĩ độ và kinh độ, hoặc để trống cả hai.";
    if (lat !== null && lon !== null) {
      const { lat: latRange, lon: lonRange } = options.hcm_bounds;
      if (!(lat >= latRange[0] && lat <= latRange[1] && lon >= lonRange[0] && lon <= lonRange[1])) {
        return "Tọa độ nằm ngoài TP.HCM.";
      }
    }
    return null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    setError(null);
    const optional = (key: OptionalField) => (used.includes(key) ? toNumber(form[key]) : null);
    try {
      const data = await predictPrice({
        property_code: Number(form.property_code),
        district_code: Number(form.district_code),
        area: toNumber(form.area) as number,
        address: form.address.trim() || null,
        latitude: lat,
        longitude: lon,
        bedrooms: optional("bedrooms"),
        floors: optional("floors"),
        frontage: optional("frontage"),
      });
      setResult({ data, form });
      setPoint(data.location.latitude, data.location.longitude, data.location.source);
      setFocus([data.location.latitude, data.location.longitude]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không dự đoán được.");
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setForm(EMPTY);
    setSource(null);
    setFocus(null);
    setResult(null);
    setError(null);
  }

  const name = (list: { code: number; name: string }[] | undefined, code: string) =>
    list?.find((item) => String(item.code) === code)?.name ?? code;
  const turn: PredictionTurn | null = result && {
    conversation_id: "form",
    mode: "prediction",
    status: "predicted",
    answer: "",
    summary: "",
    missing: [],
    prediction: result.data.estimate,
    fields: {
      property_type: name(options?.property_types, result.form.property_code),
      district: name(options?.districts, result.form.district_code),
      area: toNumber(result.form.area),
      ...Object.fromEntries(result.data.used_fields.map((key) => [key, toNumber(result.form[key])])),
    },
  };

  return (
    <div className="valuation">
      <header className="valuation__head">
        <h2>Định giá nhà đất</h2>
        <p className="muted">
          Nhập thông tin căn nhà để ước tính giá. Mô hình học từ tin rao bán trên batdongsan.com.vn tại TP.HCM (cũ),
          nên kết quả là giá rao tham khảo, không phải giá giao dịch.
        </p>
      </header>

      <form className="valuation__form" onSubmit={submit} noValidate>
        {optionsError && <p className="note note--warn"><span aria-hidden="true">!</span>{optionsError}</p>}

        <fieldset className="vform__group">
          <legend>Bất động sản</legend>
          <label className="vform__field">
            <span>Loại nhà đất *</span>
            <select value={form.property_code} onChange={(event) => set("property_code", event.target.value)} required>
              <option value="">Chọn loại nhà đất</option>
              {options?.property_types.map((item) => (
                <option key={item.code} value={item.code}>{item.name}</option>
              ))}
            </select>
          </label>
          <label className="vform__field">
            <span>Diện tích (m²) *</span>
            <input inputMode="decimal" value={form.area} onChange={(event) => set("area", event.target.value)} placeholder="Ví dụ: 65" required />
          </label>
        </fieldset>

        <fieldset className="vform__group">
          <legend>Vị trí</legend>
          <label className="vform__field">
            <span>Tỉnh/Thành phố</span>
            <input value="Hồ Chí Minh (địa giới cũ)" disabled />
          </label>
          <label className="vform__field">
            <span>Quận/Huyện *</span>
            <select value={form.district_code} onChange={(event) => set("district_code", event.target.value)} required>
              <option value="">Chọn quận/huyện</option>
              {options?.districts.map((item) => (
                <option key={item.code} value={item.code}>{item.name}</option>
              ))}
            </select>
          </label>
          <div className="vform__field vform__field--wide">
            <label htmlFor="vform-address">Địa chỉ chi tiết</label>
            <div className="vform__inline">
              <input
                id="vform-address"
                value={form.address}
                onChange={(event) => set("address", event.target.value)}
                placeholder="Tên đường, dự án… (ví dụ: Eastmark City, Trường Lưu)"
              />
              <button type="button" className="btn btn--ghost" onClick={locate} disabled={locating || !form.district_code}>
                {locating ? "Đang tìm…" : "Tìm trên bản đồ"}
              </button>
            </div>
          </div>
          <label className="vform__field">
            <span>Vĩ độ (tùy chọn)</span>
            <input inputMode="decimal" value={form.latitude} onChange={(event) => { set("latitude", event.target.value); setSource("user"); }} placeholder="10.797104" />
          </label>
          <label className="vform__field">
            <span>Kinh độ (tùy chọn)</span>
            <input inputMode="decimal" value={form.longitude} onChange={(event) => { set("longitude", event.target.value); setSource("user"); }} placeholder="106.823440" />
          </label>
          <p className="vform__hint">
            Bấm vào bản đồ hoặc kéo ghim để chọn đúng vị trí. Để trống tọa độ thì hệ thống tự tìm từ địa chỉ và quận.
          </p>
        </fieldset>

        <fieldset className="vform__group">
          <legend>Đặc điểm (để trống nếu không biết)</legend>
          {OPTIONAL_ORDER.map((key) => {
            const bound = options?.bounds[key];
            const enabled = used.includes(key);
            return (
              <label key={key} className={`vform__field${enabled ? "" : " vform__field--off"}`}>
                <span>{bound ? `${bound.label} (${bound.unit})` : key}</span>
                <input
                  inputMode={key === "frontage" ? "decimal" : "numeric"}
                  value={enabled ? form[key] : ""}
                  onChange={(event) => set(key, event.target.value)}
                  disabled={!enabled}
                  placeholder={enabled ? "Không biết" : "Không dùng cho loại này"}
                />
              </label>
            );
          })}
        </fieldset>

        {error && <p className="note note--error" role="alert"><span aria-hidden="true">!</span>{error}</p>}
        <div className="vform__actions">
          <button type="submit" className="btn" disabled={submitting || !options}>
            {submitting ? "Đang dự đoán…" : "Dự đoán giá"}
          </button>
          <button type="button" className="btn btn--ghost" onClick={reset}>Làm mới</button>
        </div>
      </form>

      <section className="valuation__side" aria-label="Bản đồ và kết quả">
        <div className="valuation__map">
          <MapContainer center={HCM_CENTER} zoom={12} className="map__canvas">
            <TileLayer url={TILES.url} attribution={TILES.attribution} maxZoom={19} />
            <MapPicker point={point} focus={focus} onPick={(latitude, longitude) => setPoint(latitude, longitude, "user")} />
          </MapContainer>
        </div>
        <p className="vform__hint">
          {point && source
            ? `${SOURCE_NOTES[source]}: ${point[0].toFixed(6)}, ${point[1].toFixed(6)}`
            : "Chưa chọn vị trí."}
        </p>
        {turn ? (
          <PredictionCard turn={turn} onSend={() => undefined} />
        ) : (
          <p className="valuation__empty">Kết quả dự đoán sẽ hiện ở đây.</p>
        )}
        {result && (
          <p className="vform__hint">
            Đây là giá rao tham khảo do mô hình ước tính. Giá thực tế còn phụ thuộc thị trường, thời điểm giao dịch và
            tình trạng căn nhà.
          </p>
        )}
      </section>
    </div>
  );
}
