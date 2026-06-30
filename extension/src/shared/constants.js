export const DEFAULT_SETTINGS = {
  enabled: false,
  subreddits: [
    "CasualConversation",
    "NoStupidQuestions",
    "todayilearned",
    "explainlikeimfive",
    "AskReddit"
  ],
  maxCommentsPerDay: 8,
  maxPerSubredditPerDay: 2,
  minDelayMinutes: 8,
  maxDelayMinutes: 22,
  activeHoursStart: 8,
  activeHoursEnd: 23,
  useOldReddit: true,
  skipNsfw: true,
  warmupMode: true,
  aiProvider: "groq",
  apiKey: "",
  apiModel: "llama-3.3-70b-versatile",
  apiBaseUrl: "",
  commentedPosts: [],
  activityLog: [],
  stats: {
    date: "",
    commentsToday: 0,
    subCounts: {},
    totalComments: 0,
    lastCommentAt: 0,
    consecutiveFailures: 0,
    circuitBreakerUntil: 0
  }
};

export const PROVIDER_PRESETS = {
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1/chat/completions",
    defaultModel: "gpt-4o-mini"
  },
  groq: {
    label: "Groq",
    baseUrl: "https://api.groq.com/openai/v1/chat/completions",
    defaultModel: "llama-3.3-70b-versatile"
  },
  openrouter: {
    label: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1/chat/completions",
    defaultModel: "google/gemini-2.0-flash-001"
  }
};

export const ALARM_NAME = "karma-farm-tick";
export const MAX_LOG_ENTRIES = 100;
export const MAX_COMMENTED_POSTS = 5000;
export const CIRCUIT_BREAKER_FAILURES = 3;
export const CIRCUIT_BREAKER_MINUTES = 120;
