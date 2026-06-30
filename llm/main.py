import time
import g4f.Provider
from g4f.client import Client
import g4f

PREFERRED_PROVIDERS = [
    "You",
    "PollinationsAI",
    "OpenaiChat",
    "HuggingChat",
    "HuggingFace",
    "DeepInfra",
    "MetaAI",
    "Groq",
    "Gemini",
    "Cloudflare",
    "Copilot",
    "Cerebras",
    "PuterJS",
]


def get_available_providers():
    providers = []
    for provider_name in PREFERRED_PROVIDERS:
        provider = getattr(g4f.Provider, provider_name, None)
        if provider is not None:
            providers.append(provider)
    return providers


def create_response(post):
    providers = get_available_providers()
    if not providers:
        print("No compatible g4f providers are available.")
        return None

    try:
        client = Client(provider=g4f.Provider.RetryProvider(providers))

        max_retries = 5
        attempt = 0

        while attempt < max_retries:
            try:
                chat_completion = client.chat.completions.create(
                    model=g4f.models.default,
                    messages=[{"role": "user", "content": post}],
                    stream=True
                )

                response = ""
                for completion in chat_completion:
                    data = completion.choices[0].delta.content or ""
                    response += data

                if response.startswith('"') and response.endswith('"'):
                    response = response[1:-1]

                return response.strip() or None

            except Exception as e:
                if "402" in str(e):
                    attempt += 1
                    print(f"Error 402 encountered. Retrying... ({attempt}/{max_retries})")
                    time.sleep(2 ** attempt)
                else:
                    raise e

        print("Max retries reached. Could not process the request.")
        return None

    except Exception as final_error:
        print(f"An unexpected error occurred: {final_error}")
        return None
