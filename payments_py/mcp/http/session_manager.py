"""
Session manager for MCP transports.

This module handles creation, retrieval, and cleanup of SSE server transport
instances. It also stores request context (headers) per session for authentication.

Examples:
    >>> from payments_py.mcp.http import SessionManager, create_session_manager
    >>> manager = create_session_manager()
    >>> manager.set_mcp_server(mcp_server_instance)
    >>> session_id = manager.generate_session_id()
    >>> transport = await manager.get_or_create_session(session_id)
"""

import uuid
from typing import Any, Callable, Dict, List, Optional

from typing_extensions import TypedDict

# =============================================================================
# TYPES
# =============================================================================


class RequestContext(TypedDict, total=False):
    """Request context stored per session.

    Contains HTTP headers and other request info needed for authentication.

    Attributes:
        headers: HTTP headers dict.
        method: HTTP method (GET, POST, etc.).
        url: Request URL.
        ip: Client IP address.
    """

    headers: Dict[str, Any]
    method: Optional[str]
    url: Optional[str]
    ip: Optional[str]


class SessionManagerConfig(TypedDict, total=False):
    """Configuration for session manager.

    Attributes:
        onSessionCreated: Callback when a session is created.
        onSessionDestroyed: Callback when a session is destroyed.
        log: Logger function.
    """

    onSessionCreated: Optional[Callable[[str], None]]
    onSessionDestroyed: Optional[Callable[[str], None]]
    log: Optional[Callable[[str], None]]


# =============================================================================
# TRANSPORT LAZY LOADING
# =============================================================================


_SSEServerTransport: Optional[Any] = None


async def _get_transport_class() -> Any:
    """Lazily load the MCP SDK SSE server transport.

    Returns:
        SSEServerTransport class from mcp.server.sse module.

    Raises:
        ImportError: If the mcp SDK is not installed.
    """
    global _SSEServerTransport

    if _SSEServerTransport is None:
        try:
            from mcp.server.sse import SseServerTransport

            _SSEServerTransport = SseServerTransport
        except ImportError as error:
            raise ImportError(
                "Failed to load mcp SDK. Make sure it is installed: "
                "pip install mcp or pip install modelcontextprotocol"
            ) from error

    return _SSEServerTransport


# =============================================================================
# SESSION MANAGER
# =============================================================================


class SessionManager:
    """Manages MCP transport sessions.

    This class handles the lifecycle of MCP transport sessions, including
    creation, retrieval, and destruction. It also stores request context
    per session for authentication purposes.

    Attributes:
        _sessions: Dict mapping session IDs to transport instances.
        _request_contexts: Dict mapping session IDs to request contexts.
        _mcp_server: Reference to the MCP server instance.
        _config: Session manager configuration.

    Examples:
        >>> manager = SessionManager()
        >>> manager.set_mcp_server(server)
        >>> session_id = manager.generate_session_id()
        >>> transport = await manager.get_or_create_session(session_id)
        >>> manager.destroy_session(session_id)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the session manager.

        Args:
            config: Optional configuration dict (SessionManagerConfig).
        """
        self._sessions: Dict[str, Any] = {}
        self._request_contexts: Dict[str, RequestContext] = {}
        self._mcp_server: Optional[Any] = None
        self._config: Dict[str, Any] = config or {}

    def set_mcp_server(self, server: Any) -> None:
        """Set the MCP server that transports will connect to.

        Args:
            server: MCP server instance (from mcp.server import Server).
        """
        self._mcp_server = server

    def generate_session_id(self) -> str:
        """Generate a new session ID.

        Returns:
            A new UUID session identifier.

        Examples:
            >>> manager = SessionManager()
            >>> session_id = manager.generate_session_id()
            >>> len(session_id) > 0
            True
        """
        return str(uuid.uuid4())

    def has_session(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: Session identifier.

        Returns:
            True if session exists, False otherwise.
        """
        return session_id in self._sessions

    def get_session(self, session_id: str) -> Optional[Any]:
        """Get an existing session's transport.

        Args:
            session_id: Session identifier.

        Returns:
            Transport instance or None if session doesn't exist.
        """
        return self._sessions.get(session_id)

    def set_request_context(self, session_id: str, context: RequestContext) -> None:
        """Store request context (headers, etc.) for a session.

        This is called when an HTTP request arrives, before dispatching to MCP.

        Args:
            session_id: Session identifier.
            context: Request context dict with headers, method, url, ip.
        """
        self._request_contexts[session_id] = context

    def get_request_context(self, session_id: str) -> Optional[RequestContext]:
        """Get the stored request context for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Request context dict or None if not found.
        """
        return self._request_contexts.get(session_id)

    def get_current_request_context(self) -> Optional[RequestContext]:
        """Get request context from the current/most recent request.

        This is used by paywall handlers to access headers when
        the session ID is not directly available.

        Returns:
            The most recently stored request context, or None.
        """
        # Return the most recent request context if any exist
        if self._request_contexts:
            # Get the most recently added context
            return next(reversed(self._request_contexts.values()), None)
        return None

    async def get_or_create_session(self, session_id: str) -> Any:
        """Get or create a transport for a session.

        If the session exists, returns the existing transport.
        If not, creates a new SSE transport and connects it to the MCP server.

        Args:
            session_id: Session identifier.

        Returns:
            Transport instance.

        Raises:
            RuntimeError: If MCP server is not set.
            ImportError: If mcp SDK is not installed.

        Examples:
            >>> manager = SessionManager()
            >>> manager.set_mcp_server(server)
            >>> transport = await manager.get_or_create_session("session-123")
        """
        # Return existing session if found
        existing_session = self._sessions.get(session_id)
        if existing_session is not None:
            return existing_session

        # Validate MCP server is set
        if not self._mcp_server:
            raise RuntimeError("MCP server not set. Call set_mcp_server() first.")

        # For Python MCP SDK, we don't use the SSE transport for HTTP mode.
        # Instead, we process requests directly via memory streams in mcp_handler.py.
        # Sessions are tracked by ID only for context management.

        # Create a simple session object to track state
        session = {
            "id": session_id,
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

        # Store session
        self._sessions[session_id] = session

        self._log(f"Created new session {session_id}")

        on_session_created = self._config.get("onSessionCreated")
        if on_session_created:
            on_session_created(session_id)

        return session

    def destroy_session(self, session_id: str) -> bool:
        """Destroy a session.

        Args:
            session_id: Session identifier.

        Returns:
            True if session was destroyed, False if session didn't exist.

        Examples:
            >>> manager.destroy_session("session-123")
            True
        """
        if session_id in self._sessions:
            transport = self._sessions.pop(session_id)
            self._request_contexts.pop(session_id, None)

            self._log(f"Destroyed session {session_id}")

            on_session_destroyed = self._config.get("onSessionDestroyed")
            if on_session_destroyed:
                on_session_destroyed(session_id)

            # Try to close the transport if it has a close method
            if transport:
                if hasattr(transport, "close") and callable(transport.close):
                    try:
                        transport.close()
                    except Exception:
                        # Ignore close errors
                        pass
                elif hasattr(transport, "aclose") and callable(transport.aclose):
                    try:
                        import asyncio

                        asyncio.create_task(transport.aclose())
                    except Exception:
                        # Ignore close errors
                        pass

            return True

        return False

    def get_active_sessions(self) -> List[str]:
        """Get all active session IDs.

        Returns:
            List of active session identifiers.

        Examples:
            >>> manager.get_active_sessions()
            ['session-123', 'session-456']
        """
        return list(self._sessions.keys())

    def get_session_count(self) -> int:
        """Get the number of active sessions.

        Returns:
            Number of active sessions.

        Examples:
            >>> manager.get_session_count()
            2
        """
        return len(self._sessions)

    def destroy_all_sessions(self) -> None:
        """Destroy all sessions.

        Examples:
            >>> manager.destroy_all_sessions()
            # All sessions are destroyed
        """
        session_ids = self.get_active_sessions()
        for session_id in session_ids:
            self.destroy_session(session_id)

        self._log(f"Destroyed all {len(session_ids)} sessions")

    def _log(self, message: str) -> None:
        """Internal logging helper (no-op if log not provided).

        Args:
            message: Log message.
        """
        log_fn = self._config.get("log")
        if log_fn:
            log_fn(message)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_session_manager(config: Optional[Dict[str, Any]] = None) -> SessionManager:
    """Create a new session manager.

    Args:
        config: Optional configuration dict (SessionManagerConfig).

    Returns:
        New SessionManager instance.

    Examples:
        >>> manager = create_session_manager({"log": print})
        >>> manager.generate_session_id()
        'e4a2c8b0-...'
    """
    return SessionManager(config)
