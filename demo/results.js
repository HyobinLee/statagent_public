(function () {
  "use strict";

  const STAT_LABELS = { mean: "평균", median: "중앙값", mode: "최빈값", std: "표준편차", range: "범위", min: "최솟값", max: "최댓값", q1: "제1사분위수", q3: "제3사분위수", count: "개수" };

  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function fmt(v) {
    if (v === null || v === undefined || v === "") return "";
    if (Array.isArray(v)) return v.map(fmt).join(", ");
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
    return esc(v);
  }
  function table(head, rows) {
    return `<div class="scroll"><table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows
      .map((r) => `<tr>${r.map((v) => `<td>${fmt(v)}</td>`).join("")}</tr>`)
      .join("")}</tbody></table></div>`;
  }
  function rangeLabel(r) {
    const m = /^[([]\s*(-?[\d.]+),\s*(-?[\d.]+)\]$/.exec(String(r || ""));
    if (!m) return r;
    const a = Math.max(0, Math.round(Number(m[1]) * 10) / 10);
    const b = Math.round(Number(m[2]) * 10) / 10;
    return `${a} 초과 ${b} 이하`;
  }

  function render(res, opts) {
    opts = opts || {};
    if (!res) return "";
    const data = (res.result && res.result.data) || res.data || {};
    if (res.charts && res.charts.length) {
      return `<img src="${res.charts[0]}" alt="${esc(data.alt_text || "에이전트가 그린 그림")}">`;
    }
    if (data.groups && data.statistics !== undefined) {
      const cols = data.columns || Object.keys((data.groups[0] || {}).statistics || {});
      const stats = [];
      cols.forEach((col) => Object.keys(((data.groups[0] || {}).statistics || {})[col] || {}).forEach((s) => stats.push([col, s])));
      const multi = cols.length > 1;
      const head = [data.group_by, opts.countLabel || "개수"].concat(stats.map(([col, s]) => (multi ? `${col} ${STAT_LABELS[s] || s}` : STAT_LABELS[s] || s)));
      const rows = data.groups.map((g) => [g.group, g.sample_size ?? g.row_count].concat(stats.map(([col, s]) => g.statistics[col][s])));
      return table(head, rows);
    }
    if (data.statistics) {
      const cols = Object.keys(data.statistics);
      const stats = Object.keys(data.statistics[cols[0]] || {});
      return table(["항목"].concat(stats.map((s) => STAT_LABELS[s] || s)), cols.map((c) => [c].concat(stats.map((s) => data.statistics[c][s]))));
    }
    if (data.groups && data.overall) {
      const rows = [["전체", data.overall.sample_size, data.overall.pearson_correlation, data.overall.interpretation_label]].concat(
        data.groups.map((g) => [g.group, g.sample_size, g.pearson_correlation ?? "", g.interpretation_label || g.note || ""]),
      );
      return `<p class="muted">${esc(data.x_column)}와 ${esc(data.y_column)}의 상관계수, ${esc(data.group_by)}별</p>` + table([data.group_by, "자료 수", "상관계수", "읽는 법"], rows);
    }
    if (data.pearson_correlation !== undefined) {
      return table(["가로축 항목", "세로축 항목", "피어슨 상관계수", "자료 수", "관계"], [[data.x_column, data.y_column, data.pearson_correlation, data.sample_size, data.interpretation_label]]);
    }
    if (Array.isArray(data.rows) && data.rows.length) {
      const first = data.rows[0];
      if ("frequency" in first) {
        const total = data.rows.reduce((s, r) => s + (r.frequency || 0), 0);
        return table(["값", "도수", "상대도수"], data.rows.map((r) => [r.value ?? rangeLabel(r.range), r.frequency, total ? r.frequency / total : ""]));
      }
      const keys = Object.keys(first);
      return table(keys, data.rows.map((r) => keys.map((k) => r[k])));
    }
    return "";
  }

  function groupStats(rows, columns, groupCol, valueCols, stats) {
    const gi = columns.indexOf(groupCol);
    const groups = new Map();
    rows.forEach((r) => {
      const g = r[gi];
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(r);
    });
    const out = [];
    for (const [g, rs] of groups) {
      const st = {};
      valueCols.forEach((col) => {
        const ci = columns.indexOf(col);
        const vals = rs.map((r) => Number(r[ci])).filter((v) => !Number.isNaN(v)).sort((a, b) => a - b);
        const s = {};
        stats.forEach((name) => {
          if (name === "mean") s.mean = vals.reduce((a, b) => a + b, 0) / vals.length;
          if (name === "median") s.median = vals.length % 2 ? vals[(vals.length - 1) / 2] : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
        });
        st[col] = s;
      });
      out.push({ group: g, sample_size: rs.length, statistics: st });
    }
    out.sort((a, b) => b.sample_size - a.sample_size);
    return { result: { data: { group_by: groupCol, columns: valueCols, groups: out, statistics: {} } } };
  }

  window.DemoResults = { render, esc, fmt, table, groupStats };
})();
