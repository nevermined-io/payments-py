"""
HTTP handlers for MCP endpoints.

This module provides POST, GET, and DELETE handlers for the /mcp endpoint,
implementing the MCP HTTP transport protocol for Python using the
StreamableHTTPServerTransport from the MCP SDK.

Examples:
    >>> from fastapi import FastAPI
    >>> from payments_py.mcp.http import mount_mcp_handlers, create_session_manager
    >>>
    >>> app = FastAPI()
    >>> session_manager = create_session_manager()
    >>> mount_mcp_handlers(app, session_manager)
"""

import asyncio
import contextvars
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from .session_manager import RequestContext, SessionManager

# =============================================================================
# CONTEXT STORAGE
# =============================================================================


# ContextVar to store request context within the async flow
# This allows handlers deep in the call stack to access HTTP headers
request_context_storage: contextvars.ContextVar[Optional[RequestContext]] = (
    contextvars.ContextVar("request_context", default=None)
)


def get_current_request_context() -> Optional[RequestContext]:
    """Get the current request context from ContextVar.

    Returns:
        Request context dict or None if not in a request context.

    Examples:
        >>> context = get_current_request_context()
        >>> if context:
        ...     headers = context["headers"]
    """
    return request_context_storage.get()


# =============================================================================
# HANDLER CONFIGURATION
# =============================================================================


class McpHandlerConfig(Dict[str, Any]):
    """Configuration for MCP handlers.

    Attributes:
        sessionManager: Session manager instance (required).
        requireAuth: Whether to require authentication. Defaults to True.
        log: Logger function (optional).
    """

    pass


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


import re

# Session ID validation pattern (visible ASCII characters 0x21-0x7E)
SESSION_ID_PATTERN = re.compile(r"^[\x21-\x7E]+$")


def _validate_session_id(session_id: Optional[str]) -> bool:
    """Validate a session ID contains only visible ASCII characters.

    Args:
        session_id: Session ID to validate.

    Returns:
        True if valid, False otherwise.
    """
    if session_id is None:
        return True
    return bool(SESSION_ID_PATTERN.fullmatch(session_id))


def _extract_session_id(request: Request) -> Optional[str]:
    """Extract session ID from request headers.

    Args:
        request: FastAPI request object.

    Returns:
        Session ID string or None if not present or invalid.
    """
    header_val = request.headers.get("mcp-session-id")
    if header_val and isinstance(header_val, str):
        # Validate the session ID
        if _validate_session_id(header_val):
            return header_val
        # Invalid session ID - return None to generate a new one
        return None
    return None


def _is_initialize_request(body: Any) -> bool:
    """Check if request is an initialize request.

    Args:
        body: Request body dict.

    Returns:
        True if this is an initialize request.
    """
    return body and isinstance(body, dict) and body.get("method") == "initialize"


# =============================================================================
# STREAMABLE HTTP TRANSPORT MANAGER
# =============================================================================


class TransportManager:
    """Manages StreamableHTTPServerTransport instances per session.

    Each session gets its own transport and a background task running
    the MCP server with that transport's streams.
    """

    def __init__(self, mcp_server: Any, log: Optional[Callable[[str], None]] = None):
        """Initialize the transport manager.

        Args:
            mcp_server: The MCP Server instance.
            log: Optional logging function.
        """
        self._mcp_server = mcp_server
        self._log = log
        self._transports: Dict[str, Any] = {}
        self._server_tasks: Dict[str, asyncio.Task] = {}
        self._ready_events: Dict[str, asyncio.Event] = {}

    async def get_or_create_transport(self, session_id: str) -> Any:
        """Get or create a transport for a session.

        Args:
            session_id: Session identifier.

        Returns:
            StreamableHTTPServerTransport instance.

        Raises:
            ValueError: If session ID is invalid.
        """
        # Validate session ID before using it
        if not _validate_session_id(session_id):
            raise ValueError("Invalid session ID: contains non-ASCII characters")

        if session_id in self._transports:
            # Wait for the server task to be ready
            if session_id in self._ready_events:
                await asyncio.wait_for(
                    self._ready_events[session_id].wait(), timeout=5.0
                )
            return self._transports[session_id]

        from mcp.server.streamable_http import StreamableHTTPServerTransport

        # Create new transport for this session
        # is_json_response_enabled=True returns JSON instead of SSE for single responses
        transport = StreamableHTTPServerTransport(
            mcp_session_id=session_id,
            is_json_response_enabled=True,
        )

        self._transports[session_id] = transport

        # Create event to signal when server is ready
        ready_event = asyncio.Event()
        self._ready_events[session_id] = ready_event

        # Start background task to run the server with this transport
        task = asyncio.create_task(
            self._run_server_for_transport(session_id, transport, ready_event)
        )
        self._server_tasks[session_id] = task

        # Wait for the server to be ready
        await asyncio.wait_for(ready_event.wait(), timeout=5.0)

        if self._log:
            self._log(f"Created transport for session {session_id}")

        return transport

    async def _run_server_for_transport(
        self, session_id: str, transport: Any, ready_event: asyncio.Event
    ) -> None:
        """Run the MCP server with a transport's streams.

        Args:
            session_id: Session identifier.
            transport: StreamableHTTPServerTransport instance.
            ready_event: Event to signal when server is ready.
        """
        try:
            # Get the streams from the transport
            async with transport.connect() as (read_stream, write_stream):
                init_options = self._mcp_server.create_initialization_options()

                if self._log:
                    self._log(
                        f"Transport connected for session {session_id}, starting server"
                    )

                # Signal that we're ready to handle requests AFTER streams are set up
                # The transport's _read_stream_writer is now set
                ready_event.set()

                # Run the server - this will handle messages from the transport
                # Use stateless=True for HTTP mode where each request is independent
                await self._mcp_server.run(
                    read_stream,
                    write_stream,
                    init_options,
                    raise_exceptions=False,
                    stateless=True,  # Important for HTTP transport
                )
        except asyncio.CancelledError:
            if self._log:
                self._log(f"Server task cancelled for session {session_id}")
        except Exception as e:
            if self._log:
                self._log(f"Server error for session {session_id}: {e}")
            import traceback

            traceback.print_exc()
            # Set the event anyway so we don't hang
            ready_event.set()

    def destroy_transport(self, session_id: str) -> bool:
        """Destroy a transport and its server task.

        Args:
            session_id: Session identifier.

        Returns:
            True if transport was destroyed, False if not found.
        """
        if session_id not in self._transports:
            return False

        # Cancel the server task
        if session_id in self._server_tasks:
            task = self._server_tasks.pop(session_id)
            task.cancel()

        # Remove the transport
        transport = self._transports.pop(session_id)

        # Terminate the transport if it has that method
        if hasattr(transport, "terminate"):
            try:
                transport.terminate()
            except Exception:
                pass

        if self._log:
            self._log(f"Destroyed transport for session {session_id}")

        return True

    def destroy_all(self) -> None:
        """Destroy all transports."""
        session_ids = list(self._transports.keys())
        for session_id in session_ids:
            self.destroy_transport(session_id)


# Global transport manager (set during mount)
_transport_manager: Optional[TransportManager] = None


# =============================================================================
# HANDLER CREATORS
# =============================================================================


def create_post_mcp_handler(config: Dict[str, Any]) -> Callable:
    """Create the POST /mcp handler.

    This handler processes MCP JSON-RPC requests using the Python MCP SDK's
    StreamableHTTPServerTransport.

    Args:
        config: Handler configuration dict (McpHandlerConfig).

    Returns:
        FastAPI endpoint handler function.
    """
    session_manager: SessionManager = config["sessionManager"]
    log = config.get("log")

    async def post_mcp_handler(request: Request) -> Response:
        """Handle POST /mcp requests."""
        global _transport_manager

        body = None
        try:
            if log:
                log("POST /mcp")

            # Parse JSON body
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32700,
                            "message": "Parse error: Invalid JSON-RPC request",
                        },
                        "id": None,
                    },
                )

            if not body or not isinstance(body, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32700,
                            "message": "Parse error: Invalid JSON-RPC request",
                        },
                        "id": None,
                    },
                )

            # Get raw header for debugging
            raw_session_id = request.headers.get("mcp-session-id")
            client_session_id = _extract_session_id(request)
            is_init = _is_initialize_request(body)

            if log:
                log(
                    f"POST /mcp - Raw session: {repr(raw_session_id)}, Validated: {repr(client_session_id)}, Is init: {is_init}"
                )

            session_id = client_session_id
            if is_init or not session_id:
                session_id = session_manager.generate_session_id()
                if log:
                    log(f"Created/assigned session: {session_id}")

            # Create request context with HTTP headers
            request_context: RequestContext = {
                "headers": dict(request.headers.items()),
                "method": request.method,
                "url": str(request.url),
                "ip": request.client.host if request.client else None,
            }

            # Store in session manager for later access
            session_manager.set_request_context(session_id, request_context)

            # Set context in ContextVar for access by tool handlers
            request_context_storage.set(request_context)

            # Get the MCP server from session manager
            mcp_server = session_manager._mcp_server
            if not mcp_server:
                return JSONResponse(
                    status_code=500,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "MCP server not configured",
                        },
                        "id": body.get("id"),
                    },
                )

            # Initialize transport manager if needed
            if _transport_manager is None:
                return JSONResponse(
                    status_code=500,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "Transport manager not initialized",
                        },
                        "id": body.get("id"),
                    },
                )

            # Get or create transport for this session
            transport = await _transport_manager.get_or_create_transport(session_id)

            # Build headers list, replacing/adding the session ID with our validated one
            headers_list = []
            session_header_added = False
            for k, v in request.headers.items():
                k_lower = k.lower()
                if k_lower == "mcp-session-id":
                    # Replace with our validated session ID
                    headers_list.append((b"mcp-session-id", session_id.encode()))
                    session_header_added = True
                else:
                    headers_list.append((k.encode(), v.encode()))

            # Add session ID header if not present
            if not session_header_added:
                headers_list.append((b"mcp-session-id", session_id.encode()))

            # Build ASGI scope from FastAPI request
            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": request.method,
                "scheme": request.url.scheme,
                "path": request.url.path,
                "query_string": (
                    request.url.query.encode() if request.url.query else b""
                ),
                "root_path": "",
                "headers": headers_list,
                "server": (request.url.hostname or "localhost", request.url.port or 80),
            }

            # Get request body as bytes
            body_bytes = await request.body()

            # Create ASGI receive function
            body_sent = False

            async def receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {
                        "type": "http.request",
                        "body": body_bytes,
                        "more_body": False,
                    }
                return {"type": "http.disconnect"}

            # Create ASGI send function to capture response
            response_started = False
            response_status = 200
            response_headers: list = []
            response_body = b""

            async def send(message):
                nonlocal response_started, response_status, response_headers, response_body
                if message["type"] == "http.response.start":
                    response_started = True
                    response_status = message.get("status", 200)
                    response_headers = message.get("headers", [])
                elif message["type"] == "http.response.body":
                    response_body += message.get("body", b"")

            # Handle the request through the transport
            await transport.handle_request(scope, receive, send)

            # Build FastAPI response from captured ASGI response
            # Use lowercase keys for consistency and avoid duplicates
            headers_dict = {}
            for k, v in response_headers:
                key = k.decode().lower()
                headers_dict[key] = v.decode()

            # Only add session ID if not already present
            if "mcp-session-id" not in headers_dict:
                headers_dict["mcp-session-id"] = session_id

            return Response(
                content=response_body,
                status_code=response_status,
                headers=headers_dict,
                media_type=headers_dict.get("content-type", "application/json"),
            )

        except Exception as error:
            if log:
                log(f"Error in POST /mcp: {error}")

            error_message = str(error) if error else "Internal server error"
            error_id = body.get("id") if isinstance(body, dict) else None

            return JSONResponse(
                status_code=500,
                content={
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": error_message},
                    "id": error_id,
                },
            )

    return post_mcp_handler


def create_get_mcp_handler(config: Dict[str, Any]) -> Callable:
    """Create the GET /mcp handler (SSE stream).

    This handler supports SSE streaming for MCP clients that prefer it.

    Args:
        config: Handler configuration dict (McpHandlerConfig).

    Returns:
        FastAPI endpoint handler function.
    """
    session_manager: SessionManager = config["sessionManager"]
    log = config.get("log")

    async def get_mcp_handler(request: Request) -> Response:
        """Handle GET /mcp requests (SSE stream)."""
        global _transport_manager

        if log:
            log("GET /mcp (SSE)")

        # Get raw header value for debugging
        raw_session_id = request.headers.get("mcp-session-id")
        client_session_id = _extract_session_id(request)

        if log:
            log(
                f"GET /mcp - Raw session ID: {repr(raw_session_id)}, Validated: {repr(client_session_id)}"
            )

        if not client_session_id:
            if log:
                log(f"GET /mcp - Session ID missing or invalid")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "missing_session",
                    "error_description": f"Mcp-Session-Id header is required for SSE connections. Received: {repr(raw_session_id)}",
                },
            )

        # Create request context
        request_context: RequestContext = {
            "headers": dict(request.headers.items()),
            "method": request.method,
            "url": str(request.url),
            "ip": request.client.host if request.client else None,
        }
        session_manager.set_request_context(client_session_id, request_context)
        request_context_storage.set(request_context)

        if _transport_manager is None:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "server_error",
                    "error_description": "Transport manager not initialized",
                },
            )

        # Get or create transport
        transport = await _transport_manager.get_or_create_transport(client_session_id)

        # Build headers list, replacing/adding the session ID with our validated one
        headers_list = []
        session_header_added = False
        for k, v in request.headers.items():
            k_lower = k.lower()
            if k_lower == "mcp-session-id":
                # Replace with our validated session ID
                headers_list.append((b"mcp-session-id", client_session_id.encode()))
                session_header_added = True
            else:
                headers_list.append((k.encode(), v.encode()))

        # Add session ID header if not present
        if not session_header_added:
            headers_list.append((b"mcp-session-id", client_session_id.encode()))

        # Build ASGI scope
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": request.url.scheme,
            "path": request.url.path,
            "query_string": request.url.query.encode() if request.url.query else b"",
            "root_path": "",
            "headers": headers_list,
            "server": (request.url.hostname or "localhost", request.url.port or 80),
        }

        # For SSE, we need to stream the response
        from starlette.responses import StreamingResponse

        async def stream_generator():
            """Generator that yields SSE events from the transport."""
            response_started = False

            async def receive():
                # GET requests have no body
                return {"type": "http.disconnect"}

            chunks = []

            async def send(message):
                nonlocal response_started
                if message["type"] == "http.response.start":
                    response_started = True
                elif message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        chunks.append(body)

            try:
                await transport.handle_request(scope, receive, send)
                for chunk in chunks:
                    yield chunk
            except Exception as e:
                if log:
                    log(f"SSE stream error: {e}")

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Mcp-Session-Id": client_session_id,
            },
        )

    return get_mcp_handler


def create_delete_mcp_handler(config: Dict[str, Any]) -> Callable:
    """Create the DELETE /mcp handler (session termination).

    Args:
        config: Handler configuration dict (McpHandlerConfig).

    Returns:
        FastAPI endpoint handler function.
    """
    session_manager: SessionManager = config["sessionManager"]
    log = config.get("log")

    async def delete_mcp_handler(request: Request) -> Response:
        """Handle DELETE /mcp requests (session termination)."""
        global _transport_manager

        if log:
            log("DELETE /mcp")

        session_id = _extract_session_id(request)

        if not session_id:
            return JSONResponse(
                status_code=400,
                content={"error": "Mcp-Session-Id header required"},
            )

        # Destroy transport if exists
        if _transport_manager:
            _transport_manager.destroy_transport(session_id)

        if session_manager.destroy_session(session_id):
            if log:
                log(f"Destroyed session: {session_id}")
            return Response(status_code=204)
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found"},
            )

    return delete_mcp_handler


# =============================================================================
# MOUNT HELPERS
# =============================================================================


def mount_mcp_handlers(
    app: FastAPI,
    session_manager: SessionManager,
    require_auth: bool = True,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """Mount all MCP handlers on a FastAPI application.

    Args:
        app: FastAPI application instance.
        session_manager: Session manager instance.
        require_auth: Whether to require authentication. Defaults to True.
        log: Optional logging callback.

    Examples:
        >>> from fastapi import FastAPI
        >>> from payments_py.mcp.http import mount_mcp_handlers, create_session_manager
        >>>
        >>> app = FastAPI()
        >>> session_manager = create_session_manager()
        >>> mount_mcp_handlers(app, session_manager, require_auth=True, log=print)
    """
    global _transport_manager

    # Initialize transport manager with the MCP server
    mcp_server = session_manager._mcp_server
    if mcp_server:
        _transport_manager = TransportManager(mcp_server, log)

    config: Dict[str, Any] = {
        "sessionManager": session_manager,
        "requireAuth": require_auth,
        "log": log,
    }

    post_handler = create_post_mcp_handler(config)
    get_handler = create_get_mcp_handler(config)
    delete_handler = create_delete_mcp_handler(config)

    if require_auth:
        from .oauth_router import create_require_auth_middleware

        auth_dependency = create_require_auth_middleware()

        from fastapi import Depends

        # Mount handlers with auth dependency
        @app.post("/mcp", dependencies=[Depends(auth_dependency)])
        async def post_mcp_with_auth(request: Request) -> Response:
            return await post_handler(request)

        @app.get("/mcp", dependencies=[Depends(auth_dependency)])
        async def get_mcp_with_auth(request: Request) -> Response:
            return await get_handler(request)

        @app.delete("/mcp", dependencies=[Depends(auth_dependency)])
        async def delete_mcp_with_auth(request: Request) -> Response:
            return await delete_handler(request)

    else:
        # Mount handlers without auth
        app.post("/mcp")(post_handler)
        app.get("/mcp")(get_handler)
        app.delete("/mcp")(delete_handler)


def set_transport_manager(manager: TransportManager) -> None:
    """Set the global transport manager (for testing).

    Args:
        manager: TransportManager instance.
    """
    global _transport_manager
    _transport_manager = manager


def get_transport_manager() -> Optional[TransportManager]:
    """Get the global transport manager.

    Returns:
        The global TransportManager instance or None.
    """
    return _transport_manager
