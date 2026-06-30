const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");
const commentsToday = document.getElementById("comments-today");
const totalComments = document.getElementById("total-comments");
const logList = document.getElementById("log-list");
const toggleBtn = document.getElementById("toggle-btn");
const runNowBtn = document.getElementById("run-now-btn");
const optionsBtn = document.getElementById("options-btn");

let enabled = false;

async function refresh() {
  const status = await chrome.runtime.sendMessage({ type: "GET_STATUS" });
  enabled = status.enabled;

  statusPill.textContent = enabled ? "On" : "Off";
  statusPill.className = `pill ${enabled ? "on" : "off"}`;
  statusText.textContent = status.gate?.ok
    ? "Ready to farm karma autonomously."
    : status.gate?.reason || "Configure settings to begin.";

  commentsToday.textContent = status.stats?.commentsToday ?? 0;
  totalComments.textContent = status.stats?.totalComments ?? 0;

  toggleBtn.textContent = enabled ? "Disable" : "Enable";
  toggleBtn.className = enabled ? "secondary" : "primary";

  logList.innerHTML = "";
  (status.recentLog || []).forEach((entry) => {
    const li = document.createElement("li");
    li.className = entry.level || "info";
    li.textContent = entry.message;
    logList.appendChild(li);
  });
}

toggleBtn.addEventListener("click", async () => {
  toggleBtn.disabled = true;
  await chrome.runtime.sendMessage({ type: "TOGGLE_ENABLED", enabled: !enabled });
  await refresh();
  toggleBtn.disabled = false;
});

runNowBtn.addEventListener("click", async () => {
  runNowBtn.disabled = true;
  runNowBtn.textContent = "Running...";
  await chrome.runtime.sendMessage({ type: "RUN_NOW" });
  await refresh();
  runNowBtn.textContent = "Run now";
  runNowBtn.disabled = false;
});

optionsBtn.addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

refresh();
setInterval(refresh, 5000);
