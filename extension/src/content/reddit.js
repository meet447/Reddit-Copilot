const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function isOldReddit() {
  return window.location.hostname === "old.reddit.com";
}

function isNetworkBlocked() {
  const text = (document.body?.innerText || document.title || "").toLowerCase();
  return (
    text.includes("whoa there, pardner") ||
    text.includes("blocked due to a network policy") ||
    text.includes("network policy") && text.includes("blocked")
  );
}

function isLoggedIn() {
  if (isNetworkBlocked()) return false;

  if (isOldReddit()) {
    const loginLink = document.querySelector('#header .user a[href*="login"]');
    const registerLink = document.querySelector('#header .user a[href*="register"]');
    return !loginLink && !registerLink;
  }

  return !!(
    document.querySelector(
      '#expand-user-drawer-button, [data-testid="user-drawer-button"], shreddit-async-loader[bundlename="profile_overview"]'
    ) ||
    document.querySelector('a[href*="/settings"]') ||
    document.querySelector('[id*="USER_DROPDOWN"]')
  );
}

function getSessionStatus() {
  const blocked = isNetworkBlocked();
  const loggedIn = !blocked && isLoggedIn();
  return { blocked, loggedIn };
}

function assertSessionReady() {
  const { blocked, loggedIn } = getSessionStatus();
  if (blocked) {
    throw new Error("Reddit network block page detected");
  }
  if (!loggedIn) {
    throw new Error("Not logged into Reddit — log in at reddit.com first");
  }
}

function extractPostId(url) {
  const match = url.match(/comments\/([a-z0-9]+)/i);
  return match ? match[1] : null;
}

function extractSubreddit(url = window.location.href) {
  const match = url.match(/\/r\/([^/]+)/i);
  return match ? match[1] : null;
}

function isListingPage() {
  const path = window.location.pathname;
  return /\/r\/[^/]+\/(hot|new|rising|top)?\/?$/.test(path) || path.match(/\/r\/[^/]+\/?$/);
}

function isPostPage() {
  return /\/comments\//.test(window.location.pathname);
}

function scanOldRedditListing({ commentedPosts, skipNsfw }) {
  const posts = [];
  const seen = new Set(commentedPosts || []);

  document.querySelectorAll(".thing.link").forEach((el) => {
    const titleLink = el.querySelector("a.title");
    if (!titleLink) return;

    const href = titleLink.href;
    const postId = extractPostId(href);
    if (!postId || seen.has(postId)) return;

    const isNsfw = el.classList.contains("over18");
    const isLocked = !!el.querySelector(".locked");
    const isStickied = el.classList.contains("stickied");

    if (skipNsfw && isNsfw) return;
    if (isLocked || isStickied) return;

    posts.push({
      id: postId,
      url: href,
      title: titleLink.textContent.trim(),
      subreddit: extractSubreddit(href)
    });
  });

  return posts;
}

function scanNewRedditListing({ commentedPosts, skipNsfw }) {
  const posts = [];
  const seen = new Set(commentedPosts || []);

  document.querySelectorAll('a[data-testid="post-title"]').forEach((titleLink) => {
    const href = titleLink.href;
    const postId = extractPostId(href);
    if (!postId || seen.has(postId)) return;

    const article = titleLink.closest("article, shreddit-post");
    const nsfw = article?.querySelector('[aria-label*="NSFW"], [data-testid="nsfw-badge"]');
    if (skipNsfw && nsfw) return;

    posts.push({
      id: postId,
      url: href,
      title: titleLink.textContent.trim(),
      subreddit: extractSubreddit(href)
    });
  });

  return posts;
}

function getTopCommentsOldReddit(limit = 4) {
  const comments = [];
  document.querySelectorAll(".comment .usertext-body").forEach((el) => {
    const text = el.textContent.trim();
    if (text && text.length > 10) comments.push(text.slice(0, 200));
  });
  return comments.slice(0, limit);
}

function getTopCommentsNewReddit(limit = 4) {
  const comments = [];
  document.querySelectorAll('[data-test-id="comment"] p, shreddit-comment').forEach((el) => {
    const text = el.textContent?.trim();
    if (text && text.length > 10) comments.push(text.slice(0, 200));
  });
  return comments.slice(0, limit);
}

function hasCommentGateOldReddit() {
  const textarea = document.querySelector("form.usertext textarea[name='text'], form.usertext-edit textarea");
  return !!textarea && !textarea.disabled;
}

function hasCommentGateNewReddit() {
  const textarea = document.querySelector(
    'textarea[placeholder*="comment" i], textarea[name="body"], div[contenteditable="true"][data-testid]'
  );
  return !!textarea;
}

function getPostContent() {
  const title = isOldReddit()
    ? document.querySelector(".title a.title, .top-matter .title")?.textContent?.trim()
    : document.querySelector('h1[slot="title"], [data-test-id="post-content"] h1, h1')?.textContent?.trim();

  const body = isOldReddit()
    ? document.querySelector(".expando .usertext-body, .thing.link .usertext-body")?.textContent?.trim()
    : document.querySelector('[data-test-id="post-content"] div, .md')?.textContent?.trim();

  const topComments = isOldReddit() ? getTopCommentsOldReddit() : getTopCommentsNewReddit();

  return {
    title: title || document.title,
    body: body || "",
    subreddit: extractSubreddit(),
    topComments
  };
}

async function humanScroll() {
  const distance = 120 + Math.random() * 280;
  window.scrollBy({ top: distance, behavior: "smooth" });
  await sleep(600 + Math.random() * 1200);
}

async function humanType(element, text) {
  element.focus();
  element.click();

  if ("value" in element) {
    element.value = "";
    for (const char of text) {
      element.value += char;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      await sleep(35 + Math.random() * 90);
    }
    element.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }

  if (element.isContentEditable) {
    element.textContent = "";
    for (const char of text) {
      element.textContent += char;
      element.dispatchEvent(new InputEvent("input", { bubbles: true, data: char }));
      await sleep(35 + Math.random() * 90);
    }
  }
}

async function submitOldReddit(textarea, commentText) {
  await humanType(textarea, commentText);
  await sleep(500 + Math.random() * 1500);

  const form = textarea.closest("form");
  const submit = form?.querySelector("button[type='submit'], .save");
  if (!submit) throw new Error("Submit button not found");
  submit.click();
  return true;
}

async function submitNewReddit(textarea, commentText) {
  await humanType(textarea, commentText);
  await sleep(800 + Math.random() * 1800);

  const submit = document.querySelector('button[slot="submit-button"], button[type="submit"]');
  if (submit) {
    submit.click();
    return true;
  }

  textarea.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Enter", code: "Enter", ctrlKey: true, bubbles: true })
  );
  return true;
}

async function postComment(commentText) {
  await humanScroll();

  if (isOldReddit()) {
    if (!hasCommentGateOldReddit()) {
      throw new Error("Comment gate: cannot comment in this subreddit/thread");
    }
    const textarea = document.querySelector("form.usertext textarea[name='text'], form.usertext-edit textarea");
    await submitOldReddit(textarea, commentText);
    return { postId: extractPostId(window.location.href) };
  }

  if (!hasCommentGateNewReddit()) {
    throw new Error("Comment gate: cannot comment in this subreddit/thread");
  }

  const textarea = document.querySelector(
    'textarea[placeholder*="comment" i], textarea[name="body"], div[contenteditable="true"]'
  );
  await submitNewReddit(textarea, commentText);
  return { postId: extractPostId(window.location.href) };
}

async function verifyCommentVisible(commentSnippet) {
  await sleep(4000 + Math.random() * 3000);
  const snippet = commentSnippet.slice(0, 40).toLowerCase();
  const pageText = document.body.innerText.toLowerCase();
  return pageText.includes(snippet);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      if (message.type === "PING") {
        sendResponse({ ok: true, page: window.location.href, ...getSessionStatus() });
        return;
      }

      if (message.type === "SESSION_CHECK") {
        sendResponse({ ok: true, ...getSessionStatus() });
        return;
      }

      if (message.type === "SCAN_LISTING") {
        assertSessionReady();
        await humanScroll();
        const posts = isOldReddit()
          ? scanOldRedditListing(message)
          : scanNewRedditListing(message);
        sendResponse({ ok: true, posts });
        return;
      }

      if (message.type === "GET_POST_CONTEXT") {
        assertSessionReady();
        sendResponse({ ok: true, ...getPostContent() });
        return;
      }

      if (message.type === "CHECK_COMMENT_GATE") {
        assertSessionReady();
        const allowed = isOldReddit() ? hasCommentGateOldReddit() : hasCommentGateNewReddit();
        sendResponse({ ok: true, allowed });
        return;
      }

      if (message.type === "POST_COMMENT") {
        assertSessionReady();
        const result = await postComment(message.comment);
        const visible = await verifyCommentVisible(message.comment);
        sendResponse({ ok: true, ...result, visible });
        return;
      }

      sendResponse({ ok: false, error: "Unknown message type" });
    } catch (error) {
      sendResponse({ ok: false, error: error.message });
    }
  })();

  return true;
});

// Visual indicator when extension is active on page
const badge = document.createElement("div");
badge.id = "rkf-badge";
badge.textContent = "Karma Farmer active";
document.documentElement.appendChild(badge);

chrome.storage.local.get("settings", ({ settings }) => {
  if (!settings?.enabled) badge.style.display = "none";
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.settings?.newValue?.enabled) {
    badge.style.display = "block";
  } else if (changes.settings?.newValue?.enabled === false) {
    badge.style.display = "none";
  }
});
