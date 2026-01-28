import os
import json
import logging
import aiohttp
import asyncio
import signal
import ssl
import yaml
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from aiohttp import ClientTimeout
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings
from typing_extensions import Annotated


class Settings(BaseSettings):
    # Gluetun control server settings
    gluetun_host: Annotated[str, Field(
        description="Gluetun control server hostname"
    )] = "gluetun"

    gluetun_port: Annotated[int, Field(
        description="Gluetun control server port"
    )] = 8000

    gluetun_auth_type: Annotated[str, Field(
        description="Gluetun authentication type (basic/apikey)"
    )] = "apikey"

    gluetun_username: Annotated[str, Field(
        description="Gluetun basic auth username"
    )] = ""

    gluetun_password: Annotated[str, Field(
        description="Gluetun basic auth password"
    )] = ""

    gluetun_apikey: Annotated[str, Field(
        description="Gluetun API key"
    )] = ""

    # slskd settings
    slskd_host: Annotated[str, Field(
        description="slskd server hostname"
    )] = "slskd"

    slskd_port: Annotated[int, Field(
        description="slskd server port"
    )] = 5030

    slskd_apikey: Annotated[str, Field(
        description="slskd API key (Administrator role required)"
    )] = ""

    slskd_https: Annotated[bool, Field(
        description="Use HTTPS for slskd connection"
    )] = False

    slskd_verify_ssl: Annotated[bool, Field(
        description="Verify SSL certificates for slskd"
    )] = False

    check_interval: Annotated[int, Field(
        description="Interval in seconds between port checks"
    )] = 30

    log_level: Annotated[str, Field(
        description="Logging level"
    )] = "INFO"

    health_file: Annotated[str, Field(
        description="Health status file path"
    )] = "/app/health/status.json"

    model_config = ConfigDict(env_prefix="")


@dataclass
class HealthStatus:
    healthy: bool
    last_check: datetime
    last_port_change: Optional[datetime] = None
    last_error: Optional[str] = None
    current_port: Optional[int] = None
    uptime: timedelta = timedelta(seconds=0)


class GluetunClient:
    def __init__(self, settings: Settings, logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self.base_url = f"http://{settings.gluetun_host}:{settings.gluetun_port}"

    async def get_forwarded_port(self) -> Optional[int]:
        """Get the current forwarded port from Gluetun with retry logic."""
        self.logger.debug("Attempting to get forwarded port from Gluetun")

        max_attempts = 3
        base_delay = 2

        for attempt in range(max_attempts):
            try:
                headers = {}
                auth = None

                if self.settings.gluetun_auth_type == "basic":
                    auth = aiohttp.BasicAuth(
                        self.settings.gluetun_username,
                        self.settings.gluetun_password
                    )
                    self.logger.debug("Using basic auth")
                elif self.settings.gluetun_auth_type == "apikey":
                    headers["X-API-Key"] = self.settings.gluetun_apikey
                    self.logger.debug("Using API key auth")
                else:
                    self.logger.error("Invalid auth type specified")
                    return None

                timeout = ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        f"{self.base_url}/v1/portforward",
                        headers=headers,
                        auth=auth
                    ) as response:
                        content = await response.text()
                        self.logger.debug(f"Gluetun API response status: {response.status}, content: {content}")

                        if response.status == 200:
                            try:
                                data = json.loads(content)
                                port = data.get("port")
                                self.logger.debug(f"Retrieved forwarded port: {port}")
                                return port
                            except json.JSONDecodeError as e:
                                self.logger.error(f"Failed to parse JSON response: {e}")
                                return None
                        else:
                            self.logger.error(f"Failed to get port: HTTP {response.status}")
                            return None

            except Exception as e:
                delay = base_delay * (attempt + 1)
                self.logger.warning(f"Connection attempt {attempt + 1} failed: {str(e)}, retrying in {delay}s...")
                await asyncio.sleep(delay)

        self.logger.error("All connection attempts to Gluetun failed")
        return None


class SlskdClient:
    def __init__(self, settings: Settings, logger: logging.Logger):
        self.settings = settings
        self.logger = logger
        self.base_url = f"{'https' if settings.slskd_https else 'http'}://{settings.slskd_host}:{settings.slskd_port}"
        self.session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with API key."""
        return {"X-API-Key": self.settings.slskd_apikey}

    async def _init_session(self) -> None:
        """Initialize aiohttp session with proper SSL settings."""
        if self.session is None:
            self.logger.debug("Initializing new aiohttp session")
            timeout = ClientTimeout(
                total=30,
                connect=10,
                sock_connect=10,
                sock_read=10
            )

            ssl_context = None
            if self.settings.slskd_https:
                if not self.settings.slskd_verify_ssl:
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    self.logger.debug("SSL verification disabled")
                else:
                    self.logger.debug("SSL verification enabled")

            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            self.logger.debug("Session initialized")

    async def get_yaml_config(self) -> Optional[str]:
        """Get the current YAML configuration from slskd."""
        try:
            async with self.session.get(
                f"{self.base_url}/api/v0/options/yaml",
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    yaml_content = await response.json()
                    self.logger.debug("Successfully retrieved YAML config")
                    return yaml_content
                elif response.status == 403:
                    self.logger.error("Access forbidden - ensure SLSKD_REMOTE_CONFIGURATION=true and API key has Administrator role")
                    return None
                else:
                    self.logger.error(f"Failed to get YAML config: {response.status}")
                    return None
        except Exception as e:
            self.logger.error(f"Error getting YAML config: {str(e)}")
            return None

    async def update_yaml_config(self, yaml_content: str) -> bool:
        """Update the YAML configuration in slskd."""
        try:
            async with self.session.post(
                f"{self.base_url}/api/v0/options/yaml",
                headers=self._get_headers(),
                json=yaml_content
            ) as response:
                if response.status == 200:
                    self.logger.debug("Successfully updated YAML config")
                    return True
                elif response.status == 403:
                    self.logger.error("Access forbidden - ensure API key has Administrator role")
                    return False
                elif response.status == 400:
                    error = await response.text()
                    self.logger.error(f"Invalid YAML configuration: {error}")
                    return False
                else:
                    self.logger.error(f"Failed to update YAML config: {response.status}")
                    return False
        except Exception as e:
            self.logger.error(f"Error updating YAML config: {str(e)}")
            return False

    async def reconnect_server(self) -> bool:
        """Trigger slskd to reconnect to the Soulseek network."""
        try:
            async with self.session.put(
                f"{self.base_url}/api/v0/server",
                headers=self._get_headers()
            ) as response:
                if response.status in (200, 205):
                    self.logger.debug("Successfully triggered server reconnect")
                    return True
                else:
                    self.logger.error(f"Failed to trigger reconnect: {response.status}")
                    return False
        except Exception as e:
            self.logger.error(f"Error triggering reconnect: {str(e)}")
            return False

    async def update_listen_port(self, new_port: int) -> bool:
        """Update the listen port in slskd configuration and reconnect."""
        if not isinstance(new_port, int) or new_port < 1024 or new_port > 65535:
            self.logger.error(f"Invalid port value: {new_port}")
            return False

        try:
            # Get current YAML config
            yaml_content = await self.get_yaml_config()
            if yaml_content is None:
                return False

            # Parse and update the YAML
            config = yaml.safe_load(yaml_content)
            if not isinstance(config, dict):
                config = {}

            # Ensure soulseek section exists
            if "soulseek" not in config:
                config["soulseek"] = {}

            # Get current port
            current_port = config.get("soulseek", {}).get("listen_port")

            # Check if port is already set correctly
            if current_port == new_port:
                self.logger.debug(f"Port {new_port} already configured in slskd, skipping update")
                return True

            # Update the port
            config["soulseek"]["listen_port"] = new_port

            # Convert back to YAML
            updated_yaml = yaml.dump(config, default_flow_style=False, sort_keys=False)

            # Update the config
            if not await self.update_yaml_config(updated_yaml):
                return False

            self.logger.info(f"Updated listen port: {current_port} -> {new_port}")

            # Trigger reconnect
            if not await self.reconnect_server():
                self.logger.warning("Port updated but reconnect failed - slskd may need manual reconnection")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error updating listen port: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None


class SlskSticky:
    def __init__(self):
        self.settings = Settings()
        self.logger = self._setup_logger()
        self.current_port: Optional[int] = None
        self.gluetun_client = GluetunClient(self.settings, self.logger)
        self.slskd_client = SlskdClient(self.settings, self.logger)
        self.start_time = datetime.now()
        self.health_status = HealthStatus(healthy=True, last_check=datetime.now())
        self.shutdown_event = asyncio.Event()
        self.first_run = True

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("slsksticky")
        logger.setLevel(getattr(logging, self.settings.log_level.upper()))
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    async def handle_port_change(self) -> None:
        """Check and update port if needed."""
        await self.slskd_client._init_session()

        try:
            # Get port from Gluetun
            new_port = await self.gluetun_client.get_forwarded_port()
            if not new_port:
                self.health_status.healthy = False
                self.health_status.last_error = "Failed to get port from Gluetun"
                return

            self.health_status.healthy = True
            self.health_status.current_port = new_port

            # Check if port needs updating
            if self.current_port != new_port:
                self.logger.info(f"Port change detected: {self.current_port} -> {new_port}")
                if await self.slskd_client.update_listen_port(new_port):
                    self.logger.info(f"Successfully updated slskd port to {new_port}")
                    self.current_port = new_port
                    self.health_status.last_port_change = datetime.now()
                else:
                    self.health_status.healthy = False
                    self.health_status.last_error = "Failed to update port in slskd"
            else:
                if self.first_run:
                    self.logger.info(f"Initial port check: {new_port} already set correctly")
                else:
                    self.logger.debug(f"Port {new_port} already set correctly")

            await self.update_health_file()
            self.first_run = False

        except Exception as e:
            self.health_status.healthy = False
            self.health_status.last_error = str(e)
            self.logger.error(f"Error handling port change: {str(e)}")
            await self.update_health_file()

    async def get_health(self) -> Dict[str, Any]:
        """Get current health status."""
        now = datetime.now()
        return {
            "healthy": self.health_status.healthy,
            "services": {
                "gluetun": {
                    "connected": self.health_status.healthy,
                    "port": self.current_port
                },
                "slskd": {
                    "connected": self.health_status.healthy and self.current_port is not None,
                    "port_synced": self.current_port is not None
                }
            },
            "uptime": str(now - self.start_time),
            "last_check": self.health_status.last_check.isoformat(),
            "last_port_change": self.health_status.last_port_change.isoformat()
                if self.health_status.last_port_change else None,
            "last_error": self.health_status.last_error,
            "timestamp": now.isoformat()
        }

    async def update_health_file(self):
        """Write health status to file."""
        health_data = await self.get_health()
        try:
            health_dir = os.path.dirname(self.settings.health_file)
            os.makedirs(health_dir, exist_ok=True)

            self.logger.debug(f"Writing health status to {self.settings.health_file}")
            with open(self.settings.health_file, 'w') as f:
                json.dump(health_data, f, indent=2)
                self.logger.debug("Successfully wrote health status")
        except Exception as e:
            self.logger.error(f"Failed to write health status: {str(e)}")

    async def watch_port(self) -> None:
        """Main watch loop."""
        self.logger.info("Starting slskSticky port manager...")

        while not self.shutdown_event.is_set():
            try:
                self.health_status.last_check = datetime.now()
                await self.handle_port_change()
                await asyncio.sleep(self.settings.check_interval)
            except Exception as e:
                self.logger.error(f"Watch error: {str(e)}")
                self.health_status.healthy = False
                self.health_status.last_error = str(e)
                await asyncio.sleep(5)

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self.slskd_client.close()
        self.logger.debug("Closed slskd client")
        try:
            if os.path.exists(self.settings.health_file):
                os.remove(self.settings.health_file)
        except Exception as e:
            self.logger.error(f"Failed to remove health file: {str(e)}")

    def setup_signal_handlers(self):
        """Setup handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self.shutdown())
            )

    async def shutdown(self):
        """Graceful shutdown."""
        self.logger.info("Starting graceful shutdown...")
        self.shutdown_event.set()
        await self.slskd_client.close()
        self.logger.info("Shutdown complete")


async def main() -> None:
    manager = SlskSticky()
    try:
        manager.setup_signal_handlers()
        tasks = [
            asyncio.create_task(manager.watch_port())
        ]
        await manager.shutdown_event.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await manager.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
