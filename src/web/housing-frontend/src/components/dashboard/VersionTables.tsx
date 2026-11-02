import { useState } from "react";
import type { Candidate, DashboardModelSummary } from "../../api";
import { formatDateTime, formatDelta, formatMetric, formatNumber, metricDelta, paginate, statusBadge, triggerLabel } from "../../dashboard";
import type { MetricKey, Tone } from "../../dashboard";

const ICONS: Record<Tone, string> = { ok: "✓", info: "●", bad: "✕", muted: "–" };

/** Huy hiệu trạng thái: biểu tượng + chữ, màu chỉ là phần bổ trợ. */
export function Badge({ status, active = false }: { status: string; active?: boolean }) {
  const { label, tone } = statusBadge(status);
  return (
    <span className="badges">
      <span className={`badge-s badge-s--${tone}`}><span aria-hidden="true">{ICONS[tone]}</span> {label}</span>
      {active && <span className="badge-s badge-s--active"><span aria-hidden="true">★</span> Đang hoạt động</span>}
    </span>
  );
}

const PAGE_SIZE = 5;

interface HistoryProps {
  models: DashboardModelSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

/** Bảng lịch sử các phiên bản (chọn để xem), có phân trang. */
export function HistoryTable({ models, selectedId, onSelect }: HistoryProps) {
  const [page, setPage] = useState(1);
  const view = paginate(models, page, PAGE_SIZE);
  return (
    <div>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Lịch sử các phiên bản mô hình</caption>
          <thead>
            <tr>
              <th scope="col">Phiên bản</th>
              <th scope="col">Trạng thái</th>
              <th scope="col" className="num">R² log</th>
              <th scope="col" className="num hide-sm">MAE</th>
              <th scope="col" className="hide-sm">Kích hoạt bởi</th>
              <th scope="col"><span className="sr-only">Thao tác</span></th>
            </tr>
          </thead>
          <tbody>
            {view.rows.map((model) => (
              <tr key={model.id} className={model.id === selectedId ? "is-selected" : undefined}>
                <th scope="row"><strong>#{model.id}</strong><div className="muted">{formatDateTime(model.created_at)}</div></th>
                <td><Badge status={model.status} active={model.is_active} /></td>
                <td className="num">{formatMetric("r2_log", model.metrics?.r2_log)}</td>
                <td className="num hide-sm">{formatMetric("mae", model.metrics?.mae)}</td>
                <td className="hide-sm">{triggerLabel(model.trigger)}</td>
                <td>
                  <button type="button" className="btn btn--ghost" disabled={model.id === selectedId} aria-label={`Xem phiên bản ${model.id}`} onClick={() => onSelect(model.id)}>
                    {model.id === selectedId ? "Đang xem" : "Xem"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {view.pages > 1 && (
        <nav className="pager" aria-label="Phân trang lịch sử">
          <button type="button" className="btn btn--ghost" disabled={view.page <= 1} onClick={() => setPage(view.page - 1)}>Trước</button>
          <span className="muted">Trang {view.page}/{view.pages}</span>
          <button type="button" className="btn btn--ghost" disabled={view.page >= view.pages} onClick={() => setPage(view.page + 1)}>Sau</button>
        </nav>
      )}
    </div>
  );
}

export function CandidatesTable({ items }: { items: Candidate[] }) {
  return (
    <table className="table">
      <caption className="sr-only">Các mô hình ứng viên</caption>
      <thead>
        <tr>
          <th scope="col">Ứng viên</th>
          <th scope="col" className="num">CV R²</th>
          <th scope="col" className="num">Test R² log</th>
          <th scope="col" className="num">MAE</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.name} className={item.chosen ? "is-selected" : undefined}>
            <th scope="row">
              {item.name}
              {item.chosen && <span className="badge-s badge-s--ok"><span aria-hidden="true">✓</span> Được chọn</span>}
            </th>
            <td className="num">{formatNumber(item.cv_r2, 3)} <span className="muted">± {formatNumber(item.cv_std, 3)}</span></td>
            <td className="num">{formatNumber(item.test_r2_log, 3)}</td>
            <td className="num">{formatNumber(item.mae, 1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const METRICS: [MetricKey, string][] = [["r2_log", "R² log"], ["mae", "MAE (triệu/m²)"], ["mape", "MAPE"]];
const VERDICT = { better: "▲ Tốt hơn", worse: "▼ Kém hơn", same: "＝ Ngang nhau" };

function countRow(label: string, a: number | null, b: number | null) {
  const show = (value: number | null) => (value === null ? "—" : formatNumber(value));
  const diff = a !== null && b !== null ? `${a - b > 0 ? "+" : a - b < 0 ? "−" : ""}${formatNumber(Math.abs(a - b))}` : "—";
  return (
    <tr key={label}>
      <th scope="row">{label}</th>
      <td className="num">{show(a)}</td>
      <td className="num">{show(b)}</td>
      <td className="num">{diff}</td>
      <td className="muted">Chỉ để tham khảo</td>
    </tr>
  );
}

/** So sánh hai phiên bản: Δ = A − B kèm nhận xét tốt/kém hơn (chữ + biểu tượng, không chỉ màu). */
export function CompareTable({ a, b }: { a: DashboardModelSummary; b: DashboardModelSummary }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">{`So sánh phiên bản #${a.id} với #${b.id}`}</caption>
        <thead>
          <tr>
            <th scope="col">Chỉ số</th>
            <th scope="col" className="num">{`#${a.id}`}</th>
            <th scope="col" className="num">{`#${b.id}`}</th>
            <th scope="col" className="num">{`Δ (#${a.id} − #${b.id})`}</th>
            <th scope="col">Nhận xét</th>
          </tr>
        </thead>
        <tbody>
          {METRICS.map(([key, label]) => {
            const diff = metricDelta(key, a.metrics, b.metrics);
            return (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td className="num">{formatMetric(key, a.metrics?.[key])}</td>
                <td className="num">{formatMetric(key, b.metrics?.[key])}</td>
                <td className="num">{diff ? formatDelta(key, diff.delta) : "—"}</td>
                <td>{diff ? <span className={`verdict verdict--${diff.verdict}`}>{VERDICT[diff.verdict]}</span> : <span className="muted">Thiếu số đo</span>}</td>
              </tr>
            );
          })}
          {countRow("Dòng huấn luyện", a.train_rows, b.train_rows)}
          {countRow("Dòng kiểm thử", a.test_rows, b.test_rows)}
          <tr>
            <th scope="row">Ứng viên thắng</th>
            <td className="num">{a.best_candidate ?? "—"}</td>
            <td className="num">{b.best_candidate ?? "—"}</td>
            <td />
            <td />
          </tr>
        </tbody>
      </table>
    </div>
  );
}
