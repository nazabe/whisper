"use strict";

const els = {
  status: document.getElementById("status"),
  timer: document.getElementById("timer"),
  meter: document.getElementById("meter"),
  meterBar: document.getElementById("meterBar"),
  recordButton: document.getElementById("recordButton"),
  sendButton: document.getElementById("sendButton"),
  resetButton: document.getElementById("resetButton"),
  uploadButton: document.getElementById("uploadButton"),
  fileInput: document.getElementById("fileInput"),
  downloadLink: document.getElementById("downloadLink"),
  preview: document.getElementById("preview"),
  language: document.getElementById("language"),
  voiceProcessing: document.getElementById("voiceProcessing"),
  error: document.getElementById("error"),
  result: document.getElementById("result"),
  metaLanguage: document.getElementById("metaLanguage"),
  metaDuration: document.getElementById("metaDuration"),
  metaRecorded: document.getElementById("metaRecorded"),
  fullText: document.getElementById("fullText"),
  segments: document.getElementById("segments"),
};

const state = {
  recorder: null,
  stream: null,
  chunks: [],
  blob: null,
  fileName: "",
  previewUrl: null,
  timerId: null,
  startedAt: 0,
  recordedSeconds: null,
  busy: false,
  starting: false,
  audioContext: null,
  meterSource: null,
  analyser: null,
  meterData: null,
  meterRaf: null,
};

const TRANSCRIPTION_TIMEOUT_MS = 15 * 60 * 1000;
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

const MIME_BY_EXTENSION = {
  mp3: "audio/mpeg",
  wav: "audio/wav",
  webm: "audio/webm",
  m4a: "audio/mp4",
  mp4: "audio/mp4",
  ogg: "audio/ogg",
  oga: "audio/ogg",
  opus: "audio/ogg",
  aac: "audio/aac",
  flac: "audio/flac",
};

const MIME_ALIASES = {
  "audio/x-m4a": "audio/mp4",
  "audio/mp3": "audio/mpeg",
  "audio/x-wav": "audio/wav",
  "audio/x-flac": "audio/flac",
  "video/webm": "audio/webm",
};

function setStatus(message, kind = "") {
  els.status.textContent = message;
  els.status.className = kind ? `status ${kind}` : "status";
}

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = false;
}

function clearError() {
  els.error.textContent = "";
  els.error.hidden = true;
}

function clearResult() {
  els.result.hidden = true;
  els.metaLanguage.textContent = "-";
  els.metaDuration.textContent = "-";
  els.metaRecorded.textContent = "-";
  els.fullText.textContent = "";
  els.segments.replaceChildren();
}

function setBusy(busy) {
  state.busy = busy;
  els.recordButton.disabled = busy;
  els.sendButton.disabled = busy || !state.blob;
  els.resetButton.disabled = busy;
  els.uploadButton.disabled = busy;
  els.language.disabled = busy;
  els.voiceProcessing.disabled = busy;
}

function formatSeconds(value) {
  const total = Math.max(0, Math.floor(Number(value) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}

function formatClock(milliseconds) {
  return formatSeconds(milliseconds / 1000);
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(1)} ${units[index]}`;
}

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") {
    return "";
  }
  return (
    MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) || ""
  );
}

function normalizeMimeType(type) {
  const base = (type || "").split(";")[0].trim().toLowerCase();
  return MIME_ALIASES[base] || base;
}

function inferMimeType(fileName) {
  const extension = (fileName || "").split(".").pop()?.toLowerCase() || "";
  return MIME_BY_EXTENSION[extension] || "";
}

function extensionFor(type) {
  const normalized = normalizeMimeType(type);
  if (normalized === "audio/mp4") {
    return ".m4a";
  }
  if (normalized === "audio/ogg") {
    return ".ogg";
  }
  if (normalized === "audio/wav") {
    return ".wav";
  }
  if (normalized === "audio/aac") {
    return ".aac";
  }
  if (normalized === "audio/flac") {
    return ".flac";
  }
  if (normalized === "audio/mpeg") {
    return ".mp3";
  }
  return ".webm";
}

function timestampForName() {
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}

function updateTimer() {
  els.timer.textContent = formatClock(performance.now() - state.startedAt);
}

function stopMeter() {
  if (state.meterRaf) {
    window.cancelAnimationFrame(state.meterRaf);
    state.meterRaf = null;
  }
  if (state.meterSource) {
    try {
      state.meterSource.disconnect();
    } catch {
      /* ignore */
    }
    state.meterSource = null;
  }
  if (state.audioContext) {
    state.audioContext.close().catch(() => {});
    state.audioContext = null;
  }
  state.analyser = null;
  state.meterData = null;
  els.meter.hidden = true;
  els.meterBar.style.width = "0%";
  els.meterBar.classList.remove("hot");
}

function startMeter(stream) {
  stopMeter();

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    return;
  }

  try {
    const context = new AudioContextClass();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);

    state.audioContext = context;
    state.meterSource = source;
    state.analyser = analyser;
    state.meterData = new Uint8Array(analyser.fftSize);
    els.meter.hidden = false;
    context.resume().catch(() => {});

    const tick = () => {
      if (!state.analyser || !state.meterData) {
        return;
      }
      state.analyser.getByteTimeDomainData(state.meterData);

      let sum = 0;
      for (const value of state.meterData) {
        const normalized = (value - 128) / 128;
        sum += normalized * normalized;
      }
      const rms = Math.sqrt(sum / state.meterData.length);
      const percent = Math.min(100, Math.round(rms * 320));

      els.meterBar.style.width = `${percent}%`;
      els.meterBar.classList.toggle("hot", rms > 0.85);
      state.meterRaf = window.requestAnimationFrame(tick);
    };

    tick();
  } catch {
    stopMeter();
  }
}

function discardPreviousRecording() {
  if (state.previewUrl) {
    URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = null;
  }
  els.preview.pause();
  els.preview.removeAttribute("src");
  els.preview.load();
  els.preview.hidden = true;

  els.downloadLink.hidden = true;
  els.downloadLink.removeAttribute("href");
  els.downloadLink.removeAttribute("download");

  state.blob = null;
  state.chunks = [];
  state.fileName = "";
  state.recordedSeconds = null;
}

function handleRecorderStop() {
  const recorder = state.recorder;
  const type = recorder?.mimeType || state.chunks[0]?.type || "audio/webm";
  const blob = new Blob(state.chunks, { type });
  const recordedSeconds = state.startedAt
    ? (performance.now() - state.startedAt) / 1000
    : null;

  state.recorder = null;
  state.chunks = [];
  state.blob = blob;
  state.recordedSeconds = recordedSeconds;

  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
    state.stream = null;
  }
  stopMeter();
  els.recordButton.disabled = false;

  if (blob.size === 0) {
    showError("No se capturó audio. Revisá el micrófono e intentá de nuevo.");
    setStatus("Sin audio", "error");
    return;
  }

  state.fileName = `recording-${timestampForName()}${extensionFor(type)}`;
  state.previewUrl = URL.createObjectURL(blob);
  els.preview.src = state.previewUrl;
  els.preview.hidden = false;

  els.sendButton.disabled = false;
  els.resetButton.hidden = false;
  els.resetButton.disabled = false;
  els.downloadLink.href = state.previewUrl;
  els.downloadLink.download = state.fileName;
  els.downloadLink.hidden = false;

  els.timer.textContent = formatSeconds(recordedSeconds);
  setStatus(`Grabación lista (${formatBytes(blob.size)})`, "ready");
}

async function startRecording() {
  if (state.starting || state.busy) {
    return;
  }

  clearError();
  clearResult();
  discardPreviousRecording();
  els.timer.textContent = "00:00";
  els.resetButton.hidden = true;

  if (!navigator.mediaDevices?.getUserMedia) {
    showError(
      "Este navegador no expone el micrófono. Usá localhost o HTTPS y un navegador moderno.",
    );
    setStatus("No disponible", "error");
    return;
  }

  if (typeof MediaRecorder === "undefined") {
    showError("Este navegador no soporta MediaRecorder.");
    setStatus("No disponible", "error");
    return;
  }

  state.starting = true;
  els.recordButton.disabled = true;

  try {
    const processing = els.voiceProcessing.checked;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 48000,
        echoCancellation: processing,
        noiseSuppression: processing,
        autoGainControl: processing,
      },
    });

    const mimeType = pickMimeType();
    const options = { audioBitsPerSecond: 128000 };
    if (mimeType) {
      options.mimeType = mimeType;
    }
    const recorder = new MediaRecorder(stream, options);

    state.stream = stream;
    state.recorder = recorder;
    state.chunks = [];

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data && event.data.size > 0) {
        state.chunks.push(event.data);
      }
    });
    recorder.addEventListener("stop", handleRecorderStop);

    recorder.start(1000);
    state.startedAt = performance.now();
    state.timerId = window.setInterval(updateTimer, 200);
    startMeter(stream);

    els.recordButton.textContent = "Detener";
    els.recordButton.classList.add("recording");
    els.sendButton.disabled = true;
    setStatus("Grabando…", "recording");
  } catch (error) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      showError(
        "Permiso de micrófono denegado. Habilitalo en el navegador e intentá de nuevo.",
      );
    } else if (error.name === "NotFoundError") {
      showError("No se encontró un micrófono disponible.");
    } else {
      showError(`No se pudo iniciar la grabación: ${error.message}`);
    }
    setStatus("Error", "error");
  } finally {
    state.starting = false;
    els.recordButton.disabled = false;
  }
}

function stopRecording() {
  if (!state.recorder || state.recorder.state === "inactive") {
    return;
  }

  state.recorder.stop();
  els.recordButton.disabled = true;

  if (state.timerId) {
    window.clearInterval(state.timerId);
    state.timerId = null;
  }

  els.recordButton.textContent = "Grabar";
  els.recordButton.classList.remove("recording");
  setStatus("Preparando la grabación…", "busy");
}

function handleFileSelection(event) {
  const file = event.target.files?.[0];
  event.target.value = "";

  if (!file) {
    return;
  }

  if (state.recorder && state.recorder.state === "recording") {
    showError("Detené la grabación antes de subir un archivo.");
    return;
  }

  if (state.busy) {
    return;
  }

  clearError();
  clearResult();
  discardPreviousRecording();

  const type = normalizeMimeType(file.type || inferMimeType(file.name));
  if (!type) {
    showError(
      "No se pudo determinar el tipo del archivo. Probá con MP3, WAV, WebM, M4A u OGG.",
    );
    setStatus("Archivo no soportado", "error");
    return;
  }

  state.blob = file.type === type ? file : new Blob([file], { type });
  state.fileName = file.name || `upload${extensionFor(type)}`;
  state.recordedSeconds = null;

  state.previewUrl = URL.createObjectURL(state.blob);
  els.preview.src = state.previewUrl;
  els.preview.hidden = false;

  els.sendButton.disabled = false;
  els.resetButton.hidden = false;
  els.resetButton.disabled = false;
  els.downloadLink.href = state.previewUrl;
  els.downloadLink.download = state.fileName;
  els.downloadLink.hidden = false;
  els.timer.textContent = "00:00";

  setStatus(`Archivo listo (${formatBytes(state.blob.size)})`, "ready");
}

function renderResult(payload) {
  const probability =
    typeof payload.language_probability === "number"
      ? ` (${Math.round(payload.language_probability * 100)}%)`
      : "";

  els.metaLanguage.textContent = `${payload.language || "-"}${probability}`;
  els.metaDuration.textContent = formatSeconds(payload.duration_sec);
  els.metaRecorded.textContent =
    state.recordedSeconds === null
      ? "-"
      : formatSeconds(state.recordedSeconds);
  els.fullText.textContent = payload.text || "(sin texto)";
  els.segments.replaceChildren();

  const segments = Array.isArray(payload.segments) ? payload.segments : [];
  for (const segment of segments) {
    const item = document.createElement("li");

    const time = document.createElement("span");
    time.className = "segment-time";
    time.textContent = `${formatSeconds(segment.start)} – ${formatSeconds(segment.end)}`;

    const text = document.createElement("span");
    text.textContent = segment.text;

    item.append(time, text);
    els.segments.append(item);
  }

  if (segments.length === 0) {
    const item = document.createElement("li");
    item.textContent = "El servicio no devolvió segmentos.";
    els.segments.append(item);
  }

  els.result.hidden = false;
  els.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

function describeHttpError(status, payload) {
  if (status === 413) {
    return "El audio supera el límite de tamaño del servicio.";
  }
  if (status === 503) {
    return "El servicio está ocupado o el modelo no está listo. Intentá de nuevo en unos segundos.";
  }
  if (status === 400) {
    return "El servicio no pudo decodificar el audio. Probá grabar de nuevo.";
  }
  const detail = payload?.detail;
  if (typeof detail === "string" && detail) {
    return detail;
  }
  if (Array.isArray(detail)) {
    return "La solicitud no es válida.";
  }
  return `El servicio respondió con un error HTTP ${status}.`;
}

async function sendRecording() {
  if (!state.blob || state.busy) {
    return;
  }

  clearError();
  clearResult();
  setBusy(true);
  setStatus("Enviando audio…", "busy");

  const form = new FormData();
  form.append(
    "file",
    state.blob,
    state.fileName || `recording${extensionFor(state.blob.type)}`,
  );

  const language = els.language.value;
  if (language) {
    form.append("language", language);
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    TRANSCRIPTION_TIMEOUT_MS,
  );
  const startedAt = performance.now();
  const tickerId = window.setInterval(() => {
    setStatus(
      `Transcribiendo… ${formatClock(performance.now() - startedAt)}`,
      "busy",
    );
  }, 1000);

  try {
    const response = await fetch("/transcribe", {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(describeHttpError(response.status, payload));
    }

    renderResult(payload);
    setStatus("Transcripción lista", "done");
  } catch (error) {
    if (error.name === "AbortError") {
      showError(
        "La transcripción tardó demasiado y se canceló la espera. El servicio puede seguir procesando.",
      );
    } else {
      showError(error.message || "No se pudo transcribir el audio.");
    }
    setStatus("Error", "error");
  } finally {
    window.clearTimeout(timeoutId);
    window.clearInterval(tickerId);
    setBusy(false);
  }
}

function resetClient() {
  if (state.timerId) {
    window.clearInterval(state.timerId);
    state.timerId = null;
  }

  stopMeter();

  if (state.recorder && state.recorder.state !== "inactive") {
    state.recorder.stop();
  }
  state.recorder = null;

  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
    state.stream = null;
  }

  discardPreviousRecording();

  els.timer.textContent = "00:00";
  els.recordButton.textContent = "Grabar";
  els.recordButton.classList.remove("recording");
  els.recordButton.disabled = false;
  els.sendButton.disabled = true;
  els.resetButton.hidden = true;
  els.resetButton.disabled = false;
  els.fileInput.value = "";
  clearError();
  clearResult();
  setStatus("Listo para grabar");
}

els.recordButton.addEventListener("click", () => {
  if (state.recorder && state.recorder.state === "recording") {
    stopRecording();
  } else {
    startRecording();
  }
});

els.sendButton.addEventListener("click", sendRecording);
els.resetButton.addEventListener("click", resetClient);
els.uploadButton.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", handleFileSelection);

window.addEventListener("beforeunload", () => {
  stopMeter();
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
  }
  if (state.previewUrl) {
    URL.revokeObjectURL(state.previewUrl);
  }
});
