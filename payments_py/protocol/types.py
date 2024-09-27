from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

# Enum for AgentExecutionStatus
class AgentExecutionStatus(Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In_Progress"
    NOT_READY = "Not_Ready"
    COMPLETED = "Completed"
    FAILED = "Failed"

# Artifact data class
@dataclass
class Artifact:
    """
    Represents an artifact with a unique identifier and a URL reference.
    """
    artifact_id: str
    url: str

# ExecutionInput data class
@dataclass
class ExecutionInput:
    """
    Represents the input for a task, such as a query and additional parameters or artifacts.
    """
    query: str
    additional_params: Optional[List[Dict[str, str]]] = None
    artifacts: Optional[List[Artifact]] = None

# ExecutionOutput data class
@dataclass
class ExecutionOutput:
    """
    Represents the output of a task or step execution.
    """
    output: Any
    additional_output: Optional[List[Dict[str, Any]]] = None
    artifacts: Optional[List[str]] = None

# ExecutionOptions data class
@dataclass
class ExecutionOptions:
    """
    Represents options for executing a task or step, such as input, status, and output.
    """
    input: ExecutionInput
    status: AgentExecutionStatus
    output: Optional[ExecutionOutput] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    retries: Optional[int] = None

# Step data class
@dataclass
class Step(ExecutionOptions):
    """
    Represents a step in the execution of a task.
    """
    step_id: str
    task_id: str
    is_last: Optional[bool] = False
    name: Optional[str] = None

# Task data class
@dataclass
class Task(ExecutionOptions):
    """
    Represents a task that an agent should execute, composed of multiple steps.
    """
    task_id: str
    steps: List[Step]
    name: Optional[str] = None

# Constants for step names
FIRST_STEP_NAME = 'init'
LAST_STEP_NAME = 'init'
