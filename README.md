# gvt-checker

Watches [gebrauchte-veranstaltungstechnik.de](https://www.gebrauchte-veranstaltungstechnik.de) for new
classified ads matching your search terms and notifies you via console, Telegram, webhook (e.g. Discord)
or e-mail.

## Features

- Multiple independent watches, each with its own keyword, sort order and filters
- Filters by include/exclude words, regex and price range
- Alerts on new ads and optionally when an ad disappears (sold/offline)
- Persistent state file so you are not notified twice
- Notifiers: `console`, `telegram`, `webhook`, `email` — enable/disable per environment variable
- Error notifications with repeat suppression
- Runs as a loop, a one-shot check, or in Docker

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp config.example.yaml config.yaml   # then edit it
.venv/bin/python -m gvt_checker check-config
.venv/bin/python -m gvt_checker run
```

Secrets are read from the environment; a `.env` file in the working directory is loaded automatically
(real environment variables take precedence).

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:abc...
TELEGRAM_CHAT_ID=987654321
```

## Commands

| Command | Description |
| --- | --- |
| `run` (default) | Run the periodic check loop |
| `once [--dry-run]` | Run a single check cycle and exit |
| `search KEYWORD [--order ...] [--limit N]` | Ad-hoc search, prints results, ignores state |
| `test-notify` | Send a test notification and exit |
| `check-config` | Validate the config file and exit |

Global options: `-c/--config`, `--env-file`, `--log-level`, `--test-notify`.

## Configuration

See [config.example.yaml](config.example.yaml) for a fully commented example. `${VAR}` and
`${VAR:-default}` placeholders are expanded from environment variables, so no secrets need to live in
the file.

A watch looks like this:

```yaml
watches:
  - name: Moving Heads
    keyword: moving head
    order: dDESC                 # rel | dDESC | dASC | pDESC | pASC | distASC
    notify_on_first_run: false
    notify_on_disappear: true
    filter:
      include_words: [robe, martin, clay paky]
      include_mode: any          # any | all
      exclude_words: [defekt, bastler]
      max_price: 2500
      allow_missing_price: true
```

## Docker

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

The config is resolved in this order:

1. `GVT_CONFIG_YAML` — the whole YAML pasted into an environment variable (handy for Portainer stacks)
2. An existing file at `GVT_CONFIG` (default `/config/config.yaml`, e.g. from a volume)
3. The bundled `config.example.yaml`, copied on first start

State is stored in the `gvt-data` volume (`GVT_STATE_FILE`, default `/data/state.json`).

## License

Non-Commercial Public Use License (NCPUL) v1.3 — see [LICENSE.md](LICENSE.md).
