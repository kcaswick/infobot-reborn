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

- `DISCORD_BOT_TOKEN` is required to run the local Discord bot and to register
  slash commands in Modal (`modal run src/modal.py::register_commands`).
- `DISCORD_CLIENT_ID` and `DISCORD_PUBLIC_KEY` are required for Modal deployments
  (webhook verification + command registration).
- Optional: `LLM_BASE_URL`, `LLM_MODEL`, `DATABASE_PATH`, `LOG_LEVEL`.

### Running Locally

```bash
python src/main.py
```

### Deploying to Modal

```bash
modal deploy src/modal.py
```

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

## Architecture

See [Architecture Documentation](docs/architecture.md) for details on the system design.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
