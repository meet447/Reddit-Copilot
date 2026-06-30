import { DEFAULT_SETTINGS, MAX_COMMENTED_POSTS, MAX_LOG_ENTRIES, NETWORK_BLOCK_HOURS } from "./constants.js";

export async function getSettings() {
  const stored = await chrome.storage.local.get("settings");
  return { ...DEFAULT_SETTINGS, ...(stored.settings || {}) };
}

export async function saveSettings(partial) {
  const current = await getSettings();
  const next = { ...current, ...partial };
  await chrome.storage.local.set({ settings: next });
  return next;
}

export async function updateSettings(mutator) {
  const current = await getSettings();
  const next = typeof mutator === "function" ? mutator(current) : { ...current, ...mutator };
  await chrome.storage.local.set({ settings: next });
  return next;
}

export function todayKey() {
  return new Date().toISOString().slice(0, 10);
}

export function resetDailyStatsIfNeeded(stats) {
  const today = todayKey();
  if (stats.date !== today) {
    return {
      ...stats,
      date: today,
      commentsToday: 0,
      subCounts: {}
    };
  }
  return stats;
}

export async function addLogEntry(message, level = "info") {
  await updateSettings((settings) => {
    const activityLog = [
      { at: Date.now(), message, level },
      ...(settings.activityLog || [])
    ].slice(0, MAX_LOG_ENTRIES);
    return { ...settings, activityLog };
  });
}

export async function recordComment(postId, subreddit) {
  await updateSettings((settings) => {
    const stats = resetDailyStatsIfNeeded(settings.stats);
    const commentedPosts = [...new Set([postId, ...(settings.commentedPosts || [])])].slice(
      0,
      MAX_COMMENTED_POSTS
    );
    const subCounts = { ...stats.subCounts };
    subCounts[subreddit] = (subCounts[subreddit] || 0) + 1;

    return {
      ...settings,
      commentedPosts,
      stats: {
        ...stats,
        commentsToday: stats.commentsToday + 1,
        totalComments: (stats.totalComments || 0) + 1,
        lastCommentAt: Date.now(),
        consecutiveFailures: 0,
        circuitBreakerUntil: 0,
        subCounts
      }
    };
  });
}

export async function setNetworkBlock(hours = NETWORK_BLOCK_HOURS) {
  await updateSettings((settings) => {
    const stats = resetDailyStatsIfNeeded(settings.stats);
    return {
      ...settings,
      enabled: false,
      stats: {
        ...stats,
        networkBlockedUntil: Date.now() + hours * 60 * 60 * 1000
      }
    };
  });
  await addLogEntry(
    `Reddit network block detected. Paused ${hours}h — log into reddit.com on home WiFi, no VPN.`,
    "error"
  );
}

export async function recordFailure(reason, { critical = true } = {}) {
  if (!critical) {
    await addLogEntry(reason, "warn");
    return;
  }

  await updateSettings((settings) => {
    const stats = resetDailyStatsIfNeeded(settings.stats);
    const failures = (stats.consecutiveFailures || 0) + 1;
    let circuitBreakerUntil = stats.circuitBreakerUntil || 0;

    if (failures >= 3) {
      circuitBreakerUntil = Date.now() + 2 * 60 * 60 * 1000;
    }

    return {
      ...settings,
      stats: {
        ...stats,
        consecutiveFailures: failures,
        circuitBreakerUntil
      }
    };
  });
  await addLogEntry(reason, "error");
}
