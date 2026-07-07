# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os

import google.auth
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as adk_app
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

setup_telemetry()

try:
    _, project_id = google.auth.default()
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
except Exception:
    import logging as _logging
    logger = _logging.getLogger(__name__)
    _logging.warning(
        "Google Cloud credentials not found — Cloud Logging disabled. "
        "Set up Application Default Credentials (ADC) for production use."
    )
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

try:
    google.auth.default()
    otel_to_cloud = True
except Exception:
    otel_to_cloud = False

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=otel_to_cloud,
)
app.title = "vouch"
app.description = "API for interacting with the Agent vouch"


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    if hasattr(logger, "log_struct"):
        logger.log_struct(feedback.model_dump(), severity="INFO")
    else:
        logger.info("Feedback: %s", feedback.model_dump())
    return {"status": "success"}


class RunRequest(BaseModel):
    source_data: dict
    brief: str
    draft_text: str | None = None


@app.post("/api/run")
async def run_workflow_api(req: RunRequest) -> dict:
    """Runs the Vouch workflow end-to-end and returns the final state."""
    runner = InMemoryRunner(app=adk_app)

    state = {
        "source_data": req.source_data,
        "brief": req.brief
    }
    if req.draft_text:
        state["draft_text"] = req.draft_text

    session = await runner.session_service.create_session(
        app_name="app",
        user_id="api_user",
        state=state
    )

    # Run the workflow
    async for _ in runner.run_async(
        user_id="api_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text="run")]),
    ):
        pass

    final_session = await runner.session_service.get_session(
        app_name="app",
        user_id="api_user",
        session_id=session.id
    )

    return final_session.state


@app.get("/", response_class=HTMLResponse)
def get_dashboard() -> HTMLResponse:
    """Serves the interactive web dashboard."""
    template_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "templates", "index.html"
    )
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=200)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Dashboard Template Not Found</h1><p>Please ensure templates/index.html is created.</p>",
            status_code=404
        )


# Main execution
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
