import os
import sys
import uvicorn
from backend.core.config.settings import Config
from backend.core.logging.logger import logger

class UI:
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_api_boot_screen(host: str, port: int):
    """Prints a clean initialization banner for ERIS API Server."""
    print(f"{UI.CYAN}{UI.BOLD}")
    print(" ╔════════════════════════════════════════════════════════╗")
    print(" ║                                                        ║")
    print(" ║              ERIS API SERVER ONLINE (v2.1.0)           ║")
    print(" ║                                                        ║")
    print(" ╚════════════════════════════════════════════════════════╝")
    print(f" {UI.GREEN}✓ REST API Endpoint: {UI.BOLD}http://{host}:{port}/api/health{UI.RESET}")
    print(f" {UI.GREEN}✓ Swagger API Docs:  {UI.BOLD}http://{host}:{port}/docs{UI.RESET}")
    print(f" {UI.YELLOW}Press Ctrl+C to terminate server.{UI.RESET}\n")

def main():
    try:
        config = Config()
    except ValueError as e:
        logger.critical(f"API Server startup aborted: {e}")
        print(f"{UI.RED}{UI.BOLD}[CRITICAL ERROR] API Server startup aborted: {e}{UI.RESET}")
        sys.exit(1)

    host = os.getenv("ERIS_API_HOST", "127.0.0.1")
    port = int(os.getenv("ERIS_API_PORT", "8000"))

    print_api_boot_screen(host, port)

    uvicorn.run(
        "backend.server.app:app",
        host=host,
        port=port,
        log_level="info",
        reload=False
    )

if __name__ == "__main__":
    main()
