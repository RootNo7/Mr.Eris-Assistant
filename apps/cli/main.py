import sys
import os
import time
from backend.core.config.settings import Config
from backend.core.logging.logger import logger
from backend.providers.gemini.provider import GeminiProvider
from backend.ai.memory.buffer import ConversationBuffer
from backend.ai.persona.system import ERIS_SYSTEM_PROMPT
from backend.tools.registry import ToolRegistry
from backend.tools.system_info import SystemInfoTool
from backend.tools.pc_tools import LaunchAppTool, OpenUrlTool, RunPCCommandTool
from backend.tools.file_tools import (
    ListFilesTool,
    SearchFilesTool,
    ReadFileTool,
    WriteFileTool,
    CreateDirectoryTool,
    CopyFileTool,
    MoveFileTool
)

from backend.core.version import VERSION

# Enable ANSI escape codes for older Windows terminals
os.system("") 

# --- UI Formatting Codes (Zero Dependency) ---
class UI:
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_boot_screen():
    """Clears the terminal and prints a clean initialization header."""
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{UI.CYAN}{UI.BOLD}")
    print(" ╔════════════════════════════════════════════════════════╗")
    print(f"║              ERIS SYSTEM ONLINE (v{VERSION})           ║")
    print(" ╚════════════════════════════════════════════════════════╝")
    print(f" {UI.YELLOW}Type 'exit' or 'quit' to terminate. 'clear memory' to wipe context.{UI.RESET}\n")

def main():
    print_boot_screen()

    try:  
        config = Config()  
    except ValueError as e:  
        logger.critical(f"Boot sequence aborted: {e}")
        print(f"{UI.RED}{UI.BOLD}[CRITICAL ERROR] Boot sequence aborted: {e}{UI.RESET}")
        sys.exit(1)  

    # Initialize Tool Engine and register default tools  
    tool_registry = ToolRegistry()  
    tool_registry.register(SystemInfoTool())  
    tool_registry.register(LaunchAppTool())  
    tool_registry.register(OpenUrlTool())  
    tool_registry.register(RunPCCommandTool())  
    tool_registry.register(ListFilesTool())
    tool_registry.register(SearchFilesTool())
    tool_registry.register(ReadFileTool())
    tool_registry.register(WriteFileTool())
    tool_registry.register(CreateDirectoryTool())
    tool_registry.register(CopyFileTool())
    tool_registry.register(MoveFileTool())

    try:
        if config.ACTIVE_PROVIDER == "ollama":
            from backend.providers.ollama.provider import OllamaProvider
            provider = OllamaProvider(
                config=config, 
                system_prompt=ERIS_SYSTEM_PROMPT,
                tool_registry=tool_registry
            )
            engine_display_name = f"Ollama Local ({provider.model_name})"
        elif config.ACTIVE_PROVIDER == "openrouter":
            from backend.providers.openrouter.provider import OpenRouterProvider
            provider = OpenRouterProvider(
                config=config,
                system_prompt=ERIS_SYSTEM_PROMPT,
                tool_registry=tool_registry
            )
            engine_display_name = f"OpenRouter Gateway ({provider.model_name})"
        else:
            from backend.providers.gemini.provider import GeminiProvider
            provider = GeminiProvider(  
                config=config,   
                system_prompt=ERIS_SYSTEM_PROMPT,  
                tool_registry=tool_registry  
            )
            engine_display_name = f"Gemini Cloud ({provider.model_name})"
            
    except Exception as e:  
        logger.critical(f"Failed to initialize AI Provider: {e}")  
        print(f"{UI.RED}{UI.BOLD}[CRITICAL ERROR] Failed to initialize AI Provider: {e}{UI.RESET}")
        sys.exit(1)

    memory_file = os.path.join(os.getcwd(), "backend", "storage", "memory", "session.json")  
    memory = ConversationBuffer(max_history=20, storage_path=memory_file)  

    if memory.get_history():  
        print(f" {UI.GREEN}✓ System Notice: Previous memory context loaded successfully.{UI.RESET}")  

    while True:  
        try:  
            # Colored User Input
            user_input = input(f"\n{UI.BLUE}{UI.BOLD}You: {UI.RESET}").strip()  
              
            if user_input.lower() in ['exit', 'quit']:  
                print(f"\n{UI.YELLOW}ERIS: Shutting down. Memory state saved. Goodbye.{UI.RESET}")  
                break  
              
            if user_input.lower() == 'clear memory':  
                memory.clear()  
                print(f"\n{UI.GREEN}ERIS: Memory buffer cleared.{UI.RESET}")  
                continue  

            # Handle Approval System CLI commands (v2.9.1)
            cmd_lower = user_input.lower()
            if cmd_lower in ('approvals', 'pending', 'list approvals'):
                from backend.security.approval import ApprovalManager
                mgr = ApprovalManager()
                pending = mgr.list_pending()
                if not pending:
                    print(f"\n{UI.GREEN}ERIS: No pending approval requests.{UI.RESET}")
                else:
                    print(f"\n{UI.YELLOW}{UI.BOLD}--- PENDING APPROVAL REQUESTS ({len(pending)}) ---{UI.RESET}")
                    for req in pending:
                        print(f" ID: {req.approval_id} | Tool: {req.tool_name} ({req.risk_level}) | Scope: {req.resource_scope} | Expires in: {req.expires_at - time.time():.0f}s")
                continue

            if cmd_lower.startswith(('approve ', 'reject ', 'cancel ')):
                from backend.security.approval import ApprovalManager, ApprovalDecisionAction
                mgr = ApprovalManager()
                parts = user_input.split()
                action_verb = parts[0].lower()
                target_id = parts[1] if len(parts) > 1 else ""

                if not target_id:
                    print(f"\n{UI.RED}Usage: {action_verb} <approval_id>{UI.RESET}")
                    continue

                try:
                    if action_verb == 'approve':
                        res = mgr.approve(target_id, decided_by="cli_user")
                        print(f"\n{UI.GREEN}ERIS: Approval request '{target_id}' APPROVED.{UI.RESET}")
                    elif action_verb == 'reject':
                        res = mgr.reject(target_id, decided_by="cli_user")
                        print(f"\n{UI.YELLOW}ERIS: Approval request '{target_id}' REJECTED.{UI.RESET}")
                    elif action_verb == 'cancel':
                        res = mgr.cancel(target_id, decided_by="cli_user")
                        print(f"\n{UI.YELLOW}ERIS: Approval request '{target_id}' CANCELLED.{UI.RESET}")
                except Exception as err:
                    print(f"\n{UI.RED}ERIS Approval Error: {err}{UI.RESET}")
                continue

            if not user_input:  
                continue  

            # Colored ERIS Output
            print(f"\n{UI.CYAN}{UI.BOLD}ERIS: {UI.RESET}{UI.CYAN}", end="", flush=True)  
              
            full_response = ""  
            for chunk in provider.generate_response_stream(  
                prompt=user_input,  
                history=memory.get_history()  
            ):  
                print(chunk, end="", flush=True)  
                full_response += chunk  
              
            print(f"{UI.RESET}") # Reset color at the end of the response

            memory.add_user_message(user_input)  
            memory.add_assistant_message(full_response)  

        except KeyboardInterrupt:  
            print(f"\n\n{UI.RED}ERIS: Emergency shutdown. Goodbye.{UI.RESET}")  
            break  
        except Exception as e:  
            logger.error(f"Runtime error: {e}")  
            print(f"\n{UI.RED}{UI.BOLD}ERIS: An unexpected error occurred. Please check the logs.{UI.RESET}")

if __name__ == "__main__":
    main()