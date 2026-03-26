const kpiGrid = document.getElementById("kpiGrid");

const unresolvedTable = document.getElementById("unresolvedTable");
const unresolvedTableOverview = document.getElementById("unresolvedTableOverview");

const feedbackTable = document.getElementById("feedbackTable");
const feedbackTableOverview = document.getElementById("feedbackTableOverview");

const refreshBtn = document.getElementById("refreshBtn");
const answerModeDistribution = document.getElementById("answerModeDistribution");
const categoryDistribution = document.getElementById("categoryDistribution");

const searchInputOverviewUnresolved = document.getElementById("searchInputOverviewUnresolved");
const searchInputOverviewFeedback = document.getElementById("searchInputOverviewFeedback");
const searchInputUnresolved = document.getElementById("searchInputUnresolved");
const searchInputFeedback = document.getElementById("searchInputFeedback");

const chipsOverviewUnresolved = document.getElementById("chipsOverviewUnresolved");
const chipsOverviewFeedback = document.getElementById("chipsOverviewFeedback");
const chipsUnresolved = document.getElementById("chipsUnresolved");
const chipsFeedback = document.getElementById("chipsFeedback");
const sourcesTable = document.getElementById("sourcesTable");
const sourceDocumentsTable = document.getElementById("sourceDocumentsTable");
const addSourceBtn = document.getElementById("addSourceBtn");
const sourceNameInput = document.getElementById("sourceName");
const sourceTypeInput = document.getElementById("sourceType");
const sourceUriInput = document.getElementById("sourceUri");
const sourceFormatInput = document.getElementById("sourceFormat");
const jsonConvertTarget = document.getElementById("jsonConvertTarget");
const jsonConvertInput = document.getElementById("jsonConvertInput");
const jsonFileInput = document.getElementById("jsonFileInput");
const previewJsonBtn = document.getElementById("previewJsonBtn");
const importJsonBtn = document.getElementById("importJsonBtn");
const jsonMappingFields = document.getElementById("jsonMappingFields");
const jsonPreviewTable = document.getElementById("jsonPreviewTable");
const jsonErrorsBox = document.getElementById("jsonErrorsBox");

const expertModal = document.getElementById("expertModal");
const modalOverlay = document.getElementById("modalOverlay");
const closeModalBtn = document.getElementById("closeModalBtn");
const closeModalSecondaryBtn = document.getElementById("closeModalSecondaryBtn");
const saveExpertBtn = document.getElementById("saveExpertBtn");

const CATEGORY_OPTIONS = [
  { value: "", label: "All" },
  { value: "copyright", label: "Copyright" },
  { value: "trademark", label: "Trademark" },
  { value: "design", label: "Design" },
  { value: "patent", label: "Patent" },
  { value: "gi", label: "GI" },
];

const state = {
  currentView: "overview",
  summary: {},
  dashboardSummary: {},
  unresolvedItems: [],
  feedbackItems: [],
  unresolvedCategory: "",
  feedbackCategory: "",
  unresolvedSearch: "",
  feedbackSearch: "",
  dataSources: [],
  activeSourceId: null,
  sourceDocuments: [],
  jsonPreview: null,
};

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function normalizeCategory(value) {
  return String(value || "").trim().toLowerCase();
}

function prettyCategory(value) {
  if (!value) return "Unassigned";
  const str = String(value);
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function renderKpis(summary = {}) {
  const totals = summary.totals || {};
  const cards = [
    ["Total data sources", totals.data_sources_total || 0, "📦", "blue"],
    ["Total documents", totals.documents_total || 0, "📄", "purple"],
    ["Total chunks", totals.chunks_total || 0, "🧩", "green"],
    ["Q&A pairs", totals.qna_pairs_total || 0, "❓", "blue"],
    ["Expert answers", totals.expert_answers_total || 0, "✅", "purple"],
    ["Unresolved open", totals.unresolved_open || 0, "⚠", "blue"],
    ["Wrong reports open", totals.wrong_answer_reports_open || 0, "🚩", "blue"],
    ["Total chats", totals.chats_total || 0, "💬", "green"],
    ["Active sessions", totals.active_sessions || 0, "🟢", "green"],
    ["Recent sessions (24h)", totals.recent_sessions_24h || 0, "🕒", "purple"],
  ];

  kpiGrid.innerHTML = cards
    .map(
      (card) => `
        <div class="kpi-card">
          <div class="kpi-left">
            <div class="kpi-icon ${card[3]}">${card[2]}</div>
            <div>
              <p class="kpi-label">${escapeHtml(card[0])}</p>
            </div>
          </div>
          <div class="kpi-value">${card[1]}</div>
        </div>
      `
    )
    .join("");

  renderMiniDistributions(summary);
}

function renderSimpleList(target, rows, keyField) {
  if (!target) return;
  if (!rows || !rows.length) {
    target.innerHTML = `<div class="empty-state">Not enough data yet.</div>`;
    return;
  }

  target.innerHTML = `
    <table class="admin-table">
      <thead><tr><th>Name</th><th>Count</th></tr></thead>
      <tbody>
        ${rows
          .map((r) => `<tr><td>${escapeHtml(r[keyField] ?? "—")}</td><td>${escapeHtml(r.total ?? 0)}</td></tr>`)
          .join("")}
      </tbody>
    </table>
  `;
}

function renderMiniDistributions(summary = {}) {
  renderSimpleList(answerModeDistribution, summary.answer_mode_distribution || [], "answer_mode");
  renderSimpleList(categoryDistribution, summary.category_distribution || [], "category");
}

function renderChips(container, activeValue, onClickName) {
  if (!container) return;

  container.innerHTML = CATEGORY_OPTIONS.map(
    (item) => `
      <button
        type="button"
        class="chip-btn ${activeValue === item.value ? "active" : ""}"
        data-value="${item.value}"
        onclick="${onClickName}(this.dataset.value)"
      >
        ${escapeHtml(item.label)}
      </button>
    `
  ).join("");
}

function syncUnresolvedSearchInputs(value) {
  if (searchInputOverviewUnresolved) searchInputOverviewUnresolved.value = value;
  if (searchInputUnresolved) searchInputUnresolved.value = value;
}

function syncFeedbackSearchInputs(value) {
  if (searchInputOverviewFeedback) searchInputOverviewFeedback.value = value;
  if (searchInputFeedback) searchInputFeedback.value = value;
}

function getUnresolvedFilteredItems() {
  const category = normalizeCategory(state.unresolvedCategory);
  const search = String(state.unresolvedSearch || "").trim().toLowerCase();

  return state.unresolvedItems.filter((item) => {
    const itemCategory = normalizeCategory(
      item.final_category || item.user_selected_category || item.category
    );

    const categoryOk = !category || itemCategory === category;

    const haystack = [
      item.id,
      item.question,
      item.reason,
      item.created_at,
      item.final_category,
      item.user_selected_category,
      item.category,
    ]
      .join(" ")
      .toLowerCase();

    const searchOk = !search || haystack.includes(search);

    return categoryOk && searchOk;
  });
}

function getFeedbackFilteredItems() {
  const category = normalizeCategory(state.feedbackCategory);
  const search = String(state.feedbackSearch || "").trim().toLowerCase();

  return state.feedbackItems.filter((item) => {
    const itemCategory = normalizeCategory(item.category);
    const categoryOk = !category || itemCategory === category;

    const haystack = [
      item.id,
      item.question,
      item.comment,
      item.created_at,
      item.category,
      item.satisfied ? "satisfied" : "not satisfied",
    ]
      .join(" ")
      .toLowerCase();

    const searchOk = !search || haystack.includes(search);

    return categoryOk && searchOk;
  });
}

function buildUnresolvedTable(items) {
  if (!items.length) {
    return `<div class="empty-state">No unresolved queries found.</div>`;
  }

  return `
    <table class="admin-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Category</th>
          <th>Question</th>
          <th>Reason</th>
          <th>Created</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map((item) => {
            const encoded = encodeURIComponent(JSON.stringify(item));
            const categoryValue =
              item.final_category || item.user_selected_category || item.category || "unassigned";

            return `
              <tr>
                <td class="cell-id">${escapeHtml(item.id)}</td>
                <td>
                  <span class="tag tag-category">${escapeHtml(prettyCategory(categoryValue))}</span>
                </td>
                <td class="question-cell">${escapeHtml(item.question)}</td>
                <td class="reason-text">${escapeHtml(item.reason || "unresolved")}</td>
                <td class="created-text">${escapeHtml(item.created_at || "")}</td>
                <td>
                  <button class="action-btn answer-btn" type="button" data-row="${encoded}">
                    ✎ Answer
                  </button>
                </td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function buildFeedbackTable(items) {
  if (!items.length) {
    return `<div class="empty-state">No feedback records found.</div>`;
  }

  return `
    <table class="admin-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Category</th>
          <th>Question</th>
          <th>Status</th>
          <th>Comment</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td class="cell-id">${escapeHtml(item.id)}</td>
                <td>
                  <span class="tag tag-category">${escapeHtml(prettyCategory(item.category || "unassigned"))}</span>
                </td>
                <td class="question-cell">${escapeHtml(item.question)}</td>
                <td>
                  <span class="tag ${item.satisfied ? "tag-status-good" : "tag-status-bad"}">
                    ${item.satisfied ? "Satisfied" : "Not satisfied"}
                  </span>
                </td>
                <td>${escapeHtml(item.comment || "—")}</td>
                <td class="created-text">${escapeHtml(item.created_at || "")}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function bindAnswerButtons(root) {
  if (!root) return;

  root.querySelectorAll(".answer-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const payload = btn.getAttribute("data-row");
      const item = JSON.parse(decodeURIComponent(payload));
      openExpertModal(item);
    });
  });
}

function renderUnresolvedTables() {
  const html = buildUnresolvedTable(getUnresolvedFilteredItems());

  if (unresolvedTable) {
    unresolvedTable.innerHTML = html;
    bindAnswerButtons(unresolvedTable);
  }

  if (unresolvedTableOverview) {
    unresolvedTableOverview.innerHTML = html;
    bindAnswerButtons(unresolvedTableOverview);
  }

  renderChips(chipsOverviewUnresolved, state.unresolvedCategory, "setUnresolvedCategory");
  renderChips(chipsUnresolved, state.unresolvedCategory, "setUnresolvedCategory");
}

function renderFeedbackTables() {
  const html = buildFeedbackTable(getFeedbackFilteredItems());

  if (feedbackTable) {
    feedbackTable.innerHTML = html;
  }

  if (feedbackTableOverview) {
    feedbackTableOverview.innerHTML = html;
  }

  renderChips(chipsOverviewFeedback, state.feedbackCategory, "setFeedbackCategory");
  renderChips(chipsFeedback, state.feedbackCategory, "setFeedbackCategory");
}

function renderAllTables() {
  renderUnresolvedTables();
  renderFeedbackTables();
}

function openExpertModal(item) {
  document.getElementById("expertUnresolvedId").value = item.id || "";
  document.getElementById("expertQuestion").value = item.question || "";
  document.getElementById("expertNormalizedQuestion").value = item.normalized_question || "";
  document.getElementById("expertCategory").value =
    item.final_category || item.user_selected_category || item.category || "patent";
  document.getElementById("expertAnswer").value = "";
  document.getElementById("expertSourceNote").value = "";

  expertModal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeExpertModal() {
  expertModal.classList.add("hidden");
  document.body.style.overflow = "";
}

async function loadSummary() {
  const res = await fetch("/api/admin/dashboard-summary");
  const data = await res.json();
  state.dashboardSummary = data || {};
  renderKpis(data || {});
}

async function loadUnresolved() {
  const res = await fetch("/api/admin/unresolved");
  const data = await res.json();
  state.unresolvedItems = data.items || [];
  renderUnresolvedTables();
}

async function loadFeedback() {
  const res = await fetch("/api/admin/feedback");
  const data = await res.json();
  state.feedbackItems = data.items || [];
  renderFeedbackTables();
}

function buildSourcesTable(items) {
  if (!items.length) {
    return `<div class="empty-state">No data sources configured.</div>`;
  }

  return `
    <table class="admin-table">
      <thead>
        <tr>
          <th>ID</th><th>Name</th><th>Type</th><th>Format</th><th>Status</th>
          <th>Docs</th><th>Chunks</th><th>Last Ingestion</th><th>Actions</th>
        </tr>
      </thead>
      <tbody>
      ${items.map((item) => `
        <tr>
          <td>${escapeHtml(item.id)}</td>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(item.source_type)}</td>
          <td>${escapeHtml(item.source_format || "unknown")}</td>
          <td>${escapeHtml(item.status)}</td>
          <td>${escapeHtml(item.document_count || 0)}</td>
          <td>${escapeHtml(item.chunk_count || 0)}</td>
          <td>${escapeHtml(item.last_ingestion_status || "never")} ${escapeHtml(item.last_ingestion_at || "")}</td>
          <td>
            <button class="action-btn" onclick="viewSourceDocuments(${item.id})">Docs</button>
            <button class="action-btn" onclick="toggleSourceStatus(${item.id}, '${item.status === "enabled" ? "disabled" : "enabled"}')">${item.status === "enabled" ? "Disable" : "Enable"}</button>
            <button class="action-btn" onclick="triggerSourceReingest(${item.id})">Reingest</button>
          </td>
        </tr>
      `).join("")}
      </tbody>
    </table>
  `;
}

function renderSources() {
  if (!sourcesTable) return;
  sourcesTable.innerHTML = buildSourcesTable(state.dataSources || []);
}

function renderSourceDocuments() {
  if (!sourceDocumentsTable) return;
  if (!state.sourceDocuments.length) {
    sourceDocumentsTable.innerHTML = `<div class="empty-state">Select a source to view documents.</div>`;
    return;
  }

  sourceDocumentsTable.innerHTML = `
    <table class="admin-table">
      <thead>
        <tr>
          <th>File</th><th>Version</th><th>Hash</th><th>Chunks</th><th>Status</th><th>Ingested At</th>
        </tr>
      </thead>
      <tbody>
        ${state.sourceDocuments.map((d) => `
          <tr>
            <td>${escapeHtml(d.file_name)}</td>
            <td>${escapeHtml(d.version || "—")}</td>
            <td>${escapeHtml(d.content_hash || "—")}</td>
            <td>${escapeHtml(d.chunk_count || 0)}</td>
            <td>${escapeHtml(d.status || "active")}</td>
            <td>${escapeHtml(d.ingested_at || "—")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

async function loadDataSources() {
  const res = await fetch("/api/admin/data-sources");
  const data = await res.json();
  state.dataSources = data.items || [];
  renderSources();
}

async function viewSourceDocuments(sourceId) {
  state.activeSourceId = sourceId;
  const res = await fetch(`/api/admin/data-sources/${sourceId}/documents`);
  const data = await res.json();
  state.sourceDocuments = data.items || [];
  renderSourceDocuments();
}

async function addSource() {
  const payload = {
    name: (sourceNameInput?.value || "").trim(),
    source_type: (sourceTypeInput?.value || "manual_upload").trim(),
    source_format: (sourceFormatInput?.value || "manual").trim().toLowerCase(),
    uri: (sourceUriInput?.value || "").trim() || null,
  };

  if (!payload.name) {
    alert("Source name is required.");
    return;
  }

  const res = await fetch("/api/admin/data-sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    alert(data.detail || data.message || "Failed to create source.");
    return;
  }

  sourceNameInput.value = "";
  sourceUriInput.value = "";
  sourceFormatInput.value = "";
  await loadDataSources();
}

async function toggleSourceStatus(sourceId, status) {
  const res = await fetch(`/api/admin/data-sources/${sourceId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    alert(data.detail || data.message || "Failed to update source status.");
    return;
  }

  await loadDataSources();
}

async function triggerSourceReingest(sourceId) {
  const res = await fetch(`/api/admin/data-sources/${sourceId}/reingest`, { method: "POST" });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    alert(data.detail || data.message || "Failed to queue reingest.");
    return;
  }
  await loadDataSources();
}

function renderJsonPreview(previewData) {
  state.jsonPreview = previewData || null;
  if (!jsonMappingFields || !jsonPreviewTable || !jsonErrorsBox) return;

  if (!previewData) {
    jsonMappingFields.innerHTML = "";
    jsonPreviewTable.innerHTML = "";
    jsonErrorsBox.innerHTML = "";
    return;
  }

  const fields = previewData.mapping_fields || [];
  jsonMappingFields.innerHTML = `
    <div><strong>Target:</strong> ${escapeHtml(previewData.target || "")}</div>
    <div><strong>Record count:</strong> ${escapeHtml(previewData.record_count || 0)}</div>
    <div><strong>Required fields:</strong> ${escapeHtml(fields.join(", ") || "—")}</div>
  `;

  const rows = previewData.preview || [];
  if (!rows.length) {
    jsonPreviewTable.innerHTML = `<div class="empty-state">No records to preview.</div>`;
  } else {
    jsonPreviewTable.innerHTML = `
      <table class="admin-table">
        <thead><tr><th>Row</th><th>Mapped Fields</th><th>Extra Fields</th></tr></thead>
        <tbody>
          ${rows.map((r) => `
            <tr>
              <td>${escapeHtml(r.row)}</td>
              <td><pre>${escapeHtml(JSON.stringify(r.mapped || {}, null, 2))}</pre></td>
              <td>${escapeHtml((r.extra_fields || []).join(", ") || "—")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  const errors = previewData.errors || [];
  if (!errors.length) {
    jsonErrorsBox.innerHTML = `<div class="empty-state">No validation errors.</div>`;
  } else {
    jsonErrorsBox.innerHTML = `
      <div class="empty-state" style="color:#b91c1c; text-align:left;">
        <strong>Validation errors (${errors.length}):</strong>
        <ul>${errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul>
      </div>
    `;
  }
}

async function previewJsonConvert() {
  const target = (jsonConvertTarget?.value || "").trim();
  const jsonText = (jsonConvertInput?.value || "").trim();
  if (!target || !jsonText) {
    alert("Please select target and provide JSON.");
    return;
  }

  const res = await fetch("/api/admin/json-convert/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, json_text: jsonText }),
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Preview failed.");
    return;
  }
  renderJsonPreview(data);
}

async function importJsonConvert() {
  const target = (jsonConvertTarget?.value || "").trim();
  const jsonText = (jsonConvertInput?.value || "").trim();
  if (!target || !jsonText) {
    alert("Please select target and provide JSON.");
    return;
  }

  const res = await fetch("/api/admin/json-convert/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target, json_text: jsonText }),
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.detail || "Import failed.");
    return;
  }

  const msg = `Imported: ${data.created_count || 0}, Errors: ${data.error_count || 0}, Audit Log ID: ${data.audit_log_id || "n/a"}`;
  alert(msg);
  if (data.errors && data.errors.length) {
    renderJsonPreview({
      target,
      record_count: 0,
      mapping_fields: state.jsonPreview?.mapping_fields || [],
      preview: state.jsonPreview?.preview || [],
      errors: data.errors,
    });
  }
  await refreshAll();
}

async function saveExpertAnswer() {
  const payload = {
    unresolved_query_id: Number(document.getElementById("expertUnresolvedId").value || 0) || null,
    question: document.getElementById("expertQuestion").value.trim(),
    normalized_question: document.getElementById("expertNormalizedQuestion").value.trim(),
    category: document.getElementById("expertCategory").value,
    expert_answer: document.getElementById("expertAnswer").value.trim(),
    source_note: document.getElementById("expertSourceNote").value.trim(),
  };

  if (!payload.question) {
    alert("Question is missing.");
    return;
  }

  if (!payload.expert_answer) {
    alert("Please enter an expert answer.");
    return;
  }

  saveExpertBtn.disabled = true;
  saveExpertBtn.textContent = "Saving...";

  try {
    const res = await fetch("/api/admin/expert-answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      alert(data.message || "Failed to save expert answer");
      return;
    }

    closeExpertModal();
    await refreshAll();
  } catch (error) {
    console.error(error);
    alert("Something went wrong while saving the expert answer.");
  } finally {
    saveExpertBtn.disabled = false;
    saveExpertBtn.textContent = "Save Answer";
  }
}

async function refreshAll() {
  refreshBtn.disabled = true;
  refreshBtn.innerHTML = `<span>↻</span><span>Refreshing...</span>`;

  try {
    await Promise.all([loadSummary(), loadUnresolved(), loadFeedback(), loadDataSources()]);
  } catch (error) {
    console.error(error);
    alert("Failed to load dashboard data.");
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.innerHTML = `<span>↻</span><span>Refresh</span>`;
  }
}

function setActiveView(sectionName) {
  state.currentView = sectionName;

  const menuItems = document.querySelectorAll(".menu-item");
  const sections = document.querySelectorAll(".view-section");

  menuItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.section === sectionName);
  });

  sections.forEach((section) => {
    const isTarget = section.id === `section-${sectionName}`;
    section.classList.toggle("active-view", isTarget);
    section.classList.toggle("hidden-view", !isTarget);
  });
}

function setupSidebarNavigation() {
  const menuItems = document.querySelectorAll(".menu-item");

  menuItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const section = btn.dataset.section;
      setActiveView(section);
    });
  });
}

function setupSearch() {
  if (searchInputOverviewUnresolved) {
    searchInputOverviewUnresolved.addEventListener("input", (e) => {
      state.unresolvedSearch = e.target.value || "";
      syncUnresolvedSearchInputs(state.unresolvedSearch);
      renderUnresolvedTables();
    });
  }

  if (searchInputUnresolved) {
    searchInputUnresolved.addEventListener("input", (e) => {
      state.unresolvedSearch = e.target.value || "";
      syncUnresolvedSearchInputs(state.unresolvedSearch);
      renderUnresolvedTables();
    });
  }

  if (searchInputOverviewFeedback) {
    searchInputOverviewFeedback.addEventListener("input", (e) => {
      state.feedbackSearch = e.target.value || "";
      syncFeedbackSearchInputs(state.feedbackSearch);
      renderFeedbackTables();
    });
  }

  if (searchInputFeedback) {
    searchInputFeedback.addEventListener("input", (e) => {
      state.feedbackSearch = e.target.value || "";
      syncFeedbackSearchInputs(state.feedbackSearch);
      renderFeedbackTables();
    });
  }
}

function exportUnresolved() {
  window.open("/api/admin/export/unresolved", "_blank");
}

function exportFeedback() {
  window.open("/api/admin/export/feedback", "_blank");
}

function setUnresolvedCategory(value) {
  state.unresolvedCategory = value || "";
  renderUnresolvedTables();
}

function setFeedbackCategory(value) {
  state.feedbackCategory = value || "";
  renderFeedbackTables();
}

window.exportUnresolved = exportUnresolved;
window.exportFeedback = exportFeedback;
window.setUnresolvedCategory = setUnresolvedCategory;
window.setFeedbackCategory = setFeedbackCategory;
window.viewSourceDocuments = viewSourceDocuments;
window.toggleSourceStatus = toggleSourceStatus;
window.triggerSourceReingest = triggerSourceReingest;

refreshBtn.addEventListener("click", refreshAll);

closeModalBtn.addEventListener("click", closeExpertModal);
closeModalSecondaryBtn.addEventListener("click", closeExpertModal);
modalOverlay.addEventListener("click", closeExpertModal);
saveExpertBtn.addEventListener("click", saveExpertAnswer);
if (addSourceBtn) addSourceBtn.addEventListener("click", addSource);
if (previewJsonBtn) previewJsonBtn.addEventListener("click", previewJsonConvert);
if (importJsonBtn) importJsonBtn.addEventListener("click", importJsonConvert);
if (jsonFileInput) {
  jsonFileInput.addEventListener("change", async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const text = await file.text();
    if (jsonConvertInput) jsonConvertInput.value = text;
  });
}

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !expertModal.classList.contains("hidden")) {
    closeExpertModal();
  }
});

setupSidebarNavigation();
setupSearch();
setActiveView("overview");
refreshAll();
