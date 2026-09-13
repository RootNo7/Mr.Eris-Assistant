import platform
from datetime import datetime
from typing import Dict, Any, Callable
from backend.tools.base import BaseTool
from backend.security.enums import RiskLevel

def get_system_info() -> Dict[str, Any]:
    """Retrieves current local system time, OS platform, and architecture information."""
    return {
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "operating_system": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version()
    }

class SystemInfoTool(BaseTool):
    name = "get_system_info"
    description = "Retrieves current local system time, OS platform, and architecture details."
    risk_level = RiskLevel.T0
    requires_approval = False
    timeout_seconds = 5.0
    permission_scope = "system.info"
    required_permission = "system.control"
    side_effect_level = "none"


    def execute(self, **kwargs) -> Dict[str, Any]:
        return get_system_info()

    def get_schema(self) -> Callable:
        return get_system_info