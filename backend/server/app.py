import os
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import json

from backend.server.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    MemoryResponse,
    ToolsResponse,
    ProviderInfo,
    FactSchema,
    FactCreateRequest,
    FactsResponse,
    OrchestrationRequest,
    OrchestrationResponse,
    OrchestrationStepSchema,
    VoiceProfileSchema,
    VoiceSettingsUpdateSchema,
    VoiceSettingsResponse,
    ApprovalRequestSchema,
    ApprovalListResponse,
    ApprovalActionRequest,
    ApprovalActionResponse,
)
from backend.server.service import ERISEngineService
from backend.server.auth import verify_api_key
from backend.core.version import VERSION
from backend.core.logging.logger import logger
from backend.core.exceptions import ERISError, InvalidPromptError

def create_app(service: Optional[ERISEngineService] = None) -> FastAPI:
    """
    Factory creating FastAPI application for ERIS Web Architecture & Engine Services.
    Allows passing mock or custom engine services during unit tests.
    """
    app = FastAPI(
        title="ERIS Engine API & Web UI",
        version=VERSION,
        description="Backend API service, Long-Term Memory, and Web Interface for Evolutionary Responsive Intelligence System (ERIS)",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Enable CORS for local web interface access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Permits dev access from localhost / Vite / React clients
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Singleton instance of engine service
    engine = service or ERISEngineService()

    @app.get("/api/health", response_model=HealthResponse, tags=["System"])
    def get_health():
        """Retrieve ERIS engine health status and active provider metadata."""
        return engine.get_health()

    @app.get("/api/settings/voice", response_model=VoiceSettingsResponse, dependencies=[Depends(verify_api_key)], tags=["Voice Settings"])
    def get_voice_settings():
        """Retrieve active voice profile, engine capabilities, and available profiles."""
        return engine.get_voice_settings()

    @app.put("/api/settings/voice", response_model=VoiceSettingsResponse, dependencies=[Depends(verify_api_key)], tags=["Voice Settings"])
    def update_voice_settings(request: VoiceSettingsUpdateSchema):
        """Update settings and preferences for the active voice profile."""
        try:
            updates = request.model_dump(exclude_unset=True)
            return engine.update_voice_settings(updates)
        except ValueError as val_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
        except Exception as exc:
            logger.error(f"Error updating voice settings: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred updating voice settings.")

    @app.get("/api/settings/voice/profiles", response_model=list[VoiceProfileSchema], dependencies=[Depends(verify_api_key)], tags=["Voice Settings"])
    def list_voice_profiles():
        """List all available voice profiles."""
        settings = engine.get_voice_settings()
        return settings["available_profiles"]

    @app.post("/api/settings/voice/profiles", response_model=VoiceSettingsResponse, dependencies=[Depends(verify_api_key)], tags=["Voice Settings"])
    def create_or_select_voice_profile(profile: VoiceProfileSchema):
        """Create or select a voice profile by ID."""
        try:
            from backend.voice.models import VoiceProfile
            new_profile = VoiceProfile.from_dict(profile.model_dump())
            if engine.voice_profile_manager.get_profile(new_profile.id) is None:
                engine.voice_profile_manager.create_profile(new_profile)
            engine.voice_profile_manager.set_active_profile(new_profile.id)
            return engine.get_voice_settings()
        except ValueError as val_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
        except Exception as exc:
            logger.error(f"Error managing voice profile: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid voice profile request payload.")


    @app.get("/api/providers", response_model=ProviderInfo, dependencies=[Depends(verify_api_key)], tags=["Providers"])
    def get_providers():
        """Retrieve details on active and supported AI providers."""
        return engine.get_providers_info()

    @app.get("/api/tools", response_model=ToolsResponse, dependencies=[Depends(verify_api_key)], tags=["Tools"])
    def get_tools():
        """List all registered PC and system tools available to ERIS."""
        tools_list = engine.get_tools_info()
        return {
            "tools": tools_list,
            "count": len(tools_list)
        }

    @app.get("/api/memory", response_model=MemoryResponse, dependencies=[Depends(verify_api_key)], tags=["Memory"])
    def get_memory():
        """Retrieve current session conversation memory buffer."""
        history = engine.get_memory()
        return {
            "history": history,
            "count": len(history)
        }

    @app.delete("/api/memory", dependencies=[Depends(verify_api_key)], tags=["Memory"])
    def clear_memory():
        """Wipe conversation memory buffer for the active session."""
        engine.clear_memory()
        return {"status": "ok", "message": "Memory context wiped successfully"}

    @app.get("/api/memory/facts", response_model=FactsResponse, dependencies=[Depends(verify_api_key)], tags=["Long-Term Memory"])
    def get_facts():
        """Retrieve all stored persistent long-term memory facts."""
        facts = engine.get_facts()
        return {"facts": facts, "count": len(facts)}

    @app.post("/api/memory/facts", response_model=FactSchema, dependencies=[Depends(verify_api_key)], tags=["Long-Term Memory"])
    def add_fact(request: FactCreateRequest):
        """Manually store or update a persistent long-term memory fact."""
        return engine.add_fact(key=request.key, value=request.value, category=request.category)

    @app.delete("/api/memory/facts/{key}", dependencies=[Depends(verify_api_key)], tags=["Long-Term Memory"])
    def delete_fact(key: str):
        """Delete a persistent long-term memory fact by key."""
        deleted = engine.delete_fact(key)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Fact with key '{key}' not found.")
        return {"status": "ok", "message": f"Fact '{key}' deleted successfully."}

    @app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)], tags=["Chat"])
    def post_chat(request: ChatRequest):
        """Process user prompt synchronously and return complete assistant response."""
        try:
            result = engine.process_chat(
                prompt=request.prompt,
                clear_history=request.clear_history
            )
            return result
        except InvalidPromptError as val_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
        except ERISError as eris_err:
            logger.error(f"ERIS operational error: {eris_err}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred processing your request.")
        except Exception as e:
            logger.error(f"Unhandled internal server error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An internal server error occurred."
            )

    @app.post("/api/chat/stream", dependencies=[Depends(verify_api_key)], tags=["Chat"])
    def post_chat_stream(request: ChatRequest):
        """Process user prompt and stream response text chunks via Server-Sent Events (SSE)."""
        def event_generator():
            try:
                for chunk in engine.process_chat_stream(
                    prompt=request.prompt,
                    clear_history=request.clear_history
                ):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Unhandled chat stream error: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': 'An internal error occurred processing your request.'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    @app.post("/api/orchestrate", response_model=OrchestrationResponse, dependencies=[Depends(verify_api_key)], tags=["Orchestration"])
    def post_orchestrate(request: OrchestrationRequest):
        """
        Execute a user goal through the controlled ERIS Orchestration Loop.

        The loop runs a structured think → act → observe cycle with configurable
        safety governors (max_steps, max_tool_calls, max_seconds).  Returns a
        complete step-by-step execution trace alongside the final answer.

        All tool calls are routed through the existing CentralToolExecutor
        security pipeline.  Governors cannot be disabled.
        """
        from backend.orchestration.config import OrchestrationConfig
        from backend.core.exceptions import ConfigurationError

        try:
            orch_config = OrchestrationConfig(
                max_steps=request.max_steps or 10,
                max_tool_calls=request.max_tool_calls or 20,
                max_execution_seconds=request.max_seconds or 120.0,
            )
        except ConfigurationError as cfg_err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid orchestration configuration: {cfg_err}"
            )

        task = engine.process_orchestrated_chat(
            goal=request.goal,
            config=orch_config,
            clear_history=request.clear_history,
        )

        task_dict = task.to_dict()
        return OrchestrationResponse(
            task_id=task_dict["task_id"],
            goal=task_dict["goal"],
            status=task_dict["status"],
            step_count=task_dict["step_count"],
            tool_call_count=task_dict["tool_call_count"],
            elapsed_seconds=task_dict["elapsed_seconds"],
            final_answer=task_dict.get("final_answer"),
            error=task_dict.get("error"),
            steps=[
                OrchestrationStepSchema(
                    step_index=s["step_index"],
                    status=s["status"],
                    thought=s["thought"],
                    tool_name=s.get("tool_name"),
                    tool_args=s.get("tool_args"),
                    observation=s.get("observation"),
                    retry_count=s.get("retry_count", 0),
                )
                for s in task_dict["steps"]
            ]
        )

    # ---------------------------------------------------------------------------
    # Approval System Endpoints (v2.9.1)
    # ---------------------------------------------------------------------------

    @app.get("/api/approvals/pending", response_model=ApprovalListResponse, dependencies=[Depends(verify_api_key)], tags=["Approvals"])
    def get_pending_approvals(session_id: Optional[str] = None):
        """List active pending approval requests."""
        approvals = engine.list_pending_approvals(session_id=session_id)
        return {
            "approvals": approvals,
            "count": len(approvals)
        }

    @app.get("/api/approvals/{approval_id}", response_model=ApprovalRequestSchema, dependencies=[Depends(verify_api_key)], tags=["Approvals"])
    def get_approval_by_id(approval_id: str):
        """Retrieve details of a specific approval request."""
        approval = engine.get_approval(approval_id)
        if not approval:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval request '{approval_id}' not found.")
        return approval

    @app.post("/api/approvals/{approval_id}/approve", response_model=ApprovalActionResponse, dependencies=[Depends(verify_api_key)], tags=["Approvals"])
    def approve_approval(approval_id: str, request: Optional[ApprovalActionRequest] = None):
        """Authorize a pending approval request."""
        decided_by = request.decided_by if request else "user"
        try:
            approval = engine.approve_request(approval_id, decided_by=decided_by)
            return {
                "status": "ok",
                "message": f"Approval request '{approval_id}' successfully approved by '{decided_by}'.",
                "approval": approval
            }
        except ValueError as val_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
        except Exception as exc:
            logger.error(f"Error approving request '{approval_id}': {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error approving request.")

    @app.post("/api/approvals/{approval_id}/reject", response_model=ApprovalActionResponse, dependencies=[Depends(verify_api_key)], tags=["Approvals"])
    def reject_approval(approval_id: str, request: Optional[ApprovalActionRequest] = None):
        """Reject a pending approval request."""
        decided_by = request.decided_by if request else "user"
        try:
            approval = engine.reject_request(approval_id, decided_by=decided_by)
            return {
                "status": "ok",
                "message": f"Approval request '{approval_id}' rejected by '{decided_by}'.",
                "approval": approval
            }
        except ValueError as val_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
        except Exception as exc:
            logger.error(f"Error rejecting request '{approval_id}': {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error rejecting request.")

    @app.post("/api/approvals/{approval_id}/cancel", response_model=ApprovalActionResponse, dependencies=[Depends(verify_api_key)], tags=["Approvals"])
    def cancel_approval(approval_id: str, request: Optional[ApprovalActionRequest] = None):
        """Cancel a pending approval request."""
        decided_by = request.decided_by if request else "user"
        try:
            approval = engine.cancel_request(approval_id, decided_by=decided_by)
            return {
                "status": "ok",
                "message": f"Approval request '{approval_id}' cancelled by '{decided_by}'.",
                "approval": approval
            }
        except ValueError as val_err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
        except Exception as exc:
            logger.error(f"Error cancelling request '{approval_id}': {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error cancelling request.")

    # Mount Web UI static assets if apps/web directory exists
    web_dir = os.path.join(os.getcwd(), "apps", "web")
    if os.path.exists(web_dir):
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app

# Default app instance for uvicorn
app = create_app()

