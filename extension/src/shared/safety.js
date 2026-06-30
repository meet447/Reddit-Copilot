import { CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_MINUTES } from "./constants.js";
import { resetDailyStatsIfNeeded } from "./storage.js";

export function isWithinActiveHours(settings) {
  const hour = new Date().getHours();
  const start = settings.activeHoursStart ?? 8;
  const end = settings.activeHoursEnd ?? 23;
  if (start <= end) {
    return hour >= start && hour < end;
  }
  return hour >= start || hour < end;
}

export function canCommentNow(settings) {
  const stats = resetDailyStatsIfNeeded(settings.stats);

  if (!settings.enabled) {
    return { ok: false, reason: "Extension is disabled." };
  }

  if (!settings.apiKey?.trim()) {
    return { ok: false, reason: "Add an AI API key in Options." };
  }

  if (!settings.subreddits?.length) {
    return { ok: false, reason: "Add at least one subreddit in Options." };
  }

  if (!isWithinActiveHours(settings)) {
    return { ok: false, reason: "Outside active hours. Bot sleeps until your window opens." };
  }

  if (stats.networkBlockedUntil && Date.now() < stats.networkBlockedUntil) {
    const mins = Math.ceil((stats.networkBlockedUntil - Date.now()) / 60000);
    return {
      ok: false,
      reason: `Reddit network block active (~${mins} min left). Log into reddit.com manually on home WiFi.`
    };
  }

  if (stats.circuitBreakerUntil && Date.now() < stats.circuitBreakerUntil) {
    const mins = Math.ceil((stats.circuitBreakerUntil - Date.now()) / 60000);
    return { ok: false, reason: `Circuit breaker active. Paused for ~${mins} min after repeated failures.` };
  }

  if (stats.commentsToday >= (settings.maxCommentsPerDay || 8)) {
    return { ok: false, reason: "Daily comment limit reached. Resets at midnight." };
  }

  const minGapMs = (settings.minDelayMinutes || 8) * 60 * 1000;
  if (stats.lastCommentAt && Date.now() - stats.lastCommentAt < minGapMs) {
    const wait = Math.ceil((minGapMs - (Date.now() - stats.lastCommentAt)) / 60000);
    return { ok: false, reason: `Cooldown active. Next comment in ~${wait} min.` };
  }

  return { ok: true, stats };
}

export function canCommentInSubreddit(settings, subreddit, stats) {
  const count = stats.subCounts?.[subreddit] || 0;
  const limit = settings.maxPerSubredditPerDay || 2;
  if (count >= limit) {
    return { ok: false, reason: `Daily limit reached for r/${subreddit}.` };
  }
  return { ok: true };
}

export function pickRandomSubreddit(settings, stats) {
  const eligible = settings.subreddits.filter((sub) => {
    const check = canCommentInSubreddit(settings, sub, stats);
    return check.ok;
  });

  if (!eligible.length) {
    return null;
  }

  return eligible[Math.floor(Math.random() * eligible.length)];
}

export function randomDelayMinutes(settings) {
  const min = settings.minDelayMinutes || 8;
  const max = settings.maxDelayMinutes || 22;
  return min + Math.random() * (max - min);
}

export function gaussianDelay(meanMs, sigmaMs) {
  let u = 0;
  let v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  const num = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return Math.max(200, meanMs + num * sigmaMs);
}
