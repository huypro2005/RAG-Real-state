import { Component, useState } from "react";
import type { ReactNode } from "react";

/** Lỗi khi vẽ một biểu đồ chỉ làm hỏng khung của biểu đồ đó, không sập cả trang. */
class ChartBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="state state--error" role="alert">
        <p>Biểu đồ này gặp lỗi khi vẽ. Các biểu đồ khác vẫn dùng được.</p>
        <button type="button" className="btn btn--ghost" onClick={() => this.setState({ failed: false })}>Thử lại</button>
      </div>
    );
  }
}

interface Props {
  title: string;
  note?: string; // dòng phụ: đơn vị, phạm vi
  pin?: string; // ghim phiên bản của dữ liệu đang vẽ, vd. "Phiên bản #3"
  controls?: ReactNode;
  legend?: ReactNode;
  table?: ReactNode; // bản thay thế dạng bảng của biểu đồ
  empty?: string; // có giá trị = không có dữ liệu cho biểu đồ này
  busy?: boolean;
  wide?: boolean;
  children: ReactNode;
}

/** Khung biểu đồ: tiêu đề, bộ điều khiển, legend, nút chuyển sang bảng; trạng thái rỗng/bận riêng cho từng biểu đồ. */
export function ChartCard({ title, note, pin, controls, legend, table, empty, busy, wide, children }: Props) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className={`card-chart${wide ? " card-chart--wide" : ""}`} aria-busy={busy}>
      <header className="card-chart__head">
        <div>
          <h3>{title}</h3>
          {note && <p className="muted">{note}</p>}
        </div>
        <div className="card-chart__tools">
          {pin && <span className="pill">{pin}</span>}
          {table && !empty && (
            <button type="button" className="btn btn--ghost" aria-pressed={asTable} onClick={() => setAsTable((on) => !on)}>
              {asTable ? "Xem biểu đồ" : "Xem bảng"}
            </button>
          )}
        </div>
      </header>
      {controls && !empty && !asTable && <div className="card-chart__controls">{controls}</div>}
      <div className={busy ? "card-chart__body card-chart__body--busy" : "card-chart__body"}>
        {empty ? (
          <div className="state"><p>{empty}</p></div>
        ) : (
          <ChartBoundary>{asTable && table ? <div className="table-wrap">{table}</div> : children}</ChartBoundary>
        )}
      </div>
      {legend && !empty && !asTable && <div className="card-chart__legend">{legend}</div>}
    </section>
  );
}
