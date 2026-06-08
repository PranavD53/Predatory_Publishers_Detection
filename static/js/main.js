const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
const rootHtml = document.documentElement;
const storedTheme = localStorage.getItem("ppd-theme");
const themeToggle = document.getElementById("themeToggle");

function applyTheme(theme) {
  const next = theme === "light" ? "light" : "dark";
  rootHtml.setAttribute("data-theme", next);
  localStorage.setItem("ppd-theme", next);
  if (themeToggle) {
    const isDark = next === "dark";
    themeToggle.setAttribute("aria-pressed", isDark ? "true" : "false");
    themeToggle.classList.toggle("theme-toggle--dark", isDark);
    themeToggle.classList.toggle("theme-toggle--light", !isDark);
  }
}

if (storedTheme === "light" || storedTheme === "dark") {
  applyTheme(storedTheme);
} else {
  applyTheme(prefersDark ? "dark" : "light");
}

themeToggle?.addEventListener("click", () => {
  const current = rootHtml.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
});

const form = document.getElementById("analyzeForm");
const resultSection = document.getElementById("resultSection");
const resultUrlEl = document.getElementById("resultUrl");
const resultLabelEl = document.getElementById("resultLabel");
const riskScoreValueEl = document.getElementById("riskScoreValue");
const resultTitleEl = document.getElementById("resultTitle");
const resultDescriptionEl = document.getElementById("resultDescription");
const resultConfidenceEl = document.getElementById("resultConfidence");
const gaugeFillEl = document.getElementById("gaugeFill");

async function handleAnalyze(event) {
  event.preventDefault();
  const input = document.getElementById("journalUrl");
  const url = input.value.trim();
  if (!url) return;

  form.classList.add("is-loading");

  try {
    const response = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    let data;
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      data = await response.json();
    } else {
      const text = await response.text();
      // Render or standard web servers return HTML on 502/504/500 errors.
      // Strip HTML tags for a cleaner alert.
      const cleanText = text.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().substring(0, 200);
      throw new Error(`Server Error (${response.status} ${response.statusText}): ${cleanText || "No response body"}`);
    }

    if (!response.ok) {
      throw new Error(data.error || "Failed to analyze URL.");
    }

    renderResult(data);
  } catch (error) {
    alert(error.message || "Unexpected error. Please try again.");
  } finally {
    form.classList.remove("is-loading");
  }
}

function renderResult(data) {
  const riskPct = Math.round((data.risk_score || 0) * 100);
  const confPct = Math.round((data.confidence || 0) * 100);

  resultSection?.classList.remove("hidden");
  resultUrlEl.textContent = data.url || "";
  resultTitleEl.textContent = data.title || "No clear journal title detected.";
  resultDescriptionEl.textContent =
    data.description || "No meta description was available for this URL.";
  resultConfidenceEl.textContent = `Model confidence: ${confPct}%`;

  riskScoreValueEl.textContent = `${riskPct}%`;

  const deg = Math.min(330, Math.max(0, (riskPct / 100) * 330));
  if (gaugeFillEl) {
    gaugeFillEl.style.transform = `rotate(${deg}deg)`;
  }

  resultLabelEl.textContent = data.label || "Unknown";
  resultLabelEl.classList.remove("pill--danger", "pill--success");
  if ((data.label || "").toLowerCase().includes("predatory")) {
    resultLabelEl.classList.add("pill--danger");
  } else {
    resultLabelEl.classList.add("pill--success");
  }

  const directoryBadgeEl = document.getElementById("directoryBadge");
  if (directoryBadgeEl) {
    directoryBadgeEl.classList.add("hidden");
    directoryBadgeEl.classList.remove("pill--success", "pill--danger", "pill--info");
    
    if (data.directory_match) {
      directoryBadgeEl.classList.remove("hidden");
      if (data.directory_match.source === "doaj") {
        directoryBadgeEl.textContent = "Verified on DOAJ";
        directoryBadgeEl.classList.add("pill--info");
      } else if (data.directory_match.source === "bealls") {
        directoryBadgeEl.textContent = "Listed on Beall's List";
        directoryBadgeEl.classList.add("pill--danger");
      }
    }
  }

  const suspiciousWrapper = document.getElementById("suspiciousPhrasesWrapper");
  const suspiciousList = document.getElementById("suspiciousPhrasesList");
  if (suspiciousList) {
    suspiciousList.innerHTML = "";
    if (data.suspicious_phrases && data.suspicious_phrases.length > 0) {
      suspiciousWrapper?.classList.remove("hidden");
      data.suspicious_phrases.forEach((phrase) => {
        const span = document.createElement("span");
        span.className = "suspicious-phrase-tag";
        span.textContent = phrase;
        suspiciousList.appendChild(span);
      });
    } else {
      suspiciousWrapper?.classList.add("hidden");
    }
  }

  const recentList = document.getElementById("recentList");
  if (recentList) {
    const placeholder = document.getElementById("recentListPlaceholder");
    if (placeholder) {
      placeholder.remove();
    }
    
    const li = document.createElement("li");
    const riskPct = Math.round((data.risk_score || 0) * 100);
    const confPct = Math.round((data.confidence || 0) * 100);
    const isPredatory = (data.label || "").toLowerCase().includes("predatory");
    const labelClass = isPredatory ? "pill--danger" : "pill--success";
    
    li.innerHTML = `
      <div class="recent-url" title="${data.url || ""}">${data.url || ""}</div>
      <div class="recent-meta">
        <span class="pill pill--small ${labelClass}">
          ${data.label || "Unknown"}
        </span>
        <span class="recent-score">
          Risk: ${riskPct}% · Conf: ${confPct}%
        </span>
      </div>
    `;
    
    recentList.insertBefore(li, recentList.firstChild);
    
    while (recentList.children.length > 5) {
      const last = recentList.lastChild;
      if (last) {
        last.remove();
      } else {
        break;
      }
    }
  }
}

if (form) {
  form.addEventListener("submit", handleAnalyze);
}

const journalInput = document.getElementById("journalUrl");
if (journalInput && form) {
  journalInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      form.requestSubmit ? form.requestSubmit() : form.submit();
    }
  });
}

function attachEnterToForm(formId) {
  const formEl = document.getElementById(formId);
  if (!formEl) return;
  formEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const target = event.target;
      if (target && target.tagName === "TEXTAREA") return;
      formEl.requestSubmit ? formEl.requestSubmit() : formEl.submit();
    }
  });
}

attachEnterToForm("loginForm");
attachEnterToForm("signupForm");

