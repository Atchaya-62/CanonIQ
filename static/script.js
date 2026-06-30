const state = {
  uploadKind: "folder",
  report: null,
  publicPayload: null,
  currentCandidateId: null,
  files: [],
};

const dropzone = document.getElementById("dropzone");
const folderInput = document.getElementById("folderInput");
const zipInput = document.getElementById("zipInput");
const transformBtn = document.getElementById("transformBtn");
const downloadJsonBtn = document.getElementById("downloadJsonBtn");
const downloadCsvBtn = document.getElementById("downloadCsvBtn");
const explainBtn = document.getElementById("explainBtn");
const backBtn = document.getElementById("backBtn");
const jsonViewer = document.getElementById("jsonViewer");
const statusText = document.getElementById("statusText");
const fileLabel = document.getElementById("fileLabel");
const selectedFiles = document.getElementById("selectedFiles");
const uploadPage = document.getElementById("uploadPage");
const resultsPage = document.getElementById("resultsPage");
const resultsActions = document.getElementById("resultsActions");
const statusPanel = document.getElementById("statusPanel");
const modal = document.getElementById("modal");
const closeModalBtn = document.getElementById("closeModalBtn");
const explainViewer = document.getElementById("explainViewer");
const candidateSelect = document.getElementById("candidateSelect");

const apiTransform = "/api/transform";
const apiDownloadJson = "/api/download/json";
const apiDownloadCsv = "/api/download/csv";

folderInput.addEventListener("change", () => {
  state.files = Array.from(folderInput.files || []);
  state.uploadKind = "folder";
  updateSelectionLabel();
});

zipInput.addEventListener("change", () => {
  state.uploadKind = "zip";
  state.files = Array.from(zipInput.files || []);
  updateSelectionLabel();
});

transformBtn.addEventListener("click", transform);
downloadJsonBtn.addEventListener("click", () => download(apiDownloadJson, "candidate_report.json"));
downloadCsvBtn.addEventListener("click", () => download(apiDownloadCsv, "candidate_report.csv"));
explainBtn.addEventListener("click", openExplainModal);
backBtn.addEventListener("click", goBack);
closeModalBtn.addEventListener("click", closeModal);
modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    closeModal();
  }
});
candidateSelect.addEventListener("change", renderExplanation);

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  const droppedFiles = Array.from(event.dataTransfer.files || []);
  if (!droppedFiles.length) {
    return;
  }
  state.files = droppedFiles;
  state.uploadKind = droppedFiles.length === 1 && droppedFiles[0].name.toLowerCase().endsWith(".zip") ? "zip" : "folder";
  updateSelectionLabel();
});

function updateSelectionLabel() {
  if (!state.files.length) {
    fileLabel.textContent = "No input selected";
    selectedFiles.classList.add("hidden");
    selectedFiles.innerHTML = "";
    return;
  }
  selectedFiles.classList.remove("hidden");
  if (state.uploadKind === "zip") {
    fileLabel.textContent = "ZIP Loaded";
    selectedFiles.innerHTML = `<strong>${escapeHtml(state.files[0].name)}</strong>`;
    return;
  }
  fileLabel.textContent = "Folder Loaded";
  const names = state.files
    .map((file) => file.name)
    .slice(0, 8)
    .map((name) => `<div>${escapeHtml(name)}</div>`)
    .join("");
  const extra = state.files.length > 8 ? `<div>+ ${state.files.length - 8} more</div>` : "";
  selectedFiles.innerHTML = names + extra;
}

async function transform() {
  if (!state.files.length) {
    setStatus("Please choose files first.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("upload_kind", state.uploadKind);
  if (state.uploadKind === "zip") {
    formData.append("zip_file", state.files[0]);
  } else {
    state.files.forEach((file) => {
      const relativePath = file.webkitRelativePath || file.name;
      formData.append("folder_files", file, relativePath);
    });
  }

  setBusy(true);
  setStatus("Transforming...", "processing");

  try {
    const response = await fetch(apiTransform, {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw new Error(payload.error || "Transform failed.");
    }

    state.report = payload.report;
    state.publicPayload = buildPublicPayload(payload.report);
    state.currentCandidateId = "0";
    jsonViewer.innerHTML = highlightJson(JSON.stringify(state.publicPayload, null, 2));
    downloadJsonBtn.disabled = false;
    downloadCsvBtn.disabled = false;
    explainBtn.disabled = false;
    showResultsPage();
    setStatus("Transformation Complete", "ready");
  } catch (error) {
    setStatus(error.message || "Error", "error");
  } finally {
    setBusy(false);
  }
}

async function download(endpoint, filename) {
  if (!state.publicPayload) {
    return;
  }
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.publicPayload),
  });
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function openExplainModal() {
  if (!state.report?.candidates?.length) {
    return;
  }
  candidateSelect.innerHTML = "";
  state.report.candidates.forEach((candidate, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = candidate.name || candidate.candidate_id || "Candidate";
    candidateSelect.appendChild(option);
  });
  state.currentCandidateId = candidateSelect.value;
  modal.classList.remove("hidden");
  renderExplanation();
}

function renderExplanation() {
  if (!state.report) {
    return;
  }
  const selectedIndex = Number.parseInt(candidateSelect.value || state.currentCandidateId || "0", 10);
  const candidate = state.report.candidates[selectedIndex] || state.report.candidates[0];
  const explanationKey = Object.keys(state.report.explanations || {})[selectedIndex];
  const explanation = state.report.explanations?.[explanationKey] || {};
  explainViewer.innerHTML = buildExplanationHtml(candidate, explanation);
}

function closeModal() {
  modal.classList.add("hidden");
}

function goBack() {
  resetUploadState();
  uploadPage.classList.remove("hidden");
  resultsPage.classList.add("hidden");
  resultsActions.classList.add("hidden");
  statusPanel.classList.add("hidden");
  setStatus("Ready", "ready");
}

function showResultsPage() {
  uploadPage.classList.add("hidden");
  resultsPage.classList.remove("hidden");
  resultsActions.classList.remove("hidden");
  statusPanel.classList.remove("hidden");
}

function setBusy(isBusy) {
  transformBtn.disabled = isBusy;
}

function setStatus(message, variant) {
  statusText.textContent = message;
  statusText.className = `status ${variant}`;
}

function highlightJson(jsonText) {
  const escaped = escapeHtml(jsonText);
  return escaped
    .replace(/(&quot;.*?&quot;)(?=\s*:)/g, '<span class="json-key">$1</span>')
    .replace(/: (&quot;.*?&quot;)/g, ': <span class="json-string">$1</span>')
    .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="json-number">$1</span>')
    .replace(/\b(true|false)\b/g, '<span class="json-bool">$1</span>')
    .replace(/\bnull\b/g, '<span class="json-null">null</span>');
}

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => renderValue(item)).join(" + ") || "n/a";
  }
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}

function titleCase(value) {
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function appendListSection(lines, title, values) {
  const items = Array.isArray(values) ? values.filter((item) => item !== null && item !== undefined && item !== "") : [];
  if (!items.length) {
    return;
  }
  lines.push(title);
  items.forEach((item) => {
    lines.push(`- ${renderSummary(item)}`);
  });
  lines.push("");
}

function appendMatchSection(lines, title, values) {
  const items = Array.isArray(values) ? values.filter(Boolean) : [];
  if (!items.length) {
    return;
  }
  lines.push(title);
  items.forEach((item) => {
    lines.push(`- ${renderMatchItem(item)}`);
  });
  lines.push("");
}

function appendFieldSection(lines, title, fields) {
  const entries = fields && typeof fields === "object" ? Object.entries(fields) : [];
  if (!entries.length) {
    return;
  }
  lines.push(title);
  entries.forEach(([fieldName, detail]) => {
    lines.push(`${titleCase(fieldName)}`);
    formatDetail(detail).forEach((line) => lines.push(line));
  });
  lines.push("");
}

function appendJsonSection(lines, title, value) {
  if (!value || (typeof value === "object" && !Array.isArray(value) && !Object.keys(value).length)) {
    return;
  }
  lines.push(title);
  const jsonText = JSON.stringify(value, null, 2).split("\n");
  jsonText.forEach((line) => lines.push(`  ${line}`));
  lines.push("");
}

function formatDetail(detail) {
  if (detail === null || detail === undefined || detail === "") {
    return ["  n/a"];
  }
  if (Array.isArray(detail)) {
    return detail.length ? detail.map((item) => `  - ${renderSummary(item)}`) : ["  n/a"];
  }
  if (typeof detail !== "object") {
    return [`  ${renderValue(detail)}`];
  }
  const lines = [];
  if (Object.prototype.hasOwnProperty.call(detail, "selected_value")) {
    lines.push(`  Value: ${renderValue(detail.selected_value)}`);
  } else if (Object.prototype.hasOwnProperty.call(detail, "value")) {
    lines.push(`  Value: ${renderValue(detail.value)}`);
  }
  if (detail.selected_source || detail.source) {
    lines.push(`  Source: ${renderValue(detail.selected_source || detail.source)}`);
  }
  if (detail.selected_confidence !== undefined || detail.confidence !== undefined) {
    lines.push(`  Confidence: ${formatPercent(detail.selected_confidence ?? detail.confidence)}`);
  }
  if (detail.selected_reason || detail.reason) {
    lines.push(`  Reason: ${renderValue(detail.selected_reason || detail.reason)}`);
  }
  if (Array.isArray(detail.sources) && detail.sources.length) {
    lines.push(`  Sources: ${detail.sources.join(", ")}`);
  }
  if (Array.isArray(detail.items) && detail.items.length) {
    lines.push("  Evidence:");
    detail.items.slice(0, 5).forEach((item) => {
      lines.push(`    - ${renderSummary(item)}`);
    });
    if (detail.items.length > 5) {
      lines.push(`    - + ${detail.items.length - 5} more`);
    }
  }
  if (Array.isArray(detail.values) && detail.values.length) {
    lines.push("  Values:");
    detail.values.slice(0, 5).forEach((item) => {
      lines.push(`    - ${renderSummary(item)}`);
    });
    if (detail.values.length > 5) {
      lines.push(`    - + ${detail.values.length - 5} more`);
    }
  }
  if (!lines.length) {
    lines.push(`  ${renderValue(detail)}`);
  }
  return lines;
}

function renderSummary(value) {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  if (Array.isArray(value)) {
    return value.map((item) => renderSummary(item)).join(" + ") || "n/a";
  }
  if (typeof value !== "object") {
    return String(value);
  }
  const parts = [];
  if (value.value !== undefined && value.value !== null && value.value !== "") {
    parts.push(renderValue(value.value));
  } else {
    for (const key of ["company", "title", "institution", "degree", "field_of_study", "location"]) {
      if (value[key]) {
        parts.push(String(value[key]));
      }
    }
  }
  if (value.source || value.selected_source) {
    parts.push(`from ${renderValue(value.source || value.selected_source)}`);
  }
  if (value.confidence !== undefined || value.selected_confidence !== undefined) {
    parts.push(`confidence ${formatPercent(value.confidence ?? value.selected_confidence)}`);
  }
  return parts.join(" | ") || JSON.stringify(value);
}

function renderMatchItem(value) {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  if (typeof value !== "object") {
    return String(value);
  }
  const parts = [];
  if (value.field) {
    parts.push(titleCase(value.field));
  }
  if (value.selected_value !== undefined || value.value !== undefined) {
    parts.push(renderValue(value.selected_value ?? value.value));
  }
  if (value.selected_source || value.source) {
    parts.push(`from ${renderValue(value.selected_source || value.source)}`);
  }
  if (value.selected_confidence !== undefined || value.confidence !== undefined) {
    parts.push(`confidence ${formatPercent(value.selected_confidence ?? value.confidence)}`);
  }
  if (value.selected_reason || value.reason) {
    parts.push(renderValue(value.selected_reason || value.reason));
  }
  if (!parts.length) {
    return JSON.stringify(value);
  }
  return parts.join(" | ");
}

function buildExplanationHtml(candidate, explanation) {
  const summaryLines = [];
  summaryLines.push(`<strong>Candidate:</strong> ${escapeHtml(candidate.name || "Unknown")}`);
  if (explanation.cluster_size) {
    summaryLines.push(`<strong>Cluster size:</strong> ${escapeHtml(renderValue(explanation.cluster_size))}`);
  }
  if (explanation.merge_decision) {
    summaryLines.push(`<strong>Decision:</strong> ${escapeHtml(titleCase(explanation.merge_decision))}`);
  }
  if (typeof explanation.merge_score === "number") {
    summaryLines.push(`<strong>Merge score:</strong> ${escapeHtml(formatPercent(explanation.merge_score))}`);
  }
  if (typeof explanation.merge_threshold === "number") {
    summaryLines.push(`<strong>Threshold:</strong> ${escapeHtml(formatPercent(explanation.merge_threshold))}`);
  }

  const summary = `
    <section class="report-summary">
      <h3>Merge Summary</h3>
      <p>${escapeHtml(toSummaryText(explanation.merge_summary || ""))}</p>
      <div class="report-kv">
        ${summaryLines.map((line) => `<div class="report-kv-item">${line}</div>`).join("")}
      </div>
    </section>
  `;

  const cards = [];
  cards.push(renderCandidateCard(candidate));
  cards.push(renderListCard("Sources", explanation.sources_merged));
  cards.push(renderListCard("Merge Details", explanation.merge_details));
  cards.push(renderMatchCard("Matching Criteria", explanation.matching_details || explanation.matched_on));
  cards.push(renderFieldCard("Field Resolution", explanation.field_details || explanation.field_selection));
  cards.push(renderJsonCard("Conflict Resolution", explanation.field_conflicts));
  cards.push(renderJsonCard("Field Resolvers", explanation.field_resolvers));
  cards.push(renderJsonCard("Confidence Breakdown", explanation.confidence_evidence));
  cards.push(renderJsonCard("Raw Explanation", explanation));
  if (explanation.warnings && explanation.warnings.length) {
    cards.push(renderListCard("Warnings", explanation.warnings));
  }
  cards.push(`
    <section class="report-card">
      <h3>Overall Confidence</h3>
      <p>${escapeHtml(formatPercent(candidate.overall_confidence))}</p>
    </section>
  `);
  return `<div class="report-shell">${summary}<div class="report-grid">${cards.filter(Boolean).join("")}</div></div>`;
}

function renderCandidateCard(candidate) {
  const rows = [
    ["Name", candidate.name || candidate.full_name || "n/a"],
    ["Primary Email", candidate.primary_email || "n/a"],
    ["Primary Phone", candidate.primary_phone || "n/a"],
    ["Experience", candidate.experience ?? candidate.years_experience ?? "n/a"],
    ["Location", candidate.location ? `${candidate.location.city || ""}${candidate.location.country ? ", " + candidate.location.country : ""}`.replace(/^,\s*/, "") : "n/a"],
    ["Skills", Array.isArray(candidate.all_skills) ? candidate.all_skills.join(", ") : (candidate.skills || "n/a")],
    ["Confidence", formatPercent(candidate.overall_confidence)],
  ];
  return `
    <section class="report-card">
      <h4>Candidate Data</h4>
      <div class="report-kv">
        ${rows.map(([key, value]) => `
          <div class="report-kv-item">
            <div class="report-key">${escapeHtml(key)}</div>
            <div class="report-value">${escapeHtml(renderValue(value))}</div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderListCard(title, values) {
  const items = Array.isArray(values) ? values.filter((item) => item !== null && item !== undefined && item !== "") : [];
  if (!items.length) {
    return "";
  }
  return `
    <section class="report-card">
      <h4>${escapeHtml(title)}</h4>
      <ul class="report-list">
        ${items.map((item) => `<li>${escapeHtml(renderSummary(item))}</li>`).join("")}
      </ul>
    </section>
  `;
}

function renderMatchCard(title, values) {
  const items = Array.isArray(values) ? values.filter(Boolean) : [];
  if (!items.length) {
    return "";
  }
  return `
    <section class="report-card">
      <h4>${escapeHtml(title)}</h4>
      <ul class="report-list">
        ${items.map((item) => `<li>${escapeHtml(renderMatchItem(item))}</li>`).join("")}
      </ul>
    </section>
  `;
}

function renderFieldCard(title, fields) {
  const entries = fields && typeof fields === "object" ? Object.entries(fields) : [];
  if (!entries.length) {
    return "";
  }
  return `
    <section class="report-card">
      <h4>${escapeHtml(title)}</h4>
      <div class="report-kv">
        ${entries.map(([fieldName, detail]) => `
          <div class="report-kv-item">
            <div class="report-key">${escapeHtml(titleCase(fieldName))}</div>
            <div class="report-value">${renderDetailHtml(detail)}</div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function renderJsonCard(title, value) {
  if (!value || (typeof value === "object" && !Array.isArray(value) && !Object.keys(value).length)) {
    return "";
  }
  return `
    <section class="report-card">
      <h4>${escapeHtml(title)}</h4>
      <pre class="report-json">${escapeHtml(JSON.stringify(value, null, 2))}</pre>
    </section>
  `;
}

function renderDetailHtml(detail) {
  if (detail === null || detail === undefined || detail === "") {
    return `<span class="report-muted">n/a</span>`;
  }
  if (Array.isArray(detail)) {
    return `<ul class="report-list">${detail.map((item) => `<li>${escapeHtml(renderSummary(item))}</li>`).join("")}</ul>`;
  }
  if (typeof detail !== "object") {
    return escapeHtml(renderValue(detail));
  }
  const parts = [];
  const value = detail.selected_value !== undefined ? detail.selected_value : detail.value;
  if (value !== undefined) {
    parts.push(`<div><strong>Value:</strong> ${escapeHtml(renderValue(value))}</div>`);
  }
  const source = detail.selected_source || detail.source;
  if (source) {
    parts.push(`<div><strong>Source:</strong> ${escapeHtml(renderValue(source))}</div>`);
  }
  const confidence = detail.selected_confidence ?? detail.confidence;
  if (typeof confidence === "number") {
    parts.push(`<div><strong>Confidence:</strong> ${escapeHtml(formatPercent(confidence))}</div>`);
  }
  const reason = detail.selected_reason || detail.reason;
  if (reason) {
    parts.push(`<div><strong>Reason:</strong> ${escapeHtml(renderValue(reason))}</div>`);
  }
  if (Array.isArray(detail.sources) && detail.sources.length) {
    parts.push(`<div><strong>Sources:</strong> ${escapeHtml(detail.sources.join(", "))}</div>`);
  }
  if (Array.isArray(detail.items) && detail.items.length) {
    parts.push(`<div><strong>Evidence:</strong></div><ul class="report-list">${detail.items.slice(0, 5).map((item) => `<li>${escapeHtml(renderSummary(item))}</li>`).join("")}${detail.items.length > 5 ? `<li>+ ${detail.items.length - 5} more</li>` : ""}</ul>`);
  }
  if (Array.isArray(detail.values) && detail.values.length) {
    parts.push(`<div><strong>Values:</strong></div><ul class="report-list">${detail.values.slice(0, 5).map((item) => `<li>${escapeHtml(renderSummary(item))}</li>`).join("")}${detail.values.length > 5 ? `<li>+ ${detail.values.length - 5} more</li>` : ""}</ul>`);
  }
  return parts.length ? parts.join("") : escapeHtml(JSON.stringify(detail));
}

function toSummaryText(value) {
  if (Array.isArray(value)) {
    return value.map((item) => renderValue(item)).join(" + ") || "n/a";
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value || "");
}

function buildPublicPayload(report) {
  return (report?.candidates || []).map((candidate) => ({
    name: candidate.name ?? candidate.full_name ?? null,
    primary_email: candidate.primary_email ?? null,
    primary_phone: candidate.primary_phone ?? null,
    experience: candidate.experience ?? candidate.years_experience ?? null,
    location: candidate.location ?? { city: null, country: null },
    all_skills: candidate.all_skills ?? candidate.skills ?? [],
    overall_confidence: candidate.overall_confidence ?? 0,
    provenance: candidate.provenance ?? [],
  }));
}

function resetUploadState() {
  state.report = null;
  state.publicPayload = null;
  state.currentCandidateId = null;
  state.files = [];
  state.uploadKind = "folder";
  folderInput.value = "";
  zipInput.value = "";
  fileLabel.textContent = "No input selected";
  selectedFiles.classList.add("hidden");
  selectedFiles.innerHTML = "";
  jsonViewer.innerHTML = "[]";
  downloadJsonBtn.disabled = true;
  downloadCsvBtn.disabled = true;
  explainBtn.disabled = true;
  closeModal();
}
