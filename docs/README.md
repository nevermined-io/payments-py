<!-- markdownlint-disable -->

# API Overview

## Modules

- [`ai_query_api`](./ai_query_api.md#module-ai_query_api)
- [`data_models`](./data_models.md#module-data_models)
- [`environments`](./environments.md#module-environments)
- [`nvm_backend`](./nvm_backend.md#module-nvm_backend)
- [`payments`](./payments.md#module-payments)
- [`utils`](./utils.md#module-utils)

## Classes

- [`ai_query_api.AIQueryApi`](./ai_query_api.md#class-aiqueryapi): Represents the AI Query API.
- [`data_models.AgentExecutionStatus`](./data_models.md#class-agentexecutionstatus): An enumeration.
- [`data_models.Artifact`](./data_models.md#class-artifact): Represents an artifact with a unique identifier and a URL reference.
- [`data_models.BalanceResultDto`](./data_models.md#class-balanceresultdto)
- [`data_models.BurnResultDto`](./data_models.md#class-burnresultdto)
- [`data_models.CreateAssetResultDto`](./data_models.md#class-createassetresultdto)
- [`data_models.DownloadFileResultDto`](./data_models.md#class-downloadfileresultdto)
- [`data_models.ExecutionInput`](./data_models.md#class-executioninput): Represents the input for a task, such as a query and additional parameters or artifacts.
- [`data_models.ExecutionOptions`](./data_models.md#class-executionoptions): Represents options for executing a task or step, such as input, status, and output.
- [`data_models.ExecutionOutput`](./data_models.md#class-executionoutput): Represents the output of a task or step execution.
- [`data_models.MintResultDto`](./data_models.md#class-mintresultdto)
- [`data_models.OrderPlanResultDto`](./data_models.md#class-orderplanresultdto)
- [`data_models.PlanType`](./data_models.md#class-plantype): An enumeration.
- [`data_models.ServiceTokenResultDto`](./data_models.md#class-servicetokenresultdto)
- [`data_models.Step`](./data_models.md#class-step): Represents a step in the execution of a task.
- [`data_models.Task`](./data_models.md#class-task): Represents a task that an agent should execute, composed of multiple steps.
- [`environments.Environment`](./environments.md#class-environment): Enum class to define the different environments
- [`nvm_backend.BackendApiOptions`](./nvm_backend.md#class-backendapioptions)
- [`nvm_backend.NVMBackendApi`](./nvm_backend.md#class-nvmbackendapi)
- [`payments.Payments`](./payments.md#class-payments): A class representing a payment system.

## Functions

- [`utils.snake_to_camel`](./utils.md#function-snake_to_camel): Convert snake_case to camelCase.


---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
