# Reddit Karma Farmer

Welcome to Reddit Karma Farmer, a sophisticated tool designed to help you efficiently manage and enhance your Reddit karma points. This application automates the process of engaging with Reddit posts, generating comments that align with popular trends and user sentiments, thereby increasing the likelihood of receiving upvotes.

## Getting Started

To run the karma farmer locally using the terminal, follow these steps:

1. Navigate to the project directory.
2. Run the `app.py` file.

```bash
python app.py
```

To run the farmer with a web interface locally, follow these steps:

1. Navigate to the project directory.
2. Run the `index.py` file.
3. Visit the `/start_bot` route to initiate the karma farmer.
4. Access the `/log` page to view detailed logs.

```bash
python index.py
```
## Web Dashboard

![image](https://github.com/meet447/Reddit-Karma-Bot/assets/51074036/2552eb5c-b2ce-42ec-aa5a-154f11435e16)


To deploy the farmer on hosting services like Render and more, configure the hosting server to execute `web.py`.
Render and hugging face spaces recommended!

## Chrome Extension (Recommended)

For the best karma farming experience with lower ban risk, use the **Chrome extension** in the `extension/` folder. It runs autonomously in your browser with AI-generated comments and human-like typing.

See [extension/README.md](extension/README.md) for install and setup instructions.

## Features

- **Effortless Engagement**: Automatically engage with Reddit posts by generating comments that resonate with the community's interests.
- **User-Friendly Interface**: Access the karma farmer through a web interface for convenient interaction and monitoring.
- **Scalable Deployment**: Deploy the farmer on various hosting platforms to ensure accessibility and scalability.

## Requirements

- Python 3.7 or higher
- PRAW (Python Reddit API Wrapper)
- Fake Useragent
- Flask (for web interface)
- chipling ai (optional, for comment generation)

Your updated `config.py` file looks good! It nicely organizes the configuration parameters for your Reddit bot. 

## Configuration

Ensure to configure the following parameters in the `config.py` file:

- `client_id`: Your Reddit API client ID.
- `client_secret`: Your Reddit API client secret.
- `username`: Your Reddit account username.
- `password`: Your Reddit account password.
- `webhook`: (Optional) Discord webhook URL for logging purposes.
- `discord_webhook`: (Optional) Boolean indicating whether the Discord webhook is enabled.
- `type`: Select the purpose of your bot. You can choose from:
  - `"ai"`: For a bot that generates comments using AI.
  - `"ad"`: For a bot that posts predefined advertisements.
  - `"post"`: For a bot that makes posts based on predefined titles and bodies.
- `all_subreddits`: Set to `True` if you want the bot to post in all subreddits, or `False` to only post in specific subreddits listed below.
- `subreddits`: List of subreddits where the bot will post or comment. If `all_subreddits` is set to `False`, the bot will only interact with these subreddits.
- `posts`: List of dictionaries containing the titles and bodies of the posts to be made by the bot. Used when `type` is set to `"post"`.
- `ads`: List of advertisements or messages to be posted by the bot. Used when `type` is set to `"ad"`.

Ensure that you provide valid values for each parameter before running your bot.

## Usage

1. Configure the `config.py` file with your Reddit account credentials and other settings.
2. Run the application using either the terminal or a web interface.
3. Monitor the logs to track the farmer's activities and engagement.
4. Customize the comment generation method and parameters based on your preferences and requirements.

## Disclaimer

This application is intended for educational and experimental purposes only. Use it responsibly and adhere to Reddit's guidelines and terms of service. Excessive automation and misuse may lead to account suspension or other penalties imposed by Reddit.
