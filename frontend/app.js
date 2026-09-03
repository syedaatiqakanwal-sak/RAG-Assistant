const API_BASE = window.location.protocol === "file:" || window.location.port === "3000"
  ? "http://localhost:8001/api"
  : `${window.location.origin}/api`;

const WS_BASE = API_BASE.replace(/^http/, "ws");

const state = {
  token: localStorage.getItem("zeviq_admin_token") || "",
  sessions: loadSessions(),
  currentSessionId: localStorage.getItem("zeviq_current_session") || "",
  documents: [],
  uploadFiles: [],
  isStreaming: false,
};

const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", init);

function init() {
  if (!state.sessions.length) createSession(false);
  if (!state.currentSessionId || !state.sessions.find((s) => s.id === state.currentSessionId)) {
    state.currentSessionId = state.sessions[0].id;
  }

  bindNavigation();
  bindChat();
  bindAdmin();
  bindDocuments();
  bindModal();

  renderSessions();
  renderMessages();
  loadSuggestions();
  loadStatus();
  connectStatusSocket();
  loadPublicDocuments();
  updateAdminVisibility();
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) payload = await response.json();
  else payload = await response.text();

  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload;
}

function toast(message, type = "info") {
  const item = document.createElement("div");
  item.className = `toast ${type}`;
  item.textContent = message;
  $("toasts").appendChild(item);
  setTimeout(() => item.remove(), 4200);
}

function escapeHtml(value = "") {
  return value.replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function markdown(text = "") {
  let html = escapeHtml(text);
  html = html.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code.trim()}</code></pre>`);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.*)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.*)$/gm, "<h1>$1</h1>");
  html = html.replace(/^\s*[-*] (.*)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
  html = html.replace(/\n{2,}/g, "</p><p>");
  html = `<p>${html.replace(/\n/g, "<br>")}</p>`;
  return html.replace(/<p><\/p>/g, "");
}

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function fileIcon(name = "") {
  const ext = name.split(".").pop().toLowerCase();
  return { pdf: "PDF", docx: "DOC", txt: "TXT", csv: "CSV", md: "MD", markdown: "MD" }[ext] || "FILE";
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
function bindNavigation() {
  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
}

function showView(view) {
  document.querySelectorAll(".nav-tab").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".view").forEach((section) => section.classList.remove("active"));
  $(`${view}View`).classList.add("active");

  if (view === "documents") loadPublicDocuments();
  if (view === "admin" && state.token) {
    loadStats();
    loadAdminDocuments();
  }
}

// ---------------------------------------------------------------------------
// Chat sessions and rendering
// ---------------------------------------------------------------------------
function loadSessions() {
  try {
    return JSON.parse(localStorage.getItem("zeviq_sessions") || "[]");
  } catch {
    return [];
  }
}

function persistSessions() {
  localStorage.setItem("zeviq_sessions", JSON.stringify(state.sessions));
  localStorage.setItem("zeviq_current_session", state.currentSessionId);
}

function currentSession() {
  return state.sessions.find((s) => s.id === state.currentSessionId);
}

function createSession(render = true) {
  const session = {
    id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
    title: "New chat",
    createdAt: new Date().toISOString(),
    messages: [],
  };
  state.sessions.unshift(session);
  state.currentSessionId = session.id;
  persistSessions();
  if (render) {
    renderSessions();
    renderMessages();
  }
  return session;
}

function deleteSession(id) {
  state.sessions = state.sessions.filter((s) => s.id !== id);
  if (!state.sessions.length) createSession(false);
  if (state.currentSessionId === id) state.currentSessionId = state.sessions[0].id;
  persistSessions();
  renderSessions();
  renderMessages();
}

function renderSessions() {
  $("sessionList").innerHTML = state.sessions.map((session) => `
    <div class="session-item ${session.id === state.currentSessionId ? "active" : ""}" data-session="${session.id}">
      <div class="title">${escapeHtml(session.title)}</div>
      <button class="x" data-delete-session="${session.id}" aria-label="Delete session">x</button>
    </div>
  `).join("");

  document.querySelectorAll("[data-session]").forEach((item) => {
    item.addEventListener("click", (event) => {
      if (event.target.dataset.deleteSession) return;
      state.currentSessionId = item.dataset.session;
      persistSessions();
      renderSessions();
      renderMessages();
    });
  });
  document.querySelectorAll("[data-delete-session]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteSession(button.dataset.deleteSession);
    });
  });
}

function renderMessages() {
  const session = currentSession();
  const messages = session ? session.messages : [];
  $("welcome").style.display = messages.length ? "none" : "block";
  const existingWelcome = $("welcome").outerHTML;
  $("messages").innerHTML = existingWelcome + messages.map(renderMessage).join("");
  $("messages").scrollTop = $("messages").scrollHeight;

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const msg = messages[Number(button.dataset.copy)];
      await navigator.clipboard.writeText(msg.content || "");
      toast("Copied to clipboard", "ok");
    });
  });
}

function renderMessage(message, index) {
  const role = message.role === "user" ? "user" : "assistant";
  const avatar = role === "user" ? "You" : "AI";
  const isPending = role === "assistant" && message.pending && !message.content;
  const bubbleContent = isPending
    ? renderPending(message.status || "Searching documents and thinking")
    : role === "assistant" ? markdown(message.content) : escapeHtml(message.content);
  const sources = message.sources && message.sources.length
    ? `<details class="sources"><summary>${message.sources.length} source(s)</summary>${message.sources.map(renderSource).join("")}</details>`
    : "";
  const tools = role === "assistant" && !isPending
    ? `<div class="msg-tools"><button class="icon-btn" data-copy="${index}">Copy</button></div>`
    : "";
  return `
    <article class="msg ${role}">
      <div class="avatar" aria-hidden="true">${avatar}</div>
      <div>
        <div class="bubble">${bubbleContent}${sources}</div>
        ${tools}
      </div>
    </article>
  `;
}

function renderPending(label) {
  return `
    <div class="pending-answer" role="status" aria-live="polite">
      <span class="typing" aria-hidden="true"><span></span><span></span><span></span></span>
      <span>${escapeHtml(label)}...</span>
    </div>
  `;
}

function renderSource(source, i) {
  return `
    <div class="source">
      <div class="meta">
        <strong>${escapeHtml(source.filename || `Source ${i + 1}`)}</strong>
        <span class="tag">${escapeHtml(source.file_type || "")}</span>
        ${source.page !== null && source.page !== undefined ? `<span>Page ${source.page + 1}</span>` : ""}
      </div>
      <div class="text">${escapeHtml(source.preview || source.content || "")}</div>
    </div>
  `;
}

function bindChat() {
  $("newSessionBtn").addEventListener("click", () => createSession(true));
  $("clearChatBtn").addEventListener("click", () => {
    const session = currentSession();
    session.messages = [];
    persistSessions();
    renderMessages();
  });

  $("temperature").addEventListener("input", () => {
    $("temperatureValue").textContent = Number($("temperature").value).toFixed(2);
  });
  $("topK").addEventListener("input", () => {
    $("topKValue").textContent = $("topK").value;
  });

  $("questionInput").addEventListener("input", autoResize);
  $("questionInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("chatForm").requestSubmit();
    }
  });

  $("chatForm").addEventListener("submit", sendMessage);
  $("exportTxtBtn").addEventListener("click", exportText);
  $("exportPdfBtn").addEventListener("click", () => window.print());
}

function autoResize(event) {
  const el = event.target;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

async function sendMessage(event) {
  event.preventDefault();
  if (state.isStreaming) return;

  const input = $("questionInput");
  const question = input.value.trim();
  if (!question) return;

  const session = currentSession();
  if (session.title === "New chat") session.title = question.slice(0, 40);
  session.messages.push({ role: "user", content: question, createdAt: new Date().toISOString() });
  const assistantMessage = {
    role: "assistant",
    content: "",
    sources: [],
    pending: true,
    status: "Searching documents and thinking",
    createdAt: new Date().toISOString(),
  };
  session.messages.push(assistantMessage);
  input.value = "";
  input.style.height = "auto";
  persistSessions();
  renderSessions();
  renderMessages();

  state.isStreaming = true;
  $("sendBtn").disabled = true;
  const assistantIndex = session.messages.length - 1;

  try {
    await streamAnswer(question, assistantMessage, () => {
      persistSessions();
      updateAssistantMessage(assistantIndex, assistantMessage);
    });
  } catch (error) {
    assistantMessage.content = `Error: ${error.message}`;
    toast(error.message, "err");
  } finally {
    state.isStreaming = false;
    $("sendBtn").disabled = false;
    persistSessions();
    renderMessages();
  }
}

async function streamAnswer(question, assistantMessage, onToken) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      temperature: Number($("temperature").value),
      top_k: Number($("topK").value),
      stream: true,
    }),
  });
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Streaming request failed");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();
    for (const raw of events) handleSse(raw, assistantMessage, onToken);
  }
}

function handleSse(raw, assistantMessage, onToken) {
  const event = (raw.match(/^event:\s*(.+)$/m) || [])[1];
  const dataRaw = (raw.match(/^data:\s*(.+)$/m) || [])[1];
  if (!event || !dataRaw) return;
  const data = JSON.parse(dataRaw);
  if (event === "sources") {
    assistantMessage.sources = data;
    assistantMessage.status = data.length
      ? `Found ${data.length} relevant source${data.length === 1 ? "" : "s"}; generating answer`
      : "No matching sources found; generating response";
    onToken();
  }
  if (event === "token") {
    assistantMessage.pending = false;
    assistantMessage.content += data.token;
    onToken();
  }
  if (event === "error") throw new Error(data.detail || "Stream failed");
}

function updateAssistantMessage(index, message) {
  const items = currentSession().messages;
  items[index] = message;
  const html = currentSession().messages.map(renderMessage).join("");
  $("messages").innerHTML = $("welcome").outerHTML + html;
  $("welcome").style.display = "none";
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function loadSuggestions() {
  try {
    const payload = await api("/chat/suggestions");
    $("suggestions").innerHTML = payload.suggestions.map((q) => `<button class="chip">${escapeHtml(q)}</button>`).join("");
    document.querySelectorAll(".chip").forEach((button) => {
      button.addEventListener("click", () => {
        $("questionInput").value = button.textContent;
        $("questionInput").focus();
      });
    });
  } catch {
    $("suggestions").innerHTML = "";
  }
}

function exportText() {
  const session = currentSession();
  const text = session.messages.map((m) => `${m.role.toUpperCase()}: ${m.content}`).join("\n\n");
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${session.title.replace(/[^a-z0-9]+/gi, "_").toLowerCase() || "chat"}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------
function bindDocuments() {
  $("refreshPublicDocsBtn").addEventListener("click", loadPublicDocuments);
  $("publicDocSearch").addEventListener("input", () => loadPublicDocuments($("publicDocSearch").value));
}

async function loadPublicDocuments(search = "") {
  const target = $("publicDocumentList");
  target.innerHTML = skeletonRows(5);
  try {
    const qs = search ? `?search=${encodeURIComponent(search)}` : "";
    const payload = await api(`/documents${qs}`);
    state.documents = payload.documents;
    target.innerHTML = renderDocumentTable(payload.documents, { selectable: false });
    bindDocumentTable(target);
  } catch (error) {
    target.innerHTML = empty(`Could not load documents: ${escapeHtml(error.message)}`);
  }
}

async function loadAdminDocuments(search = "") {
  const target = $("adminDocumentList");
  target.innerHTML = skeletonRows(5);
  try {
    const qs = search ? `?search=${encodeURIComponent(search)}` : "";
    const payload = await api(`/documents${qs}`);
    state.documents = payload.documents;
    target.innerHTML = renderDocumentTable(payload.documents, { selectable: true });
    bindDocumentTable(target);
  } catch (error) {
    target.innerHTML = empty(`Could not load documents: ${escapeHtml(error.message)}`);
  }
}

function renderDocumentTable(docs, { selectable }) {
  if (!docs.length) return empty("No documents found.");
  return `
    <div class="card" style="overflow:auto;">
      <table class="docs">
        <thead>
          <tr>
            ${selectable ? "<th><input id=\"selectAllDocs\" type=\"checkbox\" aria-label=\"Select all documents\"></th>" : ""}
            <th>Name</th><th>Type</th><th>Category</th><th>Size</th><th>Modified</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${docs.map((doc) => `
            <tr>
              ${selectable ? `<td><input class="doc-check" type="checkbox" value="${doc.id}" aria-label="Select ${escapeHtml(doc.name)}"></td>` : ""}
              <td><strong>${fileIcon(doc.name)}</strong> ${escapeHtml(doc.name)}</td>
              <td><span class="badge">${escapeHtml(doc.file_type)}</span></td>
              <td>${escapeHtml(doc.category)}</td>
              <td>${escapeHtml(doc.size_human)}</td>
              <td>${formatDate(doc.modified)}</td>
              <td><button class="btn sm" data-preview="${doc.id}">Preview</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function bindDocumentTable(root) {
  root.querySelectorAll("[data-preview]").forEach((button) => {
    button.addEventListener("click", () => previewDocument(button.dataset.preview));
  });
  const selectAll = root.querySelector("#selectAllDocs");
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      root.querySelectorAll(".doc-check").forEach((check) => { check.checked = selectAll.checked; });
    });
  }
}

async function previewDocument(id) {
  try {
    const payload = await api(`/documents/${encodeURIComponent(id)}/preview`);
    $("modalTitle").textContent = payload.name;
    $("modalBody").innerHTML = `<pre class="preview">${escapeHtml(payload.content || "No preview available.")}</pre>`;
    $("modalOverlay").classList.add("show");
  } catch (error) {
    toast(error.message, "err");
  }
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------
function bindAdmin() {
  $("loginForm").addEventListener("submit", login);
  $("logoutBtn").addEventListener("click", logout);
  $("refreshStatsBtn").addEventListener("click", loadStats);
  $("refreshActivityBtn").addEventListener("click", loadActivity);
  $("refreshAdminDocsBtn").addEventListener("click", () => loadAdminDocuments($("adminDocSearch").value));
  $("adminDocSearch").addEventListener("input", () => loadAdminDocuments($("adminDocSearch").value));
  $("reindexBtn").addEventListener("click", reindexAll);
  $("bulkDeleteBtn").addEventListener("click", bulkDelete);
  bindUpload();

  document.querySelectorAll(".admin-nav [data-panel]").forEach((button) => {
    button.addEventListener("click", () => showAdminPanel(button.dataset.panel));
  });
}

function updateAdminVisibility() {
  $("adminLogin").classList.toggle("hidden", Boolean(state.token));
  $("adminPanel").classList.toggle("hidden", !state.token);
  if (state.token) {
    loadStats();
    loadAdminDocuments();
    loadActivity();
  }
}

async function login(event) {
  event.preventDefault();
  try {
    const payload = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: $("username").value, password: $("password").value }),
    });
    state.token = payload.access_token;
    localStorage.setItem("zeviq_admin_token", state.token);
    toast("Logged in", "ok");
    updateAdminVisibility();
  } catch (error) {
    toast(error.message, "err");
  }
}

async function logout() {
  try { await api("/auth/logout", { method: "POST" }); } catch {}
  state.token = "";
  localStorage.removeItem("zeviq_admin_token");
  updateAdminVisibility();
  toast("Logged out", "info");
}

function showAdminPanel(panel) {
  document.querySelectorAll(".admin-nav [data-panel]").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === panel);
  });
  document.querySelectorAll(".panel").forEach((section) => section.classList.remove("active"));
  $(`${panel}Panel`).classList.add("active");
  if (panel === "dashboard") loadStats();
  if (panel === "manager") loadAdminDocuments();
  if (panel === "activity") loadActivity();
}

async function loadStats() {
  if (!state.token) return;
  try {
    const payload = await api("/stats");
    $("statDocs").textContent = payload.total_documents;
    $("statChunks").textContent = payload.total_chunks;
    $("statQuestions").textContent = payload.questions_asked;
    $("statOllama").textContent = payload.ollama_reachable ? "Online" : "Offline";
    $("categoryStats").innerHTML = Object.entries(payload.by_category || {}).map(([name, count]) => `
      <div style="display:flex; justify-content:space-between; padding:.45rem 0; border-bottom:1px solid var(--border);">
        <span>${escapeHtml(name)}</span><strong>${count}</strong>
      </div>
    `).join("") || "<p style='color: var(--muted);'>No documents uploaded yet.</p>";
  } catch (error) {
    toast(error.message, "err");
  }
}

async function loadActivity() {
  if (!state.token) return;
  try {
    const payload = await api("/activity?limit=80");
    $("activityList").innerHTML = payload.activity.length
      ? payload.activity.map(renderActivity).join("")
      : empty("No activity yet.");
  } catch (error) {
    $("activityList").innerHTML = empty(`Could not load activity: ${escapeHtml(error.message)}`);
  }
}

function renderActivity(item) {
  const icon = item.type === "question" ? "Q" : item.type === "upload" ? "UP" : item.type === "delete" ? "DEL" : "IDX";
  return `
    <div class="activity-item">
      <div class="ai">${icon}</div>
      <div class="ac">
        <div class="at">${escapeHtml(item.question || item.type)}</div>
        <div class="am">${escapeHtml(item.type)} - ${formatDate(item.timestamp)}${item.latency_ms ? ` - ${item.latency_ms}ms` : ""}</div>
      </div>
    </div>
  `;
}

async function reindexAll() {
  if (!confirm("Re-index all documents now?")) return;
  $("reindexBtn").disabled = true;
  $("reindexBtn").innerHTML = `<span class="spin"></span> Indexing`;
  try {
    const payload = await api("/documents/reindex", { method: "POST", body: "{}" });
    toast(payload.message, "ok");
    await Promise.all([loadStats(), loadAdminDocuments(), loadSuggestions(), loadPublicDocuments()]);
  } catch (error) {
    toast(error.message, "err");
  } finally {
    $("reindexBtn").disabled = false;
    $("reindexBtn").textContent = "Re-index all";
  }
}

async function bulkDelete() {
  const ids = Array.from(document.querySelectorAll("#adminDocumentList .doc-check:checked")).map((el) => el.value);
  if (!ids.length) return toast("Select documents to delete first", "info");
  if (!confirm(`Delete ${ids.length} selected document(s)?`)) return;
  try {
    const payload = await api("/documents/delete", { method: "POST", body: JSON.stringify({ ids }) });
    toast(payload.message, payload.success ? "ok" : "err");
    await Promise.all([loadStats(), loadAdminDocuments(), loadPublicDocuments(), loadSuggestions()]);
  } catch (error) {
    toast(error.message, "err");
  }
}

function bindUpload() {
  const dz = $("dropzone");
  const input = $("fileInput");
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") input.click();
  });
  input.addEventListener("change", () => addUploadFiles(input.files));
  ["dragenter", "dragover"].forEach((name) => dz.addEventListener(name, (event) => {
    event.preventDefault();
    dz.classList.add("hover");
  }));
  ["dragleave", "drop"].forEach((name) => dz.addEventListener(name, (event) => {
    event.preventDefault();
    dz.classList.remove("hover");
  }));
  dz.addEventListener("drop", (event) => addUploadFiles(event.dataTransfer.files));
  $("clearQueueBtn").addEventListener("click", () => {
    state.uploadFiles = [];
    renderFileQueue();
  });
  $("uploadBtn").addEventListener("click", uploadQueuedFiles);
}

function addUploadFiles(files) {
  state.uploadFiles.push(...Array.from(files));
  renderFileQueue();
}

function renderFileQueue(status = {}) {
  $("fileQueue").innerHTML = state.uploadFiles.map((file, index) => `
    <div class="queue-item">
      <div class="fi">${fileIcon(file.name)}</div>
      <div class="info">
        <div class="nm">${escapeHtml(file.name)}</div>
        <div class="sz">${(file.size / 1024 / 1024).toFixed(2)} MB</div>
      </div>
      <div class="st ${status[index]?.type || "pending"}">${status[index]?.text || "Ready"}</div>
    </div>
  `).join("") || `<div class="empty"><div class="big">+</div><p>No files queued.</p></div>`;
}

async function uploadQueuedFiles() {
  if (!state.uploadFiles.length) return toast("Add files first", "info");
  $("uploadBtn").disabled = true;
  $("uploadProgress").classList.remove("hidden");
  $("uploadProgressBar").style.width = "35%";
  try {
    const form = new FormData();
    state.uploadFiles.forEach((file) => form.append("files", file));
    const payload = await api("/documents/upload?reindex=true", { method: "POST", body: form, headers: {} });
    const status = {};
    payload.results.forEach((result, index) => {
      status[index] = { type: result.success ? "ok" : "err", text: result.success ? "Uploaded" : result.detail };
    });
    renderFileQueue(status);
    $("uploadProgressBar").style.width = "100%";
    toast(payload.message, payload.success ? "ok" : "err");
    state.uploadFiles = [];
    await Promise.all([loadStats(), loadAdminDocuments(), loadPublicDocuments(), loadSuggestions()]);
  } catch (error) {
    toast(error.message, "err");
  } finally {
    $("uploadBtn").disabled = false;
    setTimeout(() => {
      $("uploadProgress").classList.add("hidden");
      $("uploadProgressBar").style.width = "0%";
    }, 900);
  }
}

// ---------------------------------------------------------------------------
// Status and modal
// ---------------------------------------------------------------------------
async function loadStatus() {
  try {
    const payload = await api("/status");
    updateStatus(payload.ollama && payload.ollama.reachable, payload);
  } catch {
    updateStatus(false);
  }
}

function connectStatusSocket() {
  try {
    const ws = new WebSocket(`${WS_BASE}/ws/status`);
    ws.onmessage = () => {};
    ws.onclose = () => setTimeout(connectStatusSocket, 5000);
  } catch {
    setTimeout(connectStatusSocket, 5000);
  }
}

function updateStatus(ok, payload = {}) {
  $("statusDot").className = `dot ${ok ? "ok" : "bad"}`;
  $("statusText").textContent = ok ? "Ollama online" : "Ollama offline";
  $("statusPill").title = payload.total_documents !== undefined
    ? `${payload.total_documents} docs, ${payload.total_chunks} chunks`
    : "Status unavailable";
}

function bindModal() {
  $("closeModalBtn").addEventListener("click", closeModal);
  $("modalOverlay").addEventListener("click", (event) => {
    if (event.target.id === "modalOverlay") closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
}

function closeModal() {
  $("modalOverlay").classList.remove("show");
}

function skeletonRows(count) {
  return `<div class="card" style="padding:1rem;">${Array.from({ length: count }, () => `<div class="skeleton sk-row"></div>`).join("")}</div>`;
}

function empty(message) {
  return `<div class="empty"><div class="big">-</div><p>${message}</p></div>`;
}
