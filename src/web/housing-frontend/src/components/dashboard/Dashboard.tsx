import { useMemo, useState } from "react";
import type { DashboardModelDetail, DashboardModelSummary, ModelCharts } from "../../api";
import {
  formatDateTime, formatMetric, formatNumber, groupDistrictTypes, logDomain, orderedTypes, prepareBins,
  sentenceCase, summarizeScatter, trendSeries, triggerLabel, typeColor, typeLabel,
} from "../../dashboard";
import { useDashboard } from "../../useDashboard";
import { ChartCard } from "./ChartCard";
import { DistrictBars } from "./DistrictBars";
import { GeoCard } from "./GeoCard";
import { Histogram } from "./Histogram";
import { ImportanceBars } from "./ImportanceBars";
import { Scatter } from "./Scatter";
import { TrendLines } from "./TrendLines";
import { TypeKey, TypeSelect, TypeToggles } from "./TypeFilter";
import { Badge, CandidatesTable, CompareTable, HistoryTable } from "./VersionTables";

const typeName = typeLabel;

function Kpis({ model }: { model: DashboardModelSummary }) {
  const metrics = model.metrics;
  const rows = (value: number | null) => (value === null ? "—" : formatNumber(value));
  return (
    <section className="kpis" aria-label="Chỉ số chính của phiên bản">
      <div className="kpi kpi--hero">
        <span className="kpi__label">R² log (tập kiểm thử)</span>
        <span className="kpi__hero">{formatMetric("r2_log", metrics?.r2_log)}</span>
        <span className="kpi__sub">Càng gần 1 càng tốt</span>
      </div>
      <div className="kpi"><span className="kpi__label">MAE</span><span className="kpi__value">{formatMetric("mae", metrics?.mae)}</span><span className="kpi__sub">triệu/m²</span></div>
      <div className="kpi"><span className="kpi__label">MAPE</span><span className="kpi__value">{formatMetric("mape", metrics?.mape)}</span><span className="kpi__sub">sai số tương đối</span></div>
      <div className="kpi"><span className="kpi__label">Dòng train / test</span><span className="kpi__value">{rows(model.train_rows)} / {rows(model.test_rows)}</span></div>
      <div className="kpi"><span className="kpi__label">Ứng viên thắng</span><span className="kpi__value kpi__value--text">{model.best_candidate ?? "—"}</span></div>
      <div className="kpi"><span className="kpi__label">Thời điểm train</span><span className="kpi__value kpi__value--text">{formatDateTime(model.created_at)}</span><span className="kpi__sub">{triggerLabel(model.trigger)}</span></div>
      <div className="kpi"><span className="kpi__label">Trạng thái</span><Badge status={model.status} active={model.is_active} /></div>
    </section>
  );
}

/** Nội dung vì sao một phiên bản không có biểu đồ. */
function missingMessage(model: DashboardModelSummary): string {
  if (model.status === "failed") return "Lần huấn luyện này thất bại nên không có dữ liệu biểu đồ. Chọn một phiên bản thành công ở bảng lịch sử.";
  if (model.status === "running") return "Phiên bản đang được huấn luyện. Biểu đồ sẽ có sau khi huấn luyện xong, bấm “Tải lại” để cập nhật.";
  if (model.status === "skipped") return "Lần huấn luyện này bị bỏ qua nên không có dữ liệu biểu đồ.";
  return "Phiên bản này chưa có dữ liệu biểu đồ (thường là phiên bản cũ). Server mô hình có thể dựng lại bằng POST /api/v1/models/{id}/charts/rebuild.";
}

function Charts({ data, busy }: { data: DashboardModelDetail & { charts: ModelCharts }; busy: boolean }) {
  const { charts } = data;
  const dist = charts.price_distribution;
  const pin = `Phiên bản #${data.id}`;
  const [refType, setRefType] = useState<number | null>(null);
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const [hiddenDistrict, setHiddenDistrict] = useState<Set<number>>(new Set());
  const [facet, setFacet] = useState(false);
  const [districtCount, setDistrictCount] = useState(8);

  const bins = useMemo(() => prepareBins(dist.bins), [dist.bins]);
  const points = charts.scatter.points;
  const types = useMemo(() => orderedTypes(points.map((p) => p.type)), [points]);
  const domain = useMemo<[number, number]>(() => {
    const all = points.flatMap((p) => [p.actual, p.predicted]);
    return logDomain(all);
  }, [points]);
  const typeStats = refType === null ? undefined : dist.by_type[refType];
  const stats = typeStats ?? dist.stats;
  const shown = points.filter((p) => !hidden.has(p.type));
  const flip = (type: number) => (old: Set<number>) => {
    const next = new Set(old);
    if (!next.delete(type)) next.add(type);
    return next;
  };
  const summary = useMemo(() => summarizeScatter(points), [points]);
  const worst = useMemo(() => [...points].sort((a, b) => Math.abs(Math.log(b.predicted / b.actual)) - Math.abs(Math.log(a.predicted / a.actual))).slice(0, 10), [points]);
  const districtRows = charts.district_type_median ?? [];
  const districtTypes = orderedTypes(districtRows.map((r) => r.property_type));
  const groups = useMemo(() => groupDistrictTypes(districtRows, districtCount), [districtRows, districtCount]);
  const hiddenNames = districtTypes.filter((t) => hiddenDistrict.has(t));
  const q = charts.scatter.residual_q90_log;

  return (
    <div className="dash__grid">
      <ChartCard
        title="Phân bố giá/m²" pin={pin} busy={busy}
        note={`${formatNumber(dist.stats.n)} tin trong bảng huấn luyện · trục cắt ở p99, ${formatNumber(dist.clipped_above)} tin cao hơn không hiện`}
        controls={<TypeSelect types={orderedTypes(Object.keys(dist.by_type).map(Number))} value={refType} onChange={setRefType} />}
        table={
          <table className="table">
            <caption className="sr-only">Số tin theo khoảng giá/m²</caption>
            <thead><tr><th scope="col">Khoảng giá ({dist.unit})</th><th scope="col" className="num">Số tin</th><th scope="col" className="num">Tỷ lệ</th></tr></thead>
            <tbody>{bins.map((b) => <tr key={b.x0}><th scope="row">{formatNumber(b.x0)} – {formatNumber(b.x1)}</th><td className="num">{formatNumber(b.count)}</td><td className="num">{formatNumber(b.share * 100, 1)}%</td></tr>)}</tbody>
          </table>
        }
        legend={
          <p className="muted">
            {refType === null ? "Tất cả loại nhà" : typeName(refType)}: trung vị {formatNumber(stats.median, 1)}, p10–p90 {formatNumber(stats.p10, 1)} – {formatNumber(stats.p90, 1)} {dist.unit}
            {typeStats ? ` (${formatNumber(typeStats.n)} tin). Cột vẫn là phân bố của mọi loại nhà.` : "."}
          </p>
        }
      >
        <Histogram
          bins={bins} unit={dist.unit} color={refType === null ? "var(--viz-neutral)" : typeColor(refType)}
          median={stats.median} p10={stats.p10} p90={stats.p90}
          caption={`Histogram giá mỗi m², trung vị ${formatNumber(stats.median, 1)} ${dist.unit}. Dùng phím mũi tên để đọc từng cột.`}
        />
      </ChartCard>

      <ChartCard
        title="Độ quan trọng đặc trưng" pin={pin} busy={busy}
        note="Permutation importance trên tập test: mức giảm R² log khi xáo trộn đặc trưng (lặp 5 lần)"
        empty={charts.feature_importance.items.length === 0 ? "Phiên bản này không có dữ liệu độ quan trọng đặc trưng." : undefined}
        table={
          <table className="table">
            <caption className="sr-only">Độ quan trọng đặc trưng</caption>
            <thead><tr><th scope="col">Đặc trưng</th><th scope="col" className="num">Độ quan trọng</th><th scope="col" className="num">Độ lệch chuẩn</th></tr></thead>
            <tbody>{charts.feature_importance.items.map((i) => <tr key={i.feature}><th scope="row">{sentenceCase(i.feature)}</th><td className="num">{formatNumber(i.importance, 3)}</td><td className="num">{formatNumber(i.std, 3)}</td></tr>)}</tbody>
          </table>
        }
      >
        <ImportanceBars items={charts.feature_importance.items} />
      </ChartCard>

      <ChartCard
        title="Thực tế so với dự đoán" pin={pin} busy={busy}
        note={`${formatNumber(points.length)}/${formatNumber(charts.scatter.n_test)} tin kiểm thử, trục log · 90% dự đoán lệch không quá ±${formatNumber((Math.exp(q) - 1) * 100, 0)}% (dải mờ)`}
        controls={
          <>
            <TypeToggles types={types} hidden={hidden} onToggle={(t) => setHidden(flip(t))} />
            <button type="button" className="btn btn--ghost" aria-pressed={facet} onClick={() => setFacet((on) => !on)}>
              {facet ? "Gộp một khung" : "Tách theo loại"}
            </button>
          </>
        }
        empty={points.length === 0 ? "Phiên bản này không có điểm kiểm thử." : undefined}
        table={
          <>
            <table className="table">
              <caption className="sr-only">Tóm tắt thực tế và dự đoán theo loại nhà</caption>
              <thead><tr><th scope="col">Loại nhà</th><th scope="col" className="num">Số điểm</th><th scope="col" className="num">Trung vị thực tế</th><th scope="col" className="num">Trung vị dự đoán</th><th scope="col" className="num">MAE</th></tr></thead>
              <tbody>{summary.map((s) => <tr key={s.type}><th scope="row">{typeName(s.type)}</th><td className="num">{formatNumber(s.n)}</td><td className="num">{formatNumber(s.medianActual, 1)}</td><td className="num">{formatNumber(s.medianPredicted, 1)}</td><td className="num">{formatNumber(s.mae, 1)}</td></tr>)}</tbody>
            </table>
            <table className="table table--gap">
              <caption>10 dự đoán lệch nhiều nhất</caption>
              <thead><tr><th scope="col">Loại nhà</th><th scope="col" className="num">Thực tế</th><th scope="col" className="num">Dự đoán</th></tr></thead>
              <tbody>{worst.map((p, i) => <tr key={i}><th scope="row">{typeName(p.type)}</th><td className="num">{formatNumber(p.actual, 1)}</td><td className="num">{formatNumber(p.predicted, 1)}</td></tr>)}</tbody>
            </table>
          </>
        }
        legend={<p className="muted">Mỗi loại nhà có màu và hình riêng nên vẫn phân biệt được khi in đen trắng hoặc mù màu. Đường chéo y = x là dự đoán đúng.</p>}
      >
        {facet ? (
          <div className="facets">
            {types.map((type) => (
              <figure key={type}>
                <figcaption><TypeKey type={type} /> {typeName(type)}</figcaption>
                <Scatter compact points={points.filter((p) => p.type === type)} domain={domain} q90={q} caption={`Thực tế và dự đoán của ${typeName(type)}`} />
              </figure>
            ))}
          </div>
        ) : (
          <Scatter points={shown} domain={domain} q90={q} caption="Thực tế và dự đoán giá mỗi m². Mũi tên để đọc từng điểm." />
        )}
      </ChartCard>

      <ChartCard
        title="Các mô hình ứng viên" pin={pin} busy={busy}
        note="Đánh giá chéo (CV) trên tập huấn luyện và R² log trên tập test cố định"
        empty={charts.candidates.length === 0 ? "Phiên bản này không ghi lại các ứng viên." : undefined}
      >
        <div className="table-wrap"><CandidatesTable items={charts.candidates} /></div>
      </ChartCard>

      <GeoCard geo={charts.geo_scatter} pin={pin} busy={busy} />

      <ChartCard
        wide title="Giá/m² trung vị theo quận và loại nhà" pin={pin} busy={busy}
        note={`Trên bảng huấn luyện, chỉ nhóm có từ 5 tin · ${groups.length} quận có nhiều tin nhất`}
        empty={districtRows.length === 0 ? "Phiên bản này không có dữ liệu theo quận (phiên bản cũ hơn spec)." : undefined}
        controls={
          <>
            <TypeToggles types={districtTypes} hidden={hiddenDistrict} onToggle={(t) => setHiddenDistrict(flip(t))} />
            <label className="field-inline">Số quận
              <select value={districtCount} onChange={(e) => setDistrictCount(Number(e.target.value))}>
                {[6, 8, 12, 24].map((n) => <option key={n} value={n}>{n === 24 ? "Tất cả" : n}</option>)}
              </select>
            </label>
          </>
        }
        table={
          <table className="table">
            <caption className="sr-only">Giá trung vị theo quận và loại nhà</caption>
            <thead><tr><th scope="col">Quận</th>{districtTypes.map((t) => <th scope="col" className="num" key={t}>{typeName(t)}</th>)}</tr></thead>
            <tbody>{groupDistrictTypes(districtRows, 99).map((g) => <tr key={g.district}><th scope="row">{g.name}</th>{districtTypes.map((t) => <td className="num" key={t}>{g.values.has(t) ? `${formatNumber(g.values.get(t)?.median ?? 0, 1)} (${g.values.get(t)?.n})` : "—"}</td>)}</tr>)}</tbody>
          </table>
        }
        legend={hiddenNames.length > 0 ? <p className="muted">Đang ẩn: {hiddenNames.map(typeName).join(", ")}. Bật lại ở phần chọn loại nhà phía trên.</p> : <p className="muted">Số trong ngoặc ở bảng là số tin của nhóm.</p>}
      >
        <DistrictBars groups={groups} types={districtTypes.filter((t) => !hiddenDistrict.has(t))} />
      </ChartCard>
    </div>
  );
}

/** Trang Dashboard mô hình: chọn/so sánh phiên bản, KPI, biểu đồ theo phiên bản, xu hướng và lịch sử. */
export function Dashboard({ active }: { active: boolean }) {
  const { list, selected, compareId, detail, setSelectedId, setCompareId, reload } = useDashboard(active);
  const models = list.data ?? [];
  const compare = models.find((m) => m.id === compareId);

  if (list.status === "idle" || (list.status === "loading" && !list.data)) {
    return <div className="state state--page" role="status"><span className="dots" aria-hidden="true"><i /><i /><i /></span><p>Đang tải danh sách phiên bản…</p></div>;
  }
  if (list.status === "error") {
    return (
      <div className="state state--page state--error" role="alert">
        <h2>Không tải được dashboard</h2>
        <p>{list.error}</p>
        <p className="muted">Kiểm tra Prediction Server đã bật và backend đã cấu hình địa chỉ + khóa API của nó.</p>
        <button type="button" className="btn" onClick={reload}>Thử lại</button>
      </div>
    );
  }
  if (models.length === 0 || !selected) {
    return (
      <div className="state state--page" role="status">
        <h2>Chưa có phiên bản mô hình nào</h2>
        <p>Server mô hình chưa huấn luyện lần nào. Hãy chạy huấn luyện khởi tạo (bootstrap) ở Prediction Server rồi bấm “Tải lại”.</p>
        <button type="button" className="btn" onClick={reload}>Tải lại</button>
      </div>
    );
  }

  const ready = detail.data?.charts ? (detail.data as DashboardModelDetail & { charts: ModelCharts }) : null;
  const loading = detail.status === "loading";
  const option = (m: DashboardModelSummary) => `#${m.id} · ${formatDateTime(m.created_at)}${m.is_active ? " · đang chạy" : ""}`;

  return (
    <div className="dash" aria-busy={loading}>
      <div className="filters" role="group" aria-label="Chọn phiên bản">
        <label className="field-inline">Phiên bản
          <select value={selected.id} onChange={(e) => setSelectedId(Number(e.target.value))}>
            {models.map((m) => <option key={m.id} value={m.id}>{option(m)}</option>)}
          </select>
        </label>
        <label className="field-inline">So sánh với
          <select value={compareId ?? ""} onChange={(e) => setCompareId(e.target.value === "" ? null : Number(e.target.value))}>
            <option value="">Không so sánh</option>
            {models.filter((m) => m.id !== selected.id).map((m) => <option key={m.id} value={m.id}>{option(m)}</option>)}
          </select>
        </label>
        <button type="button" className="btn btn--ghost" onClick={reload} disabled={list.status === "loading"}>Tải lại</button>
      </div>

      <Kpis model={selected} />

      {compare && compare.id !== selected.id && (
        <section className="card-chart">
          <header className="card-chart__head"><div><h3>So sánh phiên bản</h3><p className="muted">Δ = #{selected.id} − #{compare.id}. Số đo lấy từ tập test của từng phiên bản nên chỉ so sánh gần đúng khi tập test khác nhau.</p></div></header>
          <CompareTable a={selected} b={compare} />
        </section>
      )}

      {!selected.has_charts ? (
        <div className="state state--page" role="status"><h2>Không có biểu đồ cho phiên bản #{selected.id}</h2><p>{missingMessage(selected)}</p></div>
      ) : detail.status === "error" ? (
        <div className="state state--page state--error" role="alert"><h2>Không tải được biểu đồ</h2><p>{detail.error}</p><button type="button" className="btn" onClick={reload}>Thử lại</button></div>
      ) : ready ? (
        <>
          {ready.id !== selected.id && <p className="muted" role="status">Đang tải phiên bản #{selected.id}… biểu đồ bên dưới vẫn là của phiên bản #{ready.id}.</p>}
          {ready.charts.approximate && <p className="notice" role="status">Biểu đồ của phiên bản #{ready.id} được dựng lại từ dữ liệu hiện tại nên chỉ gần đúng với lúc huấn luyện.</p>}
          <Charts key={ready.id} data={ready} busy={loading} />
        </>
      ) : (
        <div className="state state--page" role="status"><span className="dots" aria-hidden="true"><i /><i /><i /></span><p>Đang tải biểu đồ…</p></div>
      )}

      <div className="dash__grid">
        <section className="card-chart">
          <header className="card-chart__head"><div><h3>Xu hướng qua các phiên bản</h3><p className="muted">Bấm một điểm để xem phiên bản đó</p></div></header>
          {trendSeries(models, "r2_log").length === 0 ? <div className="state"><p>Chưa phiên bản nào có số đo.</p></div> : <TrendLines models={models} selectedId={selected.id} onSelect={setSelectedId} />}
        </section>
        <section className="card-chart">
          <header className="card-chart__head"><div><h3>Lịch sử phiên bản</h3><p className="muted">Trang này chỉ xem trạng thái; huấn luyện và kích hoạt do Prediction Server quản lý</p></div></header>
          <HistoryTable models={models} selectedId={selected.id} onSelect={setSelectedId} />
        </section>
      </div>
    </div>
  );
}
