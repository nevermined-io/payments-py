# LangSmith Spans Reference

Helpers for emitting Nevermined-flavored payment spans into a LangSmith trace.

When the optional `[langsmith]` extra is installed and a LangSmith run is active in the current context (typically because `LANGSMITH_TRACING=true` is set and the call is inside a traced runnable), the `@requires_payment` decorator automatically uses these helpers to emit dedicated `nvm:verify` and `nvm:settlement` child spans nested under the active tool span.

For non-LangChain code paths (e.g. the FastAPI middleware) the context managers can also be used directly — see the example in `verify_span` / `settlement_span`.

All helpers in this module silently no-op when:

- the `langsmith` package is not installed, or
- no LangSmith run tree is active in the current context.

Failures inside this module never propagate out — observability is best-effort and must not interfere with the payment flow.

::: payments_py.langsmith.spans
    options:
      show_root_heading: true
      show_source: true
      members:
        - verify_span
        - settlement_span
        - build_verify_metadata
        - build_settle_metadata
        - active_run_tree
        - add_metadata
