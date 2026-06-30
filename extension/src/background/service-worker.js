import { ALARM_NAME } from "../shared/constants.js";
import { generateComment } from "../shared/ai.js";
import {
  canCommentNow,
  pickRandomSubreddit,
  randomDelayMinutes
} from "../shared/safety.js";
import {
  addLogEntry,
  getSettings,
  recordComment,
  recordFailure,
  resetDailyStatsIfNeeded,
  saveSettings,
  updateSettings
} from "../shared/storage.js";

let workerTabId = null;
let isRunning = false;

chrome.runtime.onInstalled.addListener(async () => {
  const settings = await getSettings();
  await saveSettings(settings);
  await addLogEntry("Extension installed. Open Options to add your AI API key.");
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === ALARM_NAME) {
    await runFarmCycle();
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "TOGGLE_ENABLED") {
    toggleEnabled(message.enabled).then(sendResponse);
    return true;
  }
  if (message.type === "RUN_NOW") {
    runFarmCycle().then(sendResponse);
    return true;
  }
  if (message.type === "GET_STATUS") {
    getStatus().then(sendResponse);
    return true;
  }
});

async function getStatus() {
  const settings = await getSettings();
  const gate = canCommentNow(settings);
  return {
    enabled: settings.enabled,
    gate,
    stats: resetDailyStatsIfNeeded(settings.stats),
    subreddits: settings.subreddits,
    recentLog: (settings.activityLog || []).slice(0, 8)
  };
}

async function toggleEnabled(enabled) {
  const settings = await saveSettings({ enabled });
  if (enabled) {
    await addLogEntry("Karma farmer enabled.");
    await scheduleNextTick(0.2);
  } else {
    await chrome.alarms.clear(ALARM_NAME);
    await addLogEntry("Karma farmer disabled.");
    if (workerTabId) {
      try {
        await chrome.tabs.remove(workerTabId);
      } catch {
        // tab may already be closed
      }
      workerTabId = null;
    }
  }
  return { ok: true, enabled: settings.enabled };
}

async function scheduleNextTick(minutes) {
  const delay = minutes ?? randomDelayMinutes(await getSettings());
  await chrome.alarms.create(ALARM_NAME, { delayInMinutes: Math.max(0.1, delay) });
  await addLogEntry(`Next action scheduled in ~${Math.round(delay)} min.`);
  return delay;
}

async function getOrCreateWorkerTab(url) {
  if (workerTabId) {
    try {
      const tab = await chrome.tabs.get(workerTabId);
      await chrome.tabs.update(tab.id, { url, active: false });
      return tab.id;
    } catch {
      workerTabId = null;
    }
  }

  const tab = await chrome.tabs.create({ url, active: false });
  workerTabId = tab.id;
  return tab.id;
}

async function waitForTabLoad(tabId, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") {
      await sleep(1500 + Math.random() * 2000);
      return;
    }
    await sleep(400);
  }
  throw new Error("Tab load timeout");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function sendToTab(tabId, message, retries = 5) {
  for (let i = 0; i < retries; i++) {
    try {
      return await chrome.tabs.sendMessage(tabId, message);
    } catch (error) {
      if (i === retries - 1) throw error;
      await sleep(800);
    }
  }
}

function listingUrl(subreddit, useOldReddit) {
  const base = useOldReddit ? "https://old.reddit.com" : "https://www.reddit.com";
  return `${base}/r/${subreddit}/new/`;
}

function postUrl(url, useOldReddit) {
  if (!useOldReddit) return url;
  return url.replace("https://www.reddit.com", "https://old.reddit.com");
}

async function runFarmCycle() {
  if (isRunning) {
    return { ok: false, reason: "Cycle already running" };
  }

  isRunning = true;
  try {
    const settings = await getSettings();
    const gate = canCommentNow(settings);

    if (!gate.ok) {
      if (settings.enabled) {
        await scheduleNextTick(15);
      }
      return { ok: false, reason: gate.reason };
    }

    const stats = gate.stats;
    const subreddit = pickRandomSubreddit(settings, stats);
    if (!subreddit) {
      await addLogEntry("All configured subreddits hit their daily limits.");
      await scheduleNextTick(30);
      return { ok: false, reason: "Subreddit limits reached" };
    }

    await addLogEntry(`Scanning r/${subreddit} for threads...`);

    const tabId = await getOrCreateWorkerTab(listingUrl(subreddit, settings.useOldReddit));
    await waitForTabLoad(tabId);

    const scan = await sendToTab(tabId, {
      type: "SCAN_LISTING",
      commentedPosts: settings.commentedPosts,
      skipNsfw: settings.skipNsfw
    });

    if (!scan?.ok || !scan.posts?.length) {
      await recordFailure(`No eligible posts found in r/${subreddit}.`, { critical: false });
      await scheduleNextTick();
      return { ok: false, reason: "No posts found" };
    }

    const post = scan.posts[Math.floor(Math.random() * Math.min(scan.posts.length, 12))];
    const targetUrl = postUrl(post.url, settings.useOldReddit);

    await chrome.tabs.update(tabId, { url: targetUrl });
    await waitForTabLoad(tabId);

    const gateCheck = await sendToTab(tabId, { type: "CHECK_COMMENT_GATE" });
    if (!gateCheck?.allowed) {
      await recordFailure(`Comment gate blocked r/${subreddit} thread.`);
      await scheduleNextTick();
      return { ok: false, reason: "Comment gate" };
    }

    const context = await sendToTab(tabId, { type: "GET_POST_CONTEXT" });
    if (!context?.ok) {
      await recordFailure("Failed to read post context.");
      await scheduleNextTick();
      return { ok: false, reason: "Context failed" };
    }

    await addLogEntry(`Drafting comment for: ${context.title?.slice(0, 60)}...`);
    const comment = await generateComment(settings, {
      title: context.title,
      body: context.body,
      subreddit: context.subreddit || subreddit,
      topComments: context.topComments
    });

    const posted = await sendToTab(tabId, { type: "POST_COMMENT", comment });
    if (!posted?.ok) {
      await recordFailure(posted?.error || "Failed to post comment.");
      await scheduleNextTick();
      return { ok: false, reason: posted?.error };
    }

    await recordComment(posted.postId || post.id, subreddit);

    if (posted.visible === false) {
      await addLogEntry("Comment may have been filtered. Monitoring...", "warn");
    } else {
      await addLogEntry(`Comment posted in r/${subreddit}.`, "success");
    }

    await scheduleNextTick();
    return { ok: true, subreddit, postId: post.id };
  } catch (error) {
    await recordFailure(error.message);
    await scheduleNextTick();
    return { ok: false, reason: error.message };
  } finally {
    isRunning = false;
  }
}
