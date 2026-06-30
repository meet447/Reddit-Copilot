import { PROVIDER_PRESETS } from "./constants.js";

function buildPrompt({ title, body, subreddit, topComments, warmupMode }) {
  const context = topComments?.length
    ? `Top comments for tone reference: ${topComments.slice(0, 3).join(" | ")}`
    : "No comments yet — be the first useful reply.";

  const warmupNote = warmupMode
    ? "This is a warmup comment: be friendly, short, and never promotional."
    : "Sound like a real Reddit user. No hashtags, no emojis spam, no 'As an AI'.";

  return `You write authentic Reddit comments that earn upvotes.

Subreddit: r/${subreddit}
Post title: ${title}
Post body: ${body || "(link post / no body)"}
${context}

Rules:
- 1-3 sentences, under 280 characters preferred
- Match the subreddit's casual tone
- Add a genuine thought, question, or personal angle
- Never mention being a bot
- ${warmupNote}

Reply with ONLY the comment text, no quotes.`;
}

export async function generateComment(settings, context) {
  const preset = PROVIDER_PRESETS[settings.aiProvider] || PROVIDER_PRESETS.groq;
  const baseUrl = settings.apiBaseUrl?.trim() || preset.baseUrl;
  const model = settings.apiModel?.trim() || preset.defaultModel;

  if (!settings.apiKey?.trim()) {
    throw new Error("Missing API key");
  }

  const response = await fetch(baseUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${settings.apiKey.trim()}`,
      ...(settings.aiProvider === "openrouter"
        ? { "HTTP-Referer": "https://github.com/meet447/Reddit-Karma-Bot", "X-Title": "Reddit Karma Farmer" }
        : {})
    },
    body: JSON.stringify({
      model,
      temperature: 0.75,
      max_tokens: 180,
      messages: [
        {
          role: "user",
          content: buildPrompt({ ...context, warmupMode: settings.warmupMode })
        }
      ]
    })
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`AI API error ${response.status}: ${text.slice(0, 200)}`);
  }

  const data = await response.json();
  const content = data?.choices?.[0]?.message?.content?.trim();

  if (!content) {
    throw new Error("AI returned empty comment");
  }

  return content.replace(/^["']|["']$/g, "").trim();
}
