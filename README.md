# Infobot Reborn

An LLM-powered conversational AI chatbot, a spiritual successor to the [original Infobot project](https://en.wikipedia.org/wiki/Infobot).

## Overview

Infobot Reborn is a modern chatbot leveraging large language models to provide helpful, informative, and contextually aware responses. Built with Python and designed for serverless deployment on Modal.

This project builds on the legacy of the original Infobot, a Perl-based IRC bot created in the 1990s that could learn and respond to factual questions. Infobot Reborn reimagines this concept with modern AI capabilities while preserving the ability to import legacy Infobot knowledge bases from the [original project](https://infobot.sourceforge.net/).

## Features

- Natural language conversation with contextual memory
- Knowledge base for factual information
- Modular design for easy extension
- Serverless deployment on Modal
- Hosting-agnostic core architecture

## Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for dependency management
- [Modal](https://modal.com/) account (for deployment)
- [ollama](https://ollama.com/) for local LLM inference if you use the default
  `LLM_BASE_URL`

### Installation

```bash
# Clone the repository
git clone https://github.com/kcaswick/infobot-reborn.git
cd infobot-reborn

# Set up environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies from pyproject.toml
uv sync

# For development, include dev dependencies
# uv sync --group dev
```

### Configuration

Copy `.env.example` to `.env` and set required values:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DISCORD_BOT_TOKEN` | Local bot + command registration | — | Bot token for `python src/main.py` and `modal run src/modal.py::register_commands` |
| `DISCORD_CLIENT_ID` | Modal | — | Discord application/client ID |
| `DISCORD_PUBLIC_KEY` | Modal | — | Discord public key for webhook signature verification |
| `LLM_BASE_URL` | No | `http://localhost:11434/v1` | OpenAI-compatible API base URL |
| `LLM_MODEL` | No | `qwen3:1.7b` | Model to request from the LLM server |
| `DATABASE_PATH` | No | `data/infobot.db` locally, `/data/infobot.db` in Modal | SQLite database path |
| `LOG_LEVEL` | No | `INFO` | Logging level |

For local development with the defaults:

```bash
ollama pull qwen3:1.7b
```

### Running Locally

```bash
python src/main.py
```

Before running the local gateway bot:

- Enable the **Message Content Intent** for your bot in the Discord Developer
  Portal under **Privileged Gateway Intents**.
- Set `DISCORD_BOT_TOKEN` in `.env` for the bot application you want to run.

This is required for `python src/main.py` to read server messages. It is not
needed for the Modal webhook deployment path.

### Deploying to Modal

The production deployment uses Discord's Interactions API (HTTP webhooks), not
the local `discord.py` gateway flow.

1. Configure the Modal secret used by `src/modal.py`:

   ```bash
   modal secret create discord-secret \
     DISCORD_BOT_TOKEN=your_bot_token \
     DISCORD_CLIENT_ID=your_client_id \
     DISCORD_PUBLIC_KEY=your_public_key
   ```

   Optional: add `APP_CONFIG_LLM_BASE_URL`, `APP_CONFIG_LLM_MODEL`, and
   `APP_CONFIG_LOG_LEVEL` to the same secret for app-level runtime overrides.

2. Deploy the application:

   ```bash
   modal deploy src/modal.py
   ```

   This returns an Interactions endpoint URL like
   `https://your-app--web-app.modal.run/interactions`.

3. In the Discord Developer Portal, set **Interactions Endpoint URL** to that
   deployed `/interactions` URL.

4. Register slash commands:

   ```bash
   modal run src/modal.py::register_commands
   ```

   This registers `/ask` and `/teach`.

Modal runtime settings used by `src/modal.py` follow deterministic precedence:

1. Secret-backed `APP_CONFIG_*` keys
2. Legacy environment-variable keys
3. Built-in defaults

| Setting | Secret-backed key | Legacy env key | Default |
| --- | --- | --- | --- |
| LLM base URL | `APP_CONFIG_LLM_BASE_URL` | `LLM_BASE_URL` | `http://localhost:11434/v1` |
| LLM model | `APP_CONFIG_LLM_MODEL` | `LLM_MODEL` | `qwen3:1.7b` |
| Log level | `APP_CONFIG_LOG_LEVEL` | `LOG_LEVEL` | `INFO` |

Configuration options:

- Keep using env-only deployments (no migration required).
- Provide `APP_CONFIG_*` keys via Modal secrets for explicit app-level overrides.
  - Current `src/modal.py` mounts `discord-secret`, so add `APP_CONFIG_*` keys
    to that secret for secret-backed precedence.

### Usage

- `/ask <question>` asks the bot a question
- `/teach <factoid>` teaches the bot a factoid in `key is value` form

## Architecture

See [Architecture Documentation](docs/architecture.md) for details on the system design.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
