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

const ICONS = {
  bot: `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="icon icon-bot">
      <path d="M12 8V4H8"></path>
      <rect width="16" height="12" x="4" y="8" rx="2"></rect>
      <path d="M2 14h2"></path>
      <path d="M20 14h2"></path>
      <path d="M15 13v2"></path>
      <path d="M9 13v2"></path>
    </svg>
  `,
  user: `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="icon icon-user">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path>
      <circle cx="12" cy="7" r="4"></circle>
    </svg>
  `,
  file: `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-file">
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path>
      <path d="M14 2v4a2 2 0 0 0 2 2h4"></path>
      <path d="M10 9H8"></path>
      <path d="M16 13H8"></path>
      <path d="M16 17H8"></path>
    </svg>
  `,
  external: `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-external">
      <path d="M15 3h6v6"></path>
      <path d="M10 14 21 3"></path>
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
    </svg>
  `,
  copy: `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-copy">
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect>
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>
    </svg>
  `,
  up: `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-thumb">
      <path d="M7 10v12"></path>
      <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"></path>
    </svg>
  `,
  down: `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-thumb">
      <path d="M17 14V2"></path>
      <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"></path>
    </svg>
  `,
  check: `
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" class="icon icon-check">
      <path d="m4 10 4 4 8-8"></path>
    </svg>
  `,
  successTick: `
    <span class="success-tick" aria-hidden="true">
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="m4 10 4 4 8-8"></path>
      </svg>
    </span>
  `,
};

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function nl2br(text) {
  return escapeHtml(text).replace(/\n/g, "<br>");
}

function normalizeWhitespace(text) {
  return String(text || "")
    .replace(/\r\n/g, "\n")
    .replace(/\t/g, " ")
    .replace(/[ ]{2,}/g, " ");
}

function isBulletLine(line) {
  return /^[•●◦▪▫■□◆◇\-–—]\s+/.test(line);
}

function isNumberedLine(line) {
  return /^(\(?\d{1,3}[.)]|[a-zA-Z][.)]|\(?[ivxlcdmIVXLCDM]{1,6}[.)])\s+/.test(line);
}

function isListLine(line) {
  return isBulletLine(line) || isNumberedLine(line);
}

function isHeadingLikeLine(line) {
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (isListLine(trimmed)) return false;
  if (trimmed.length > 90) return false;
  if (/^[A-Z][A-Za-z0-9 ,/&()'’-]{2,}:$/.test(trimmed)) return true;
  if (/^[A-Z][A-Z0-9 /&()'’-]{3,}$/.test(trimmed)) return true;
  return false;
}

function cleanInlineText(text) {
  return text
    .replace(/[ ]{2,}/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();
}

function joinWrappedParagraphLines(lines) {
  return cleanInlineText(lines.join(" "));
}

function formatBlock(block) {
  const rawLines = block
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (!rawLines.length) return "";

  const output = [];
  let currentTextLines = [];
  let currentListItem = null;

  const flushText = () => {
    if (currentTextLines.length) {
      output.push(joinWrappedParagraphLines(currentTextLines));
      currentTextLines = [];
    }
  };

  const flushListItem = () => {
    if (currentListItem) {
      output.push(cleanInlineText(currentListItem));
      currentListItem = null;
    }
  };

  for (const line of rawLines) {
    if (isHeadingLikeLine(line)) {
      flushText();
      flushListItem();
      output.push(line);
      continue;
    }

    if (isListLine(line)) {
      flushText();
      flushListItem();
      currentListItem = line;
      continue;
    }

    if (currentListItem) {
      currentListItem += " " + line;
      continue;
    }

    currentTextLines.push(line);
  }

  flushText();
  flushListItem();

  return output.join("\n");
}

function formatAnswerText(text) {
  if (!text) return "";

  text = normalizeWhitespace(text);

  const blocks = text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);

  const formattedBlocks = blocks
    .map((block) => formatBlock(block))
    .filter(Boolean);

  return formattedBlocks.join("\n\n");
}

function autoResize() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 150)}px`;
  toggleSendState();
}

function toggleSendState() {
  const hasText = questionInput.value.trim().length > 0;
  askBtn.classList.toggle("active", hasText);
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
  requestAnimationFrame(() => {
    chatBody.scrollTop = chatBody.scrollHeight;
  });
}

function addUserMessage(text) {
  showChatState();

  const row = document.createElement("div");
  row.className = "message-row user";
  row.innerHTML = `
    <div class="message-stack">
      <div class="message-main">
        <div class="avatar user">${ICONS.user}</div>
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
        <div class="avatar bot">${ICONS.bot}</div>
        <div class="message-bubble typing">
          Thinking
          <span class="loading-dots" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </span>
        </div>
      </div>
      <div class="message-time">${formatTime()}</div>
    </div>
  `;

  chatMessages.appendChild(row);
  scrollToBottom();
  return row;
}

function buildSources(citations = [], answerText = "") {
  const refusal = "the answer is not available in the approved document set.";
  const isRefusal = (answerText || "").trim().toLowerCase() === refusal;

  if (isRefusal || !citations.length) return "";

  return `
    <div class="sources-block">
      ${citations.map((c) => {
    const page = c.page_start || c.page_no || 1;
    const label = c.page_label || ("Page " + page);
    return `
          <a class="source-card" href="${buildSourceUrl(c)}" target="_blank" rel="noopener noreferrer">
            <div class="source-icon">${ICONS.file}</div>
            <div class="source-meta">
              <div class="source-file">${escapeHtml(c.doc_name)}</div>
              <div class="source-page">${escapeHtml(label)}</div>
            </div>
            <div class="source-open">${ICONS.external}</div>
          </a>
        `;
  }).join("")}
    </div>
  `;
}

function markFeedbackSaved(btn, content, text = "Feedback saved") {
  btn.classList.add("feedback-active", "feedback-animate");

  const actions = content.querySelector(".message-actions");
  if (actions) {
    let note = content.querySelector(".feedback-saved-note");
    if (!note) {
      note = document.createElement("div");
      note.className = "feedback-saved-note";
      actions.insertAdjacentElement("afterend", note);
    }

    note.innerHTML = `
      ${ICONS.successTick}
      <span>${escapeHtml(text)}</span>
    `;
    note.classList.remove("show");
    void note.offsetWidth;
    note.classList.add("show");
  }

  setTimeout(() => btn.classList.remove("feedback-animate"), 700);
}

function markCopySaved(btn) {
  btn.classList.add("copied");
  setTimeout(() => btn.classList.remove("copied"), 900);
}

function showInlineSaved(btn, text = "Saved") {
  let badge = btn.querySelector(".inline-saved");
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "inline-saved";
    btn.appendChild(badge);
  }

  badge.innerHTML = `${ICONS.successTick}<span>${escapeHtml(text)}</span>`;
  badge.classList.remove("show");
  void badge.offsetWidth;
  badge.classList.add("show");
}

function showCategorySaved(chip) {
  const label = chip.dataset.label || chip.textContent.trim();
  const row = chip.closest(".category-picker");

  chip.classList.add("selected", "saved-success");
  chip.innerHTML = `
    <span class="category-chip-label">${escapeHtml(label)}</span>
    <span class="category-chip-check">${ICONS.successTick}</span>
  `;

  if (row) {
    let note = row.querySelector(".category-saved-note");
    if (!note) {
      note = document.createElement("div");
      note.className = "category-saved-note";
      row.appendChild(note);
    }

    note.innerHTML = `
      ${ICONS.successTick}
      <span>Saved successfully</span>
    `;
    note.classList.remove("show");
    void note.offsetWidth;
    note.classList.add("show");
  }
}

function pulseContainer(el) {
  el.classList.add("saved-pulse");
  setTimeout(() => el.classList.remove("saved-pulse"), 800);
}

async function sendFeedback(satisfied, payload) {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

async function sendUnresolvedCategory(unresolvedQueryId, category) {
  try {
    const res = await fetch("/api/unresolved-category", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
            data-label="${escapeHtml(opt.label)}"
            data-unresolved-id="${unresolvedQueryId}"
          >
            <span class="category-chip-label">${opt.label}</span>
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
      } catch (_) { }
    });
  }

  if (likeBtn) {
    likeBtn.addEventListener("click", async () => {
      const ok = await sendFeedback(true, payload);
      if (!ok) return;

      likeBtn.classList.add("feedback-selected", "thumb-up-selected");
      dislikeBtn.disabled = true;
      markFeedbackSaved(likeBtn, content, "Feedback saved");
      pulseContainer(content);
    });
  }

  if (dislikeBtn) {
    dislikeBtn.addEventListener("click", async () => {
      const ok = await sendFeedback(false, payload);
      if (!ok) return;

      dislikeBtn.classList.add("feedback-selected", "thumb-down-selected");
      likeBtn.disabled = true;
      markFeedbackSaved(dislikeBtn, content, "Feedback saved");
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
        btn.classList.remove("selected", "saved-success");
      });

      showCategorySaved(chip);
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
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question: clean }),
    });

    const data = await response.json();
    loadingRow.remove();

    if (!response.ok) {
      addBotAnswerMessage({
        answer: data.error || "Something went wrong.",
        grounded: false,
        citations: [],
        debug: {},
      }, clean);
      return;
    }

    addBotAnswerMessage(data, clean);
  } catch (error) {
    loadingRow.remove();
    addBotAnswerMessage({
      answer: "Something went wrong while reaching the local assistant.",
      grounded: false,
      citations: [],
      debug: {},
    }, clean);
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