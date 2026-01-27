# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

- `uv sync` - Install dependencies
- `uv run python src/slsksticky.py` - Run the service locally
- `docker build -t slsksticky .` - Build Docker image
- `docker compose up` - Run full stack

## Architecture

Single-file Python daemon that:
1. Polls Gluetun API for VPN port changes
2. Updates slskd YAML configuration via REST API
3. Triggers slskd reconnect to apply new port

Key classes:
- `Settings` - Pydantic configuration from environment variables
- `GluetunClient` - Gluetun API wrapper
- `SlskdClient` - slskd API wrapper (YAML config + server reconnect)
- `SlskSticky` - Main daemon with async watch loop

## Dependencies

Uses `uv` for project management. All commands should use `uv run` prefix.

## Reference Implementations

- qSticky (Gluetun patterns): `/home/dankreek/Development/code/monstermuffin/qSticky/qsticky.py`
- slskd API: `/home/dankreek/Development/code/slskd/slskd/src/slskd/Core/API/Controllers/`
