import inspect
from typing import Dict, Any, List, Callable, Optional
from backend.tools.base import BaseTool
from backend.core.logging.logger import logger
from backend.core.exceptions import ToolNotFoundError, ToolExecutionError
from backend.security.executor import CentralToolExecutor
from backend.security.approval import ApprovalGate


def _sanitize_tool_name(name: str) -> str:
    """
    Sanitize tool name for OpenAI-compatible providers.
    OpenAI only allows a-z, A-Z, 0-9, underscores, and dashes in function names.
    """
    return name.replace(".", "_").replace(" ", "_")


def _get_openai_param_name(param_name: str) -> str:
    """Get sanitized parameter name for OpenAI schema."""
    return param_name.replace(".", "_")


class ToolRegistry:
    """
    Central registry managing tool registration, schema generation, and execution.
    Delegates all tool executions through CentralToolExecutor to enforce security policy.
    """

    def __init__(self, executor: Optional[CentralToolExecutor] = None):
        self._tools: Dict[str, BaseTool] = {}
        self._openai_to_internal: Dict[str, str] = {}  # Maps sanitized name -> internal name
        self.executor = executor or CentralToolExecutor()

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance and build name alias mappings."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting tool: {tool.name}")
        self._tools[tool.name] = tool
        
        # Build multi-alias mapping (internal name, sanitized name, function name, openai_name)
        sanitized = _sanitize_tool_name(tool.name)
        self._openai_to_internal[tool.name] = tool.name
        self._openai_to_internal[sanitized] = tool.name
        
        fn = tool.get_schema()
        if hasattr(fn, '__name__'):
            self._openai_to_internal[fn.__name__] = tool.name
            
        openai_name = getattr(tool, 'openai_name', None)
        if openai_name:
            self._openai_to_internal[openai_name] = tool.name
        
        logger.info(f"Tool registered: {tool.name} (Risk: {tool.risk_level}, Scope: {tool.permission_scope})")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by internal name or alias."""
        if name in self._tools:
            return self._tools[name]
        internal_name = self._openai_to_internal.get(name)
        if internal_name:
            return self._tools.get(internal_name)
        return None

    def get_tool_by_openai_name(self, openai_name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by OpenAI-sanitized name or alias."""
        return self.get_tool(openai_name)

    def list_tools(self) -> List[str]:
        """List names of all registered tools (internal ERIS names)."""
        return list(self._tools.keys())

    def get_all_callables(self) -> List[Callable]:
        """Returns raw function callables for SDKs (like Gemini) that support native parsing."""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """
        Returns tool schemas in OpenAI/OpenRouter & Ollama JSON format.
        
        Sanitizes tool names (replaces dots with underscores) for OpenAI compatibility.
        Filters out internal parameters (self, kwargs, _guard, etc.).
        """
        schemas = []
        for tool in self._tools.values():
            fn = tool.get_schema()
            sig = inspect.signature(fn)
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                # Skip internal/hidden parameters
                if param_name in ["self", "kwargs", "_guard"]:
                    continue
                if param_name.startswith("_"):
                    continue
                    
                param_type = "string"
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == float:
                    param_type = "number"
                    
                # Use sanitized parameter name for schema
                schema_param_name = _get_openai_param_name(param_name)
                properties[schema_param_name] = {
                    "type": param_type,
                    "description": f"Parameter '{param_name}' for {tool.name}."
                }
                if param.default == inspect.Parameter.empty:
                    required.append(schema_param_name)

            # Use sanitized tool name for OpenAI compatibility
            openai_name = getattr(tool, 'openai_name', None) or _sanitize_tool_name(tool.name)
            
            schemas.append({
                "type": "function",
                "function": {
                    "name": openai_name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })
        return schemas

    def execute_tool(
        self,
        name: str,
        kwargs: Dict[str, Any],
        approval_gate: Optional[ApprovalGate] = None,
        approval_id: Optional[str] = None,
        principal_id: str = "user",
        session_id: Optional[str] = None
    ) -> str:
        """
        Executes a tool through the Central Security Chokepoint.
        Supports internal name, OpenAI-sanitized name, or schema function name.
        """
        tool = self.get_tool(name)
        if not tool:
            logger.error(f"Tool execution failed: '{name}' not found.")
            return f"Error: Tool '{name}' is not registered."

        return self.executor.execute(
            tool=tool,
            kwargs=kwargs,
            custom_approval_gate=approval_gate,
            approval_id=approval_id,
            principal_id=principal_id,
            session_id=session_id
        )

    def execute_tool_by_openai_name(
        self,
        openai_name: str,
        kwargs: Dict[str, Any],
        approval_gate: Optional[ApprovalGate] = None,
        approval_id: Optional[str] = None,
        principal_id: str = "user",
        session_id: Optional[str] = None
    ) -> str:
        """
        Executes a tool by its OpenAI-sanitized name or alias.
        """
        return self.execute_tool(
            name=openai_name,
            kwargs=kwargs,
            approval_gate=approval_gate,
            approval_id=approval_id,
            principal_id=principal_id,
            session_id=session_id
        )