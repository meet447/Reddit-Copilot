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
  setNetworkBlock
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
  const stats = resetDailyStatsIfNeeded(settings.stats);
  const networkBlocked =
    stats.networkBlockedUntil && Date.now() < stats.networkBlockedUntil;

  return {
    enabled: settings.enabled,
    gate,
    networkBlocked,
    stats,
    subreddits: settings.subreddits,
    recentLog: (settings.activityLog || []).slice(0, 8)
  };
}

async function toggleEnabled(enabled) {
  if (enabled) {
    try {
      await ensureRedditSession();
    } catch (error) {
      await addLogEntry(error.message, "error");
      return { ok: false, error: error.message };
    }
  }

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

async function findExistingRedditTab() {
  const tabs = await chrome.tabs.query({ url: ["https://*.reddit.com/*", "http://*.reddit.com/*"] });
  return tabs.find((tab) => tab.id && !tab.url?.startsWith("chrome-extension://")) || null;
}

async function handleNetworkBlock(tabId) {
  await setNetworkBlock();
  await chrome.alarms.clear(ALARM_NAME);
  if (tabId) {
    try {
      await chrome.tabs.update(tabId, { active: true });
    } catch {
      // ignore
    }
  }
}

async function ensureRedditSession() {
  let tab = await findExistingRedditTab();

  if (!tab?.id) {
    throw new Error(
      "Open reddit.com in Chrome and log in first. The extension reuses your logged-in tab."
    );
  }

  workerTabId = tab.id;

  // Warm session on www.reddit.com before navigating elsewhere
  if (!tab.url?.includes("www.reddit.com") || tab.url?.includes("old.reddit.com")) {
    await chrome.tabs.update(tab.id, { url: "https://www.reddit.com/", active: false });
    await waitForTabLoad(tab.id);
    await sleep(2000 + Math.random() * 2000);
  }

  const session = await sendToTab(tab.id, { type: "SESSION_CHECK" });

  if (session?.blocked) {
    await handleNetworkBlock(tab.id);
    throw new Error(
      "Reddit blocked this network. Use home WiFi (no VPN), log in manually, wait 1 hour."
    );
  }

  if (!session?.loggedIn) {
    await chrome.tabs.update(tab.id, { url: "https://www.reddit.com/login", active: true });
    throw new Error("Not logged into Reddit. Log in, then re-enable the extension.");
  }

  return tab.id;
}

async function navigateWorkerTab(tabId, url) {
  await chrome.tabs.update(tabId, { url, active: false });
  await waitForTabLoad(tabId);
  await sleep(2500 + Math.random() * 2500);

  const session = await sendToTab(tabId, { type: "SESSION_CHECK" });
  if (session?.blocked) {
    await handleNetworkBlock(tabId);
    throw new Error("Reddit network block during navigation.");
  }
  if (!session?.loggedIn) {
    throw new Error("Reddit session lost. Log in again.");
  }
}

async function getOrCreateWorkerTab(url) {
  const tabId = await ensureRedditSession();
  await navigateWorkerTab(tabId, url);
  return tabId;
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

    await navigateWorkerTab(tabId, targetUrl);

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
    const msg = error.message || String(error);
    if (msg.includes("network block") || msg.includes("blocked this network")) {
      // setNetworkBlock already called
    } else {
      await recordFailure(msg);
    }
    if ((await getSettings()).enabled) {
      await scheduleNextTick(30);
    }
    return { ok: false, reason: msg };
  } finally {
    isRunning = false;
  }
}
