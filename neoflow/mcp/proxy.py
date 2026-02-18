"""HTTP proxy for connecting local MCP clients to remote NeoFlow MCP servers.

This proxy allows VS Code (which only supports stdio) to connect to a remote
NeoFlow MCP server running with SSE transport over HTTP.
"""

import asyncio
import json
import logging
import sys
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPHTTPProxy:
    """Proxy that bridges stdio (local) to HTTP/SSE (remote) for MCP protocol."""
    
    def __init__(self, remote_url: str, auth_token: str | None = None):
        """Initialize the HTTP proxy.
        
        Args:
            remote_url: Remote MCP server URL (e.g., http://server:9721)
            auth_token: Optional authentication token
        """
        self.remote_url = remote_url.rstrip('/')
        self.sse_url = f"{self.remote_url}/sse"
        self.messages_url = f"{self.remote_url}/messages"
        self.auth_token = auth_token
        self.client = httpx.AsyncClient(timeout=60.0)
        
    async def forward_to_remote(self, message: dict[str, Any]) -> dict[str, Any]:
        """Forward an MCP message to the remote server via HTTP POST.
        
        Args:
            message: MCP protocol message
            
        Returns:
            Response from remote server
        """
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        try:
            response = await self.client.post(
                self.messages_url,
                json=message,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP request failed: {e}")
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Remote server error: {str(e)}",
                }
            }
    
    async def read_stdin(self) -> dict[str, Any] | None:
        """Read a JSON-RPC message from stdin.
        
        Returns:
            Parsed message or None on EOF
        """
        loop = asyncio.get_event_loop()
        
        # Read a line from stdin
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return None
        
        line = line.strip()
        if not line:
            return None
        
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from stdin: {e}")
            return None
    
    def write_stdout(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to stdout.
        
        Args:
            message: Message to write
        """
        json_str = json.dumps(message)
        sys.stdout.write(json_str + "\n")
        sys.stdout.flush()
    
    async def run(self) -> None:
        """Run the proxy, forwarding between stdin/stdout and HTTP."""
        logger.info(f"Starting MCP HTTP proxy to {self.remote_url}")
        
        try:
            while True:
                # Read message from local client (stdin)
                message = await self.read_stdin()
                if message is None:
                    logger.info("stdin closed, shutting down proxy")
                    break
                
                logger.debug(f"Received from stdin: {message.get('method', 'response')}")
                
                # Forward to remote server
                response = await self.forward_to_remote(message)
                
                logger.debug(f"Received from remote: {response.get('result', response.get('error'))}")
                
                # Send response back to local client (stdout)
                self.write_stdout(response)
        
        except KeyboardInterrupt:
            logger.info("Proxy interrupted by user")
        except Exception as e:
            logger.error(f"Proxy error: {e}", exc_info=True)
        finally:
            await self.client.aclose()


async def run_proxy(remote_url: str, auth_token: str | None = None) -> None:
    """Run the MCP HTTP proxy.
    
    Args:
        remote_url: Remote MCP server URL
        auth_token: Optional authentication token
    """
    proxy = MCPHTTPProxy(remote_url, auth_token)
    await proxy.run()
