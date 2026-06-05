// Frontend vanilla para "Chatea con tus PDFs".
// Maneja: subida de PDFs (drag & drop), lista de documentos y chat con
// streaming SSE mostrando las citas debajo de cada respuesta.

const API = ""; // mismo origen (FastAPI sirve este frontend)

const el = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  uploadStatus: document.getElementById("upload-status"),
  docList: document.getElementById("doc-list"),
  refreshDocs: document.getElementById("refresh-docs"),
  docFilter: document.getElementById("doc-filter"),
  messages: document.getElementById("messages"),
  form: document.getElementById("chat-form"),
  question: document.getElementById("question"),
  sendBtn: document.getElementById("send-btn"),
};

// --------------------------------------------------------------------------
// Utilidades
// --------------------------------------------------------------------------
const escapeHtml = (s) =>
  s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);

// Resalta referencias tipo [1], [2] en el texto de la respuesta.
const highlightCitations = (text) =>
  escapeHtml(text).replace(/\[(\d+)\]/g, '<span class="cite-ref">[$1]</span>');

const scrollToBottom = () => {
  el.messages.scrollTop = el.messages.scrollHeight;
};

const setUploadStatus = (msg, kind = "") => {
  el.uploadStatus.hidden = false;
  el.uploadStatus.className = "upload-status" + (kind ? " " + kind : "");
  el.uploadStatus.textContent = msg;
};

// --------------------------------------------------------------------------
// Documentos
// --------------------------------------------------------------------------
async function loadDocuments() {
  try {
    const res = await fetch(`${API}/documents`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const docs = await res.json();
    renderDocuments(docs);
  } catch (err) {
    el.docList.innerHTML = `<li class="doc-empty">No se pudieron cargar los documentos.</li>`;
  }
}

function renderDocuments(docs) {
  // Lista lateral
  if (!docs.length) {
    el.docList.innerHTML = `<li class="doc-empty">Aún no has subido documentos.</li>`;
  } else {
    el.docList.innerHTML = docs
      .map(
        (d) => `
      <li class="doc-item" data-id="${d.document_id}">
        <span>📄</span>
        <div class="doc-info">
          <div class="doc-name" title="${escapeHtml(d.filename)}">${escapeHtml(
          d.filename
        )}</div>
          <div class="doc-meta">${d.pages} pág · ${d.chunks} chunks</div>
        </div>
        <button class="doc-delete" title="Borrar" data-id="${
          d.document_id
        }">🗑️</button>
      </li>`
      )
      .join("");
  }

  // Selector de filtro del chat
  const current = el.docFilter.value;
  el.docFilter.innerHTML =
    `<option value="">Todos los documentos</option>` +
    docs
      .map(
        (d) =>
          `<option value="${d.document_id}">${escapeHtml(d.filename)}</option>`
      )
      .join("");
  if ([...el.docFilter.options].some((o) => o.value === current)) {
    el.docFilter.value = current;
  }

  el.docList.querySelectorAll(".doc-delete").forEach((btn) => {
    btn.addEventListener("click", () => deleteDocument(btn.dataset.id));
  });
}

async function deleteDocument(id) {
  if (!confirm("¿Borrar este documento y sus vectores?")) return;
  try {
    const res = await fetch(`${API}/documents/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await loadDocuments();
  } catch (err) {
    alert("No se pudo borrar el documento.");
  }
}

// --------------------------------------------------------------------------
// Subida de PDFs
// --------------------------------------------------------------------------
async function uploadFiles(fileList) {
  const files = [...fileList].filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
  if (!files.length) {
    setUploadStatus("Selecciona archivos PDF.", "error");
    return;
  }

  const form = new FormData();
  files.forEach((f) => form.append("files", f));

  setUploadStatus(`Procesando ${files.length} archivo(s)…`);
  try {
    const res = await fetch(`${API}/documents`, { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      setUploadStatus(data.detail || "Error al subir.", "error");
      return;
    }
    const total = data.documents.reduce((a, d) => a + d.chunks, 0);
    setUploadStatus(
      `✓ ${data.documents.length} documento(s) indexado(s) (${total} chunks).`,
      "success"
    );
    await loadDocuments();
  } catch (err) {
    setUploadStatus("Error de red al subir los archivos.", "error");
  }
}

el.fileInput.addEventListener("change", (e) => uploadFiles(e.target.files));
el.refreshDocs.addEventListener("click", loadDocuments);

["dragenter", "dragover"].forEach((evt) =>
  el.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    el.dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  el.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    el.dropzone.classList.remove("dragover");
  })
);
el.dropzone.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));

// --------------------------------------------------------------------------
// Chat con streaming SSE
// --------------------------------------------------------------------------
function addUserMessage(text) {
  document.querySelector(".welcome")?.remove();
  const node = document.createElement("div");
  node.className = "msg user";
  node.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  el.messages.appendChild(node);
  scrollToBottom();
}

// Crea el contenedor de respuesta del asistente y devuelve helpers.
function addAssistantMessage() {
  const node = document.createElement("div");
  node.className = "msg assistant";
  node.innerHTML = `
    <div class="bubble"><span class="typing"><span></span><span></span><span></span></span></div>
    <div class="sources" hidden></div>`;
  el.messages.appendChild(node);
  scrollToBottom();

  const bubble = node.querySelector(".bubble");
  const sources = node.querySelector(".sources");
  let raw = "";
  let started = false;

  return {
    appendToken(token) {
      if (!started) {
        bubble.innerHTML = "";
        started = true;
      }
      raw += token;
      bubble.innerHTML = highlightCitations(raw);
      scrollToBottom();
    },
    renderSources(citations) {
      if (!citations || !citations.length) return;
      sources.hidden = false;
      sources.innerHTML =
        `<div class="sources-title">Fuentes</div>` +
        citations
          .map(
            (c, i) => `
        <div class="source">
          <div class="source-head">
            <span>[${i + 1}] ${escapeHtml(c.filename)} · pág. ${c.page}</span>
            <span class="source-score">${(c.score * 100).toFixed(0)}%</span>
          </div>
          <div class="source-snippet">${escapeHtml(c.snippet)}</div>
        </div>`
          )
          .join("");
      scrollToBottom();
    },
    finish() {
      if (!started) bubble.textContent = "(sin respuesta)";
    },
    error(msg) {
      bubble.classList.remove();
      bubble.textContent = "⚠️ " + msg;
    },
  };
}

async function ask(question) {
  addUserMessage(question);
  const ui = addAssistantMessage();

  let res;
  try {
    res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        document_id: el.docFilter.value || null,
        stream: true,
      }),
    });
  } catch (err) {
    ui.error("Error de red al contactar el servidor.");
    return;
  }

  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {}
    ui.error(detail);
    return;
  }

  // Lee el stream SSE manualmente (eventos: sources, token, done, error).
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop(); // resto incompleto
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      let payload;
      try {
        payload = JSON.parse(line.slice(5).trim());
      } catch (_) {
        continue;
      }
      if (payload.type === "sources") ui.renderSources(payload.citations);
      else if (payload.type === "token") ui.appendToken(payload.text);
      else if (payload.type === "error") ui.error(payload.detail);
      else if (payload.type === "done") ui.finish();
    }
  }
}

// Autoexpandir el textarea
el.question.addEventListener("input", () => {
  el.question.style.height = "auto";
  el.question.style.height = Math.min(el.question.scrollHeight, 180) + "px";
});

// Enter envía, Shift+Enter salto de línea
el.question.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    el.form.requestSubmit();
  }
});

el.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = el.question.value.trim();
  if (!question) return;
  el.question.value = "";
  el.question.style.height = "auto";
  el.sendBtn.disabled = true;
  try {
    await ask(question);
  } finally {
    el.sendBtn.disabled = false;
    el.question.focus();
  }
});

// Init
loadDocuments();
