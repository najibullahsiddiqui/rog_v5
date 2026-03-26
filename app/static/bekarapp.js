const askForm = document.getElementById("askForm");
const questionInput = document.getElementById("questionInput");
const askBtn = document.getElementById("askBtn");
const welcomeState = document.getElementById("welcomeState");
const chatState = document.getElementById("chatState");
const chatMessages = document.getElementById("chatMessages");
const chatBody = document.getElementById("chatBody");
const suggestCards = document.querySelectorAll(".suggest-card");

const CATEGORY_OPTIONS = [
  { value: "patent", label: "Patent" },
  { value: "trademark", label: "Trademark" },
  { value: "copyright", label: "Copyright" },
  { value: "design", label: "Design" },
  { value: "gi", label: "GI" },
  { value: "sicld", label: "SICLD" },
];

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function nl2br(text) {
  return escapeHtml(text).replace(/\n/g, "<br>");
}

function autoResize() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 150)}px`;
  toggleSendState();
}

function toggleSendState() {
  askBtn.classList.toggle("active", questionInput.value.trim().length > 0);
}

function formatTime() {
  return new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function buildSourceUrl(citation) {
  const fileName = encodeURIComponent(citation.doc_name);
  const page = citation.page_start || citation.page_no || 1;
  return `/pdf/${fileName}#page=${page}`;
}

function showChatState() {
  welcomeState.classList.add("hidden");
  chatState.classList.remove("hidden");
}

function scrollToBottom() {
  chatBody.scrollTop = chatBody.scrollHeight;
}

function addUserMessage(text) {
  showChatState();

  const row = document.createElement("div");
  row.className = "message-row user";
  row.innerHTML = `
    <div class="message-stack">
      <div class="message-main">
        <div class="avatar user">👤</div>
        <div class="message-bubble">${nl2br(text)}</div>
      </div>
      <div class="message-time">${formatTime()}</div>
    </div>
  `;

  chatMessages.appendChild(row);
  scrollToBottom();
}

function addBotLoadingMessage() {
  showChatState();

  const row = document.createElement("div");
  row.className = "message-row bot";
  row.innerHTML = `
    <div class="message-stack">
      <div class="message-main">
        <div class="avatar bot">🤖</div>
        <div class="message-bubble typing">
          Reviewing the approved documents<span class="loading-dots"></span>
        </div>
      </div>
      <div class="message-time">${formatTime()}</div>
    </div>
  `;

  chatMessages.appendChild(row);
  scrollToBottom();
  return row;
}

function buildSources(citations = [], grounded = true, answerText = "") {
  const refusal = "the answer is not available in the approved document set.";
  const isRefusal = (answerText || "").trim().toLowerCase() === refusal;

  if (!grounded || isRefusal || !citations.length) return "";

  return `
    <div class="sources-block">
      ${citations.map(c => `
        <a class="source-card" href="${buildSourceUrl(c)}" target="_blank" rel="noopener noreferrer">
          <div class="source-icon">📄</div>
          <div class="source-meta">
            <div class="source-file">${escapeHtml(c.doc_name)}</div>
            <div class="source-page">${escapeHtml(c.page_label || ("Page " + c.page_no))}</div>
          </div>
          <div class="source-open">↗</div>
        </a>
      `).join("")}
    </div>
  `;
}

function markButtonSaved(btn, label = "Saved") {
  btn.classList.add("is-saved");
  const original = btn.dataset.originalText || btn.textContent;
  btn.dataset.originalText = original;
  btn.textContent = label;

  setTimeout(() => {
    btn.textContent = original;
  }, 1200);
}

function pulseRow(row) {
  row.classList.add("saved-pulse");
  setTimeout(() => {
    row.classList.remove("saved-pulse");
  }, 900);
}

async function sendFeedback(satisfied, payload) {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        question: payload.question,
        normalized_question: payload.normalized_question || null,
        category: payload.category || null,
        answer_text: payload.answer || "",
        satisfied,
        comment: null,
        citations: payload.citations || [],
      }),
    });
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function sendWrongAnswerReport(payload, note = null) {
  try {
    const res = await fetch("/api/feedback/wrong-answer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_id: payload.session_id || null,
        message_id: payload.message_id || null,
        question: payload.question,
        normalized_question: payload.normalized_question || null,
        category: payload.category || null,
        answer_text: payload.answer || "",
        citations: payload.citations || [],
        note: note || null,
        reason_code: "incorrect_answer",
        severity: "medium",
      }),
    });
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function sendUnresolvedCategory(unresolvedQueryId, category) {
  try {
    const res = await fetch("/api/unresolved-category", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        unresolved_query_id: unresolvedQueryId,
        user_selected_category: category,
      }),
    });
    return res.ok;
  } catch (_) {
    return false;
  }
}

function buildCategoryPicker(unresolvedQueryId, suggestedCategory = null) {
  if (!unresolvedQueryId) return "";

  return `
    <div class="category-picker">
      <div class="category-picker-title">
        We couldn’t find a supported answer in the approved documents. Please select the category that best matches your question to help us improve the system.
      </div>
      <div class="category-chip-row">
        ${CATEGORY_OPTIONS.map((opt) => `
          <button
            type="button"
            class="category-chip ${suggestedCategory === opt.value ? "suggested" : ""}"
            data-category="${opt.value}"
            data-unresolved-id="${unresolvedQueryId}"
          >
            ${opt.label}
            ${suggestedCategory === opt.value ? '<span class="category-chip-hint">Suggested</span>' : ""}
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function addBotAnswerMessage(data, originalQuestion) {
  const formattedAnswer = formatAnswerText(data.answer || "");
  const refusal = "the answer is not available in the approved document set.";
  const isRefusal = formattedAnswer.trim().toLowerCase() === refusal;

  const unresolvedQueryId = data.unresolved_query_id || null;
  const suggestedCategory =
    data.predicted_category ||
    data.debug?.query_info?.entity ||
    null;

  const needsCategorySelection = isRefusal && !!unresolvedQueryId;

  const row = document.createElement("div");
  row.className = "message-row bot";
  row.innerHTML = `
    <div class="message-stack">
      <div class="message-main">
        <div class="avatar bot">${ICONS.bot}</div>
        <div class="message-content">
          <div class="message-bubble">
            ${nl2br(formattedAnswer)}
          </div>

          <div class="message-time message-time-inline">${formatTime()}</div>

          <div class="message-actions">
            <button type="button" class="copy-btn" title="Copy">${ICONS.copy}</button>
            <button type="button" class="like-btn" title="Satisfied">${ICONS.up}</button>
            <button type="button" class="dislike-btn" title="Not satisfied">${ICONS.down}</button>
          </div>

          ${buildSources(data.citations || [], formattedAnswer)}
          ${needsCategorySelection ? buildCategoryPicker(unresolvedQueryId, suggestedCategory) : ""}
        </div>
      </div>
    </div>
  `;

  const payload = {
    session_id: data.session_id || data.debug?.session_id || null,
    message_id: data.message_id || data.debug?.message_id || null,
    question: originalQuestion,
    normalized_question: data.debug?.query_info?.normalized_question || null,
    category: data.category || suggestedCategory || null,
    answer: formattedAnswer,
    citations: data.citations || [],
  };

  const copyBtn = row.querySelector(".copy-btn");
  const likeBtn = row.querySelector(".like-btn");
  const dislikeBtn = row.querySelector(".dislike-btn");
  const content = row.querySelector(".message-content");

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(formattedAnswer);
        markCopySaved(copyBtn);
        pulseContainer(content);
      } catch (_) {}
    });
  }

  if (likeBtn) {
    likeBtn.addEventListener("click", async () => {
      const ok = await sendFeedback(true, payload);
      if (!ok) return;

      likeBtn.classList.add("feedback-selected", "thumb-up-selected");
      dislikeBtn.disabled = true;
      markButtonSaved(likeBtn, "Saved");
      pulseContainer(content);
    });
  }

  if (dislikeBtn) {
    dislikeBtn.addEventListener("click", async () => {
      const note = window.prompt("Optional note for wrong answer report:", "") || "";
      const ok = await sendFeedback(false, payload);
      const reportOk = await sendWrongAnswerReport(payload, note.trim() || null);
      if (!ok && !reportOk) return;

      dislikeBtn.classList.add("feedback-selected", "thumb-down-selected");
      likeBtn.disabled = true;
      markButtonSaved(dislikeBtn, reportOk ? "Reported" : "Saved");
      pulseContainer(content);
    });
  }

  row.querySelectorAll(".category-chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      const category = chip.dataset.category;
      const id = Number(chip.dataset.unresolvedId || 0);

      const ok = await sendUnresolvedCategory(id, category);
      if (!ok) return;

      row.querySelectorAll(".category-chip").forEach((btn) => {
        btn.disabled = true;
        btn.classList.remove("selected");
      });

      chip.classList.add("selected");
      chip.innerHTML = `${escapeHtml(chip.textContent.trim())} ${ICONS.check}`;
      pulseContainer(content);
    });
  });

  chatMessages.appendChild(row);
  scrollToBottom();
}
async function askQuestion(question) {
  const clean = question.trim();
  if (!clean) return;

  addUserMessage(clean);
  questionInput.value = "";
  autoResize();
  askBtn.disabled = true;

  const loadingRow = addBotLoadingMessage();

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ question: clean }),
    });

    const data = await response.json();
    loadingRow.remove();

    if (!response.ok) {
      addBotAnswerMessage(
        {
          answer: data.error || "Something went wrong.",
          grounded: false,
          citations: [],
          debug: {},
        },
        clean
      );
      return;
    }

    addBotAnswerMessage(data, clean);
  } catch (error) {
    loadingRow.remove();
    addBotAnswerMessage(
      {
        answer: "Something went wrong while reaching the local assistant.",
        grounded: false,
        citations: [],
        debug: {},
      },
      clean
    );
  } finally {
    askBtn.disabled = false;
    questionInput.focus();
    toggleSendState();
  }
}

askForm.addEventListener("submit", (e) => {
  e.preventDefault();
  askQuestion(questionInput.value);
});

questionInput.addEventListener("input", autoResize);

questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    askQuestion(questionInput.value);
  }
});

suggestCards.forEach((card) => {
  card.addEventListener("click", () => {
    const q = card.dataset.q || "";
    questionInput.value = q;
    autoResize();
    askQuestion(q);
  });
});

autoResize();
toggleSendState();
