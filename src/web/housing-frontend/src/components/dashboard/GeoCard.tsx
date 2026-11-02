import { useMemo, useState } from "react";
import type { GeoScatter } from "../../api";
import { URBAN_BOUNDS, defaultBounds, extremes, formatNumber, gridSummary, orderedTypes, outsideCount, typeLabel, visibleGeoPoints } from "../../dashboard";
import type { Bounds } from "../../dashboard";
import { ChartCard } from "./ChartCard";
import { GeoPlot } from "./GeoPlot";

/** Khối "Bản đồ giá theo vị trí": lọc loại nhà, chọn vùng, bật/tắt cỡ điểm; thiếu dữ liệu thì báo gọn. */
export function GeoCard({ geo, pin, busy }: { geo: GeoScatter | null | undefined; pin: string; busy: boolean }) {
  const [type, setType] = useState<number | null>(null);
  const [inner, setInner] = useState(false);
  const [sizeByArea, setSizeByArea] = useState(true);
  const empty = !geo || geo.points.length === 0 ? "Phiên bản này chưa có dữ liệu vị trí (phiên bản cũ). Dựng lại biểu đồ ở Prediction Server để có bản đồ giá." : undefined;
  const urban = useMemo(() => (geo ? defaultBounds(geo.points) : URBAN_BOUNDS), [geo]);
  const bounds: Bounds = geo && !inner ? geo.bounds : urban;
  const types = useMemo(() => (geo ? orderedTypes(geo.points.map((p) => p.type)) : []), [geo]);
  const shown = geo ? visibleGeoPoints(geo.points, bounds, type) : [];
  const outside = geo ? outsideCount(geo.points, bounds, type) : 0;

  return (
    <ChartCard
      wide title="Bản đồ giá theo vị trí" pin={pin} busy={busy} empty={empty}
      note={geo ? `Mỗi chấm là một tin: màu = giá/m², cỡ = diện tích. ${formatNumber(shown.length)} chấm trong khung${outside > 0 ? `, ${formatNumber(outside)} điểm ngoài khung` : ""} (mẫu ${formatNumber(geo.points.length)}/${formatNumber(geo.n_total)} tin). Kinh độ nằm ngang, vĩ độ nằm dọc, đúng tỉ lệ (đã đổi trục so với plot notebook cho dễ nhìn).` : undefined}
      controls={
        <>
          <label className="field-inline field-inline--row">Loại nhà
            <select value={type ?? ""} onChange={(e) => setType(e.target.value === "" ? null : Number(e.target.value))}>
              <option value="">Tất cả</option>
              {types.map((t) => <option key={t} value={t}>{typeLabel(t)}</option>)}
            </select>
          </label>
          <div className="seg" role="group" aria-label="Vùng hiển thị">
            <button type="button" aria-pressed={inner} onClick={() => setInner(true)}>Nội thành</button>
            <button type="button" aria-pressed={!inner} onClick={() => setInner(false)}>Toàn TP.HCM</button>
          </div>
          <button type="button" className="btn btn--ghost" aria-pressed={sizeByArea} onClick={() => setSizeByArea((on) => !on)}>
            Cỡ điểm theo diện tích
          </button>
        </>
      }
      table={geo && <GeoTable geo={geo} points={shown} bounds={bounds} />}
    >
      {geo && <GeoPlot geo={geo} bounds={bounds} type={type} sizeByArea={sizeByArea} />}
    </ChartCard>
  );
}

function GeoTable({ geo, points, bounds }: { geo: GeoScatter; points: GeoScatter["points"]; bounds: Bounds }) {
  const { cheapest, priciest } = extremes(points, 10);
  const rows = (list: typeof cheapest) => list.map((p, i) => (
    <tr key={i}>
      <th scope="row">{typeLabel(p.type)}</th>
      <td className="num">{formatNumber(p.price_per_m2, 1)}</td>
      <td className="num">{formatNumber(p.area, 0)}</td>
      <td className="num">{formatNumber(p.lat, 4)}, {formatNumber(p.lon, 4)}</td>
    </tr>
  ));
  const head = <tr><th scope="col">Loại nhà</th><th scope="col" className="num">Giá (triệu/m²)</th><th scope="col" className="num">m²</th><th scope="col" className="num">Vĩ độ, kinh độ</th></tr>;
  const cells = gridSummary(points, bounds, 6).slice(0, 10);
  return (
    <>
      <table className="table">
        <caption>10 điểm đắt nhất (trong khung nhìn)</caption>
        <thead>{head}</thead>
        <tbody>{rows(priciest)}</tbody>
      </table>
      <table className="table table--gap">
        <caption>10 điểm rẻ nhất</caption>
        <thead>{head}</thead>
        <tbody>{rows(cheapest)}</tbody>
      </table>
      <table className="table table--gap">
        <caption>10 ô lưới 6×6 nhiều tin nhất (tâm ô, giá trung vị)</caption>
        <thead><tr><th scope="col">Tâm ô (vĩ độ, kinh độ)</th><th scope="col" className="num">Số điểm</th><th scope="col" className="num">Trung vị (triệu/m²)</th></tr></thead>
        <tbody>{cells.map((c) => <tr key={`${c.row}-${c.col}`}><th scope="row">{formatNumber(c.lat, 3)}, {formatNumber(c.lon, 3)}</th><td className="num">{formatNumber(c.n)}</td><td className="num">{formatNumber(c.median, 1)}</td></tr>)}</tbody>
      </table>
      <p className="muted">Tâm: {geo.center.name}.</p>
    </>
  );
}
