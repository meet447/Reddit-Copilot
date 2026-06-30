import { DEFAULT_SETTINGS, PROVIDER_PRESETS } from "../shared/constants.js";
import { getSettings, saveSettings } from "../shared/storage.js";

const form = document.getElementById("settings-form");
const saveStatus = document.getElementById("save-status");
const aiProvider = document.getElementById("aiProvider");
const apiModel = document.getElementById("apiModel");

function fillForm(settings) {
  aiProvider.value = settings.aiProvider || "groq";
  document.getElementById("apiKey").value = settings.apiKey || "";
  apiModel.value = settings.apiModel || PROVIDER_PRESETS.groq.defaultModel;
  document.getElementById("apiBaseUrl").value = settings.apiBaseUrl || "";
  document.getElementById("subreddits").value = (settings.subreddits || []).join("\n");
  document.getElementById("useOldReddit").checked = settings.useOldReddit !== false;
  document.getElementById("skipNsfw").checked = settings.skipNsfw !== false;
  document.getElementById("warmupMode").checked = settings.warmupMode !== false;
  document.getElementById("maxCommentsPerDay").value = settings.maxCommentsPerDay ?? 8;
  document.getElementById("maxPerSubredditPerDay").value = settings.maxPerSubredditPerDay ?? 2;
  document.getElementById("minDelayMinutes").value = settings.minDelayMinutes ?? 8;
  document.getElementById("maxDelayMinutes").value = settings.maxDelayMinutes ?? 22;
  document.getElementById("activeHoursStart").value = settings.activeHoursStart ?? 8;
  document.getElementById("activeHoursEnd").value = settings.activeHoursEnd ?? 23;
}

aiProvider.addEventListener("change", () => {
  const preset = PROVIDER_PRESETS[aiProvider.value];
  if (preset) {
    apiModel.value = preset.defaultModel;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);

  const subreddits = String(data.get("subreddits") || "")
    .split("\n")
    .map((s) => s.trim().replace(/^r\//i, ""))
    .filter(Boolean);

  await saveSettings({
    aiProvider: data.get("aiProvider"),
    apiKey: String(data.get("apiKey") || "").trim(),
    apiModel: String(data.get("apiModel") || "").trim(),
    apiBaseUrl: String(data.get("apiBaseUrl") || "").trim(),
    subreddits,
    useOldReddit: data.get("useOldReddit") === "on",
    skipNsfw: data.get("skipNsfw") === "on",
    warmupMode: data.get("warmupMode") === "on",
    maxCommentsPerDay: Number(data.get("maxCommentsPerDay")),
    maxPerSubredditPerDay: Number(data.get("maxPerSubredditPerDay")),
    minDelayMinutes: Number(data.get("minDelayMinutes")),
    maxDelayMinutes: Number(data.get("maxDelayMinutes")),
    activeHoursStart: Number(data.get("activeHoursStart")),
    activeHoursEnd: Number(data.get("activeHoursEnd"))
  });

  saveStatus.textContent = "Settings saved.";
  setTimeout(() => {
    saveStatus.textContent = "";
  }, 2500);
});

const settings = await getSettings();
fillForm({ ...DEFAULT_SETTINGS, ...settings });
