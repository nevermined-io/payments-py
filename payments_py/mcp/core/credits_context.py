"""
Credits context provider for MCP paywall.
"""

from typing import Any, Dict


class CreditsContextProvider:
    """
    Resolve credits from a fixed value or a callable receiving contextual info.
    """

    def resolve(
        self,
        credits_option: Any,
        args: Any,
        result: Any,
        auth_result: Dict[str, Any],
    ) -> int:
        """Resolve the number of credits to redeem for a request.

        The function accepts either a fixed integer or a callable that will
        receive a context dictionary and return an integer.

        Args:
            credits_option: Fixed integer or callable to compute credits.
            args: Handler arguments (tools/prompts) or variables (resources).
            result: Handler result value.
            auth_result: Authentication metadata including token and logicalUrl.

        Returns:
            The number of credits to redeem (defaults to 1 when not provided).
        """
        if isinstance(credits_option, int):
            return int(credits_option)
        if callable(credits_option):
            ctx = {
                "args": args,
                "result": result,
                "request": {
                    "authHeader": f"Bearer {auth_result.get('token', '')}",
                    "logicalUrl": auth_result.get("logicalUrl", ""),
                    "toolName": self._extract_tool_name_from_url(
                        auth_result.get("logicalUrl", "")
                    ),
                },
            }
            value = credits_option(ctx)  # type: ignore[misc]
            return int(value)
        return 1

    def _extract_tool_name_from_url(self, logical_url: str) -> str:
        """Extract the tool name from a logical MCP URL.

        Args:
            logical_url: Logical MCP URL such as ``mcp://server/tools/name?...``.

        Returns:
            The last path segment or "tool" as a fallback.
        """
        try:
            from urllib.parse import urlparse

            path_parts = (urlparse(logical_url).path or "/").split("/")
            return path_parts[-1] or "tool"
        except Exception:
            return "tool"
