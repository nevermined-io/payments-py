"""Convenience wrapper to launch an A2A server wired with Nevermined Payments."""

from __future__ import annotations

import json
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import AgentCard, HttpRequestContext
from payments_py.payments import Payments


class PaymentsA2AServerResult:  # noqa: D101
    def __init__(
        self, app: FastAPI, server: uvicorn.Server, handler: PaymentsRequestHandler
    ) -> None:
        self.app = app
        self.server = server
        self.handler = handler


class PaymentsA2AServer:  # noqa: D101
    @staticmethod
    def start(  # noqa: D401, PLR0913
        *,
        agent_card: AgentCard,
        executor: Any,  # a2a.server.agent_execution.AgentExecutor
        payments_service: Payments,
        port: int = 8080,
        task_store: Any | None = None,
        base_path: str = "/",
        expose_agent_card: bool = True,
        expose_default_routes: bool = True,
        hooks: dict[str, Any] | None = None,
        custom_request_handler: Any | None = None,
        async_execution: bool = False,
        app: FastAPI | None = None,
        **kwargs: Any,
    ) -> PaymentsA2AServerResult:
        """Start a FastAPI A2A server instance (blocking)."""
        app = app or FastAPI()

        # ---------------- normalize agent_card ----------------
        if isinstance(agent_card, dict) and not hasattr(
            agent_card, "supports_authenticated_extended_card"
        ):

            class _Card(dict):
                supports_authenticated_extended_card = False

                def __init__(self, data):
                    super().__init__(data)
                    # Expose top-level properties as attributes
                    for key, value in data.items():
                        # Convert nested dicts to objects with attributes too
                        if isinstance(value, dict) and key == "capabilities":

                            class _Capabilities(dict):
                                def __init__(self, cap_data):
                                    super().__init__(cap_data)
                                    for cap_key, cap_value in cap_data.items():
                                        setattr(self, cap_key, cap_value)

                            setattr(self, key, _Capabilities(value))
                        else:
                            setattr(self, key, value)

            agent_card = _Card(agent_card)  # type: ignore[assignment]

        # ------------------------------------------------------------------
        # Handler instantiation
        # ------------------------------------------------------------------
        # agent_card is already normalized above, no need to do it again

        handler: PaymentsRequestHandler | Any
        if custom_request_handler is not None:
            handler = custom_request_handler
        else:
            handler = PaymentsRequestHandler(
                agent_card=agent_card,
                task_store=task_store or InMemoryTaskStore(),
                agent_executor=executor,
                payments_service=payments_service,
                async_execution=async_execution,
            )

        # Mount JSON-RPC routes
        if expose_default_routes:
            builder = A2AFastAPIApplication(agent_card=agent_card, http_handler=handler)
            rpc_url = base_path if base_path != "/" else "/"
            builder.add_routes_to_app(app, rpc_url=rpc_url)

        # Configure hooks via middleware if provided
        if hooks:
            # Add hooks middleware that intercepts JSON-RPC requests
            @app.middleware("http")  # type: ignore[misc]
            async def hooks_middleware(request, call_next):  # noqa: ANN001, D401
                # Only handle JSON-RPC requests
                if request.method == "POST" and request.url.path.startswith(base_path):
                    # Parse JSON-RPC to get method name
                    body = await request.body()
                    try:
                        rpc_data = json.loads(body)
                        method = rpc_data.get("method", "unknown")

                        # Call beforeRequest hook
                        if "beforeRequest" in hooks:
                            try:
                                await hooks["beforeRequest"](
                                    method, rpc_data.get("params", {}), request
                                )
                            except Exception:
                                pass  # Swallow hook errors

                        # Restore body for downstream processing
                        request._body = body

                        try:
                            response = await call_next(request)

                            # Call afterRequest hook
                            if "afterRequest" in hooks:
                                try:
                                    await hooks["afterRequest"](
                                        method, "result", request
                                    )
                                except Exception:
                                    pass  # Swallow hook errors

                            return response
                        except Exception as e:
                            # Call onError hook
                            if "onError" in hooks:
                                try:
                                    await hooks["onError"](method, e, request)
                                except Exception:
                                    pass  # Swallow hook errors
                            raise
                    except Exception:
                        # If we can't parse JSON, just proceed normally
                        pass

                return await call_next(request)

        # -----------------------------------------------------------------
        # Middleware: extract bearer token, validate credits, store context
        # -----------------------------------------------------------------
        @app.middleware("http")  # type: ignore[misc]
        async def payments_middleware(request, call_next):  # noqa: ANN001, D401
            # Only interested in RPC POSTs under base_path
            if request.method != "POST" or not request.url.path.startswith(base_path):
                return await call_next(request)

            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {"code": -32001, "message": "Missing bearer token."}
                    },
                )
            bearer_token = auth_header[len("Bearer ") :]

            absolute_url = str(request.url)
            validation: Any
            try:
                # Extract agentId from agent_card payment extension
                payment_ext = next(
                    (
                        ext
                        for ext in (
                            agent_card.get("capabilities", {}).get("extensions", [])
                        )
                        if ext.get("uri") == "urn:nevermined:payment"
                    ),
                    None,
                )
                if payment_ext is None:
                    return JSONResponse(
                        status_code=402,
                        content={
                            "error": {
                                "code": -32001,
                                "message": "Payment extension missing.",
                            }
                        },
                    )
                agent_id = payment_ext.get("params", {}).get("agentId")
                if not agent_id:
                    return JSONResponse(
                        status_code=402,
                        content={
                            "error": {"code": -32001, "message": "Agent ID missing."}
                        },
                    )

                validation = await handler.validate_request(
                    agent_id=agent_id,
                    bearer_token=bearer_token,
                    url_requested=absolute_url,
                    http_method_requested=request.method,
                )
            except Exception as exc:  # noqa: BLE001
                return JSONResponse(
                    status_code=402,
                    content={
                        "error": {"code": -32001, "message": f"Validation error: {exc}"}
                    },
                )

            # Parse JSON body early to capture method / messageId / taskId
            body = await request.body()
            try:
                body_json = json.loads(body)
            except Exception:  # noqa: BLE001
                body_json = {}

            method_name = body_json.get("method")
            task_id = body_json.get("params", {}).get("message", {}).get(
                "taskId"
            ) or body_json.get("params", {}).get("taskId")
            message_id = body_json.get("params", {}).get("message", {}).get("messageId")

            ctx = HttpRequestContext(
                bearer_token=bearer_token,
                url_requested=absolute_url,
                http_method_requested=request.method,
                validation=validation,
            )

            if task_id:
                handler.set_http_ctx_for_task(task_id, ctx)
            elif message_id:
                handler.set_http_ctx_for_message(message_id, ctx)

            # ---------------- hooks ----------------
            if hooks and callable(hooks.get("beforeRequest")):
                await hooks["beforeRequest"](
                    method_name, body_json.get("params"), request
                )

            try:
                response = await call_next(request)
                if hooks and callable(hooks.get("afterRequest")):
                    await hooks["afterRequest"](method_name, response, request)
                return response
            except Exception as exc:  # noqa: BLE001
                if hooks and callable(hooks.get("onError")):
                    await hooks["onError"](method_name, exc, request)
                raise

        # Basic .well-known/agent.json endpoint
        if expose_agent_card:
            route_path = (
                f"{base_path.rstrip('/')}/.well-known/agent.json"
                if base_path != "/"
                else "/.well-known/agent.json"
            )

            @app.get(route_path, include_in_schema=False)
            async def get_agent_card() -> Any:  # noqa: D401, ANN201
                return agent_card

        config = uvicorn.Config(app=app, port=port, log_level="info")
        server = uvicorn.Server(config)
        return PaymentsA2AServerResult(app, server, handler)
