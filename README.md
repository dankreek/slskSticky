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

### VPN Provider Compatibility

slskSticky only supports VPN providers with native port forwarding in Gluetun:
- Private Internet Access (PIA)
- ProtonVPN
- Perfect Privacy
- PrivateVPN

Ensure your VPN provider is supported before proceeding.

### slskd Configuration

**CRITICAL**: slskd must have `SLSKD_REMOTE_CONFIGURATION=true` set to allow remote YAML configuration updates.

The API key used must have **Administrator** role in slskd's configuration.

### Gluetun Authentication

slskSticky requires authentication to access Gluetun's API endpoints. You can configure this in two ways:

#### Option 1: Inline API Key (Recommended for Simple Setups)

Set the API key directly in Gluetun's environment variables (as shown in the Quick Start):

```yaml
environment:
  - CONTROL_SERVER_API_KEY=your_api_key_here
```

Then configure slskSticky to use the same API key with `GLUETUN_AUTH_TYPE=apikey`.

#### Option 2: External config.toml (Advanced)

Create a `gluetun/config.toml` file with role-based access controls:

**API Key Method:**
```toml
[[roles]]
name = "slskSticky"
routes = ["GET /v1/portforward", "GET /v1/vpn/status"]
auth = "apikey"
apikey = "your_api_key_here"
```

**Basic Auth Method:**
```toml
[[roles]]
name = "slskSticky"
routes = ["GET /v1/portforward", "GET /v1/vpn/status"]
auth = "basic"
username = "myusername"
password = "mypassword"
```

Mount the config in Gluetun:
```yaml
volumes:
  - ./gluetun/config.toml:/gluetun/auth/config.toml
```

And configure Gluetun to enable the control server:
```yaml
environment:
  - VPN_PORT_FORWARDING=on
  - HTTP_CONTROL_SERVER_ADDRESS=:8000
```

## Quick Start

1. Generate secure API keys:
   ```bash
   # For Gluetun
   openssl rand -base64 32

   # For slskd
   openssl rand -base64 32
   ```

2. Create a `docker-compose.yml` file using the example below, updating:
   - Gluetun VPN provider settings (`VPN_SERVICE_PROVIDER`, `OPENVPN_USER`, `OPENVPN_PASSWORD`, `SERVER_REGIONS`)
   - `CONTROL_SERVER_API_KEY` (Gluetun) - use the API key from step 1
   - `SLSKD_WEB_AUTHENTICATION_API_KEYS_*` (slskd) - use the API key from step 1
   - `SLSKD_SLSK_USERNAME` and `SLSKD_SLSK_PASSWORD` - your Soulseek credentials
   - Volume paths (adjust paths for your downloads and incomplete directories)
   - `GLUETUN_APIKEY` and `SLSKD_APIKEY` in slskSticky service

3. Start the stack:
   ```bash
   docker compose up -d
   ```

4. Check logs:
   ```bash
   docker compose logs -f slsksticky
   ```

5. Verify the setup (see Verification section below)

## Complete Docker Compose Example

The included `docker-compose.yml` provides a full stack setup with Gluetun, slskd, and slskSticky:

```yaml
services:
  gluetun:
    image: qmcgaw/gluetun:latest
    container_name: gluetun
    cap_add:
      - NET_ADMIN
    environment:
      - VPN_SERVICE_PROVIDER=private internet access  # Change to your provider
      - VPN_TYPE=openvpn
      - OPENVPN_USER=your_user
      - OPENVPN_PASSWORD=your_password
      - SERVER_REGIONS=your_region
      - VPN_PORT_FORWARDING=on
      - HTTP_CONTROL_SERVER_ADDRESS=:8000
      - HTTP_CONTROL_SERVER_LOG=on
      - CONTROL_SERVER_API_KEY=your_gluetun_api_key_here
    ports:
      - "8000:8000"  # Gluetun control server
      - "5030:5030"  # slskd web UI (via network_mode)
    restart: unless-stopped

  slskd:
    image: slskd/slskd:latest
    container_name: slskd
    network_mode: "service:gluetun"  # Route through Gluetun's VPN
    depends_on:
      - gluetun
    environment:
      - SLSKD_REMOTE_CONFIGURATION=true  # CRITICAL: Enable remote config
      - SLSKD_SLSK_USERNAME=your_soulseek_username
      - SLSKD_SLSK_PASSWORD=your_soulseek_password
      - SLSKD_WEB_AUTHENTICATION_API_KEYS_ADMIN=your_slskd_api_key_here
      - SLSKD_WEB_AUTHENTICATION_API_KEYS_ADMIN_ROLE=Administrator
    volumes:
      - ./slskd:/app
      - ./downloads:/var/slskd/downloads
      - ./incomplete:/var/slskd/incomplete
    restart: unless-stopped

  slsksticky:
    image: ghcr.io/dankreek/slsksticky:latest
    container_name: slsksticky
    depends_on:
      - gluetun
      - slskd
    environment:
      - GLUETUN_HOST=gluetun
      - GLUETUN_PORT=8000
      - GLUETUN_AUTH_TYPE=apikey
      - GLUETUN_APIKEY=your_gluetun_api_key_here  # Match Gluetun's key
      - SLSKD_HOST=gluetun  # Use gluetun because of network_mode
      - SLSKD_PORT=5030
      - SLSKD_APIKEY=your_slskd_api_key_here  # Match slskd's key
      - CHECK_INTERVAL=30
      - LOG_LEVEL=INFO
    volumes:
      - slsksticky-health:/app/health
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "test", "-f", "/app/health/status.json"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  slsksticky-health:
```

**Key Configuration Notes:**
- slskd uses `network_mode: "service:gluetun"` to route all traffic through the VPN
- Because of this, slskSticky must connect to slskd via `SLSKD_HOST=gluetun`
- slskd's web UI is accessible through Gluetun's ports (add `5030:5030` to Gluetun)
- Both API keys must match between services (Gluetun ↔ slskSticky and slskd ↔ slskSticky)

**Image Tags:**
- `ghcr.io/dankreek/slsksticky:latest` - Latest stable release
- `ghcr.io/dankreek/slsksticky:0.1.0` - Pin to specific version (recommended for production)
- `ghcr.io/dankreek/slsksticky:0.1` - Pin to minor version
- `ghcr.io/dankreek/slsksticky:0` - Pin to major version

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

slskSticky maintains a health status file at `/app/health/status.json` containing uptime, last check timestamp, current port, and any error information. The Docker container includes a health check that monitors this file.

Docker will mark the container as unhealthy if:
- slskd becomes unreachable
- Port updates fail repeatedly
- The health status file cannot be written

### Check Health Status

View the detailed health status:

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

Check Docker's health status:

```bash
docker ps --filter name=slsksticky --format "table {{.Names}}\t{{.Status}}"
```

## Development

### Building from Source

If you want to build from source instead of using the published image:

1. Clone the repository:
   ```bash
   git clone https://github.com/dankreek/slskSticky.git
   cd slskSticky
   ```

2. Build the Docker image:
   ```bash
   docker build -t slsksticky .
   ```

3. Update your `docker-compose.yml` to use `build: .` instead of the `image:` directive.

### Local Setup

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Run locally:
   ```bash
   uv run python slsksticky.py
   ```

## How It Works

slskSticky automatically monitors Gluetun for VPN port changes and keeps slskd synchronized:

1. **Poll Gluetun**: Every 30 seconds (configurable), slskSticky queries Gluetun's `/v1/portforward` endpoint
2. **Detect Changes**: If the forwarded port differs from slskd's current port, an update is triggered
3. **Update Configuration**:
   - Fetch slskd's current YAML configuration via REST API
   - Parse and update `soulseek.listen_port`
   - Write updated configuration back to slskd
4. **Reconnect**: Trigger slskd to reconnect to the Soulseek network to apply the new port
5. **Health Status**: Update health status file for monitoring

**Prerequisites for Gluetun:**
- `VPN_PORT_FORWARDING=on` must be enabled
- `HTTP_CONTROL_SERVER_ADDRESS=:8000` to enable the control server
- Authentication configured (API key or basic auth)

## Verification

After starting the stack, verify that everything is working correctly:

### 1. Check Container Status

```bash
docker compose ps
```

All three containers (gluetun, slskd, slsksticky) should be in "Up" state.

### 2. Verify Gluetun Port Forwarding

```bash
# Using API key authentication
curl -H "X-API-Key: your_gluetun_api_key_here" http://localhost:8000/v1/portforward

# Using basic authentication
curl -u username:password http://localhost:8000/v1/portforward
```

Expected response:
```json
{
  "port": 12345
}
```

### 3. Verify Gluetun VPN Status

```bash
# Using API key authentication
curl -H "X-API-Key: your_gluetun_api_key_here" http://localhost:8000/v1/vpn/status

# Using basic authentication
curl -u username:password http://localhost:8000/v1/vpn/status
```

Expected response should show `"status": "running"`.

### 4. Check slskSticky Logs

```bash
docker logs slsksticky
```

Look for messages indicating successful port updates:
```
INFO: Gluetun port changed from None to 12345
INFO: Successfully updated slskd port to 12345
INFO: Triggered slskd reconnect
```

### 5. Check Health Status

```bash
docker exec slsksticky cat /app/health/status.json | jq
```

Should show `"healthy": true` and matching ports for both services.

### 6. Access slskd Web UI

Navigate to `http://localhost:5030` in your browser. Log in with your slskd credentials and verify that the listen port matches the port from Gluetun.

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

### Gluetun authentication errors

If you see authentication errors when connecting to Gluetun:
- Verify the API key or basic auth credentials match between Gluetun and slskSticky
- Test Gluetun API manually using curl (see Verification section)
- Check Gluetun logs: `docker logs gluetun`
- Ensure `HTTP_CONTROL_SERVER_ADDRESS=:8000` is set in Gluetun
- If using config.toml, verify the file is properly mounted at `/gluetun/auth/config.toml`

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
