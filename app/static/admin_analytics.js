function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function table(headers, rows) {
  if (!rows || !rows.length) return `<div class="empty-state">No data available for selected range.</div>`;
  return `
    <table class="admin-table">
      <thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function renderInsights(data) {
  const insights = [
    ["Top Categories", (data.top_categories || []).map((x) => `${x.category} (${x.total})`).join(", ") || "—"],
    ["Top Repeated Queries", (data.top_repeated_queries || []).slice(0, 3).map((x) => `${x.query} (${x.total})`).join(" | ") || "—"],
    ["Top Failed Queries", (data.top_failed_queries || []).slice(0, 3).map((x) => `${x.query} (${x.total})`).join(" | ") || "—"],
    ["Source Contribution", (data.source_contribution || []).slice(0, 3).map((x) => `${x.source} (${x.total})`).join(" | ") || "—"],
    ["Latency Avg (ms)", data.latency_metrics?.avg_ms ?? "N/A"],
    ["Latency Sample", data.latency_metrics?.sample_size ?? 0],
  ];

  document.getElementById("insightsGrid").innerHTML = insights
    .map(([k, v]) => `
      <div class="kpi-card">
        <div class="kpi-left"><h3 class="kpi-title">${esc(k)}</h3></div>
        <div class="kpi-value" style="font-size:14px;max-width:300px;white-space:normal;text-align:right;">${esc(v)}</div>
      </div>
    `)
    .join("");
}

async function loadAnalytics() {
  const rangeDays = document.getElementById("rangeDays").value;
  const res = await fetch(`/api/admin/analytics?range_days=${encodeURIComponent(rangeDays)}`);
  if (!res.ok) return;
  const data = await res.json();

  document.getElementById("chatVolumeTable").innerHTML = table(
    ["Date", "Chats"],
    (data.chat_volume || []).map((x) => [x.bucket, x.total])
  );

  const unresolvedMap = new Map((data.unresolved_trend || []).map((x) => [x.bucket, x.total]));
  const wrongMap = new Map((data.wrong_answer_trend || []).map((x) => [x.bucket, x.total]));
  const allDates = [...new Set([...unresolvedMap.keys(), ...wrongMap.keys()])].sort();
  document.getElementById("trendTable").innerHTML = table(
    ["Date", "Unresolved", "Wrong Answers"],
    allDates.map((d) => [d, unresolvedMap.get(d) || 0, wrongMap.get(d) || 0])
  );

  document.getElementById("answerModeRateTable").innerHTML = table(
    ["Mode", "Count"],
    (data.answer_mode_rate || []).map((x) => [x.answer_mode, x.total])
  );

  document.getElementById("feedbackTrendTable").innerHTML = table(
    ["Date", "Total", "Satisfied", "Rate"],
    (data.feedback_satisfaction_trend || []).map((x) => [x.bucket, x.total, x.satisfied, x.satisfaction_rate])
  );

  renderInsights(data);
}

document.getElementById("reloadAnalytics").addEventListener("click", loadAnalytics);
document.getElementById("rangeDays").addEventListener("change", loadAnalytics);
loadAnalytics();
