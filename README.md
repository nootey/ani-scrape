# ani-scrape

A lightweight anime and manga release tracker that monitors AniList and sends Discord notifications when new episodes or chapters are released for your subscribed series.

## Features

- AniList Sync - Automatically sync your WATCHING/READING lists from AniList
- Search & subscribe - Search AniList's database and subscribe to any anime or manga
- Automatic notifications - Get Discord notifications when new episodes/chapters are released
- Lightweight local storage for your subscriptions
- Interactive command-line interface for managing subscriptions

## Configuration

You need to set up a config file `config.yaml` in project root.
An `config.example.yaml` file is provided, all you need to do is input your Discord webhook, 
everything else has reasonable defaults.

You can also enable notifications about errors, that may happen on scrapes, via the `notify_on_error` field in the config.

### How to access Discords webhook URL

- You need access to a Discord server where you are at least admin or higher.
- The Webhook URL can be generated via settings:
  - `Server settings -> Integrations -> Webhooks -> New Webhook`
- Select a channel and name the hook.
- Once you get the URL, paste it in your: `config.yaml` under `webhook_url:`

## Docker

You can run the app locally, but the easiest way is with Docker.
Run the scrapper with this command:

```bash
docker compose -f ./deployment/docker-compose.yml -p aniscrape up
```

**Manual Mode**
```bash
docker exec -it aniscrape python main.py --manual
```

## Local
If you want to run ani-scrape locally for development:

```bash
uv sync
```

Install Playwright browsers

```bash
uv run playwright install chromium
```

Run the app
```bash
python -m main
```