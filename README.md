# slskSticky

A service that monitors Gluetun for VPN port changes and automatically updates slskd's listen port configuration. Inspired by [qSticky](https://github.com/monstermuffin/qSticky).

## Features

- Automatically detects VPN port changes from Gluetun
- Updates slskd's YAML configuration via REST API
- Triggers slskd reconnection to apply new port
- Health monitoring with JSON status file
- Docker support with health checks
- Configurable polling interval
- Supports both Gluetun API key and basic auth

## Requirements

- Gluetun (VPN container with port forwarding)
- slskd (Soulseek daemon)
- Docker and Docker Compose (recommended)

### slskd Configuration

**CRITICAL**: slskd must have `SLSKD_REMOTE_CONFIGURATION=true` set to allow remote YAML configuration updates.

The API key used must have **Administrator** role in slskd's configuration.

## Quick Start

1. Clone this repository:
   ```bash
   git clone https://github.com/dankreek/slskSticky.git
   cd slskSticky
   ```

2. Generate secure API keys:
   ```bash
   # For Gluetun
   openssl rand -base64 32

   # For slskd
   openssl rand -base64 32
   ```

3. Edit `docker-compose.yml` and update the following:
   - Gluetun VPN provider settings
   - `CONTROL_SERVER_API_KEY` (Gluetun)
   - `SLSKD_WEB_AUTHENTICATION_API_KEYS_*` (slskd)
   - Soulseek username and password
   - Volume paths

4. Start the stack:
   ```bash
   docker compose up -d
   ```

5. Check logs:
   ```bash
   docker compose logs -f slsksticky
   ```

## Configuration

All configuration is done via environment variables:

### Gluetun Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `GLUETUN_HOST` | `gluetun` | Gluetun hostname |
| `GLUETUN_PORT` | `8000` | Gluetun API port |
| `GLUETUN_AUTH_TYPE` | `apikey` | Auth type: `apikey` or `basic` |
| `GLUETUN_APIKEY` | - | Gluetun API key |
| `GLUETUN_USERNAME` | - | Gluetun basic auth username |
| `GLUETUN_PASSWORD` | - | Gluetun basic auth password |

### slskd Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SLSKD_HOST` | `slskd` | slskd hostname (use `gluetun` if using network mode) |
| `SLSKD_PORT` | `5030` | slskd API port |
| `SLSKD_APIKEY` | - | slskd API key (Administrator role required) |
| `SLSKD_HTTPS` | `false` | Use HTTPS for slskd |
| `SLSKD_VERIFY_SSL` | `false` | Verify SSL certificates |

### General Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL` | `30` | Polling interval in seconds |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `HEALTH_FILE` | `/app/health/status.json` | Health status file path |

## Health Monitoring

The service writes a health status JSON file that can be used for monitoring:

```bash
docker exec slsksticky cat /app/health/status.json | jq
```

Example output:
```json
{
  "healthy": true,
  "services": {
    "gluetun": {
      "connected": true,
      "port": 12345
    },
    "slskd": {
      "connected": true,
      "port_synced": true
    }
  },
  "uptime": "1:23:45",
  "last_check": "2026-01-27T12:34:56.789",
  "last_port_change": "2026-01-27T11:23:45.678",
  "last_error": null,
  "timestamp": "2026-01-27T12:34:56.789"
}
```

## Development

### Local Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Run locally:
   ```bash
   uv run python src/slsksticky.py
   ```

### Building Docker Image

```bash
docker build -t slsksticky .
```

## How It Works

1. **Poll Gluetun**: Every 30 seconds (configurable), slskSticky queries Gluetun's `/v1/portforward` endpoint
2. **Detect Changes**: If the forwarded port differs from slskd's current port, an update is triggered
3. **Update Configuration**:
   - Fetch slskd's current YAML configuration
   - Parse and update `soulseek.listen_port`
   - Write updated configuration back to slskd
4. **Reconnect**: Trigger slskd to reconnect to the Soulseek network to apply the new port
5. **Health Status**: Update health status file for monitoring

## Troubleshooting

### "Access forbidden" errors

Ensure:
- `SLSKD_REMOTE_CONFIGURATION=true` is set in slskd
- Your API key has Administrator role in slskd's configuration
- The API key is correctly set in both slskd and slskSticky

### Port not updating

Check:
- Gluetun is properly configured with port forwarding enabled
- Gluetun API authentication is correct
- slskd can be reached (check hostname if using network_mode)
- Check logs: `docker compose logs slsksticky`

### Connection issues

If using `network_mode: "service:gluetun"` for slskd:
- Set `SLSKD_HOST=gluetun` (not `slskd`)
- slskd uses gluetun's network stack

## Architecture

```
┌─────────────┐     poll port      ┌─────────────┐
│   Gluetun   │◄───────────────────│ slskSticky  │
│  (VPN/Port) │    /v1/portforward │   (daemon)  │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ update YAML config
                                          │ + reconnect
                                          ▼
                                   ┌─────────────┐
                                   │    slskd    │
                                   │ (Soulseek)  │
                                   └─────────────┘
```

## Credits

- Inspired by [qSticky](https://github.com/monstermuffin/qSticky) by monstermuffin
- Built for [slskd](https://github.com/slskd/slskd)
- Uses [Gluetun](https://github.com/qdm12/gluetun) for VPN management

## License

MIT License - see LICENSE file for details
