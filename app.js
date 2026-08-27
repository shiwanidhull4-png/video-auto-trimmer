const states = {
  upload: document.getElementById("state-upload"),
  processing: document.getElementById("state-processing"),
  result: document.getElementById("state-result"),
  error: document.getElementById("state-error"),
};

function showState(name) {
  Object.values(states).forEach(el => el.hidden = true);
  states[name].hidden = false;
}

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const errorMsg = document.getElementById("errorMsg");

["dragenter", "dragover"].forEach(evt => {
  dropzone.addEventListener(evt, e => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});
["dragleave", "drop"].forEach(evt => {
  dropzone.addEventListener(evt, e => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});
dropzone.addEventListener("drop", e => {
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

const STAGES = [
  "Reading audio track…",
  "Scanning for silence…",
  "Sampling frames for blur…",
  "Cutting the bad parts…",
  "Stitching final video…",
];

let stageTimer = null;

function runStagedLog() {
  const log = document.getElementById("statusLog");
  log.innerHTML = "";
  let i = 0;

  function step() {
    Array.from(log.children).forEach(li => {
      li.classList.remove("active");
      li.classList.add("done");
    });
    if (i < STAGES.length) {
      const li = document.createElement("li");
      li.textContent = STAGES[i];
      li.classList.add("active");
      li.style.animationDelay = "0s";
      log.appendChild(li);
      i++;
      stageTimer = setTimeout(step, 1400);
    }
  }
  step();
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

async function handleFile(file) {
  errorMsg.hidden = true;

  if (!file.type.startsWith("video/")) {
    errorMsg.textContent = "Please upload a video file.";
    errorMsg.hidden = false;
    return;
  }

  document.getElementById("fileNameLabel").textContent = file.name;
  showState("processing");
  runStagedLog();

  const formData = new FormData();
  formData.append("video", file);

  try {
    const res = await fetch("/api/process", { method: "POST", body: formData });
    const data = await res.json();

    clearTimeout(stageTimer);

    if (!res.ok) {
      throw new Error(data.error || "Processing failed.");
    }

    renderResult(file.name, data);
  } catch (err) {
    clearTimeout(stageTimer);
    document.getElementById("errorBig").textContent = err.message || "Something went wrong.";
    showState("error");
  }
}

function renderResult(filename, data) {
  document.getElementById("resultFileName").textContent = filename;

  const timeline = document.getElementById("timeline");
  timeline.innerHTML = "";
  const duration = data.original_duration || 1;

  let cursor = 0;
  const segments = [];
  data.cuts.forEach(cut => {
    if (cut.start > cursor) {
      segments.push({ type: "keep", len: cut.start - cursor });
    }
    segments.push({ type: "cut", len: cut.end - cut.start });
    cursor = cut.end;
  });
  if (cursor < duration) {
    segments.push({ type: "keep", len: duration - cursor });
  }
  if (segments.length === 0) {
    segments.push({ type: "keep", len: duration });
  }

  segments.forEach(seg => {
    const div = document.createElement("div");
    div.className = `seg ${seg.type}`;
    div.style.width = `${(seg.len / duration) * 100}%`;
    timeline.appendChild(div);
  });

  document.getElementById("statOriginal").textContent = formatTime(data.original_duration);
  document.getElementById("statFinal").textContent = formatTime(data.final_duration);
  const removedPct = Math.round(((data.original_duration - data.final_duration) / data.original_duration) * 100);
  document.getElementById("statRemoved").textContent = `${removedPct}%`;

  document.getElementById("detectedLine").textContent =
    `${data.silence_count} silent part${data.silence_count === 1 ? "" : "s"} · ${data.blur_count} blurry part${data.blur_count === 1 ? "" : "s"} detected`;

  document.getElementById("downloadBtn").href = data.download_url;

  showState("result");
}

document.getElementById("resetBtn").addEventListener("click", () => {
  fileInput.value = "";
  showState("upload");
});
document.getElementById("errorResetBtn").addEventListener("click", () => {
  fileInput.value = "";
  showState("upload");
});
