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
    fileLabel.textContent = `✓ ZIP Loaded`;
    selectedFiles.innerHTML = `<strong>${escapeHtml(state.files[0].name)}</strong>`;
    return;
  }
  fileLabel.textContent = `✓ Folder Loaded`;
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
    setStatus("✓ Transformation Complete", "ready");
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
  const lines = [];
  lines.push("Merge Summary");
  lines.push("");
  lines.push("Candidate");
  lines.push(candidate.name || "Unknown");
  lines.push("");
  lines.push("Sources");
  (explanation.sources_merged || []).forEach((item) => lines.push(`✓ ${item}`));
  lines.push("");
  lines.push("Matching Criteria");
  (explanation.matched_on || []).forEach((item) => lines.push(`✓ ${item}`));
  lines.push("");
  lines.push("Fields");
  Object.entries(explanation.field_selection || {}).forEach(([fieldName, value]) => {
    lines.push(`${titleCase(fieldName)} ← ${renderValue(value)}`);
  });
  lines.push("");
  lines.push("Overall Confidence");
  lines.push(formatPercent(candidate.overall_confidence));
  if (explanation.warnings && explanation.warnings.length) {
    lines.push("");
    lines.push("Warnings");
    explanation.warnings.forEach((warning) => lines.push(warning));
  }
  explainViewer.textContent = lines.join("\n");
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
    return value.join(" + ") || "n/a";
  }
  if (value === null || value === undefined || value === "") {
    return "n/a";
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
