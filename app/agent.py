import os
import google.auth
from google.adk.apps import App
from google.adk.workflow import Workflow

from app.draft_node import draft_node
from app.extract_node import extract_node
from app.verify_node import verify_node
from app.output_node import output_node

# Graceful authentication fallback to Gemini developer API key
try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
except Exception:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

# Define the sequential 4-node ADK 2.0 Workflow graph
root_agent = Workflow(
    name="vouch",
    edges=[
        ('START', draft_node),
        (draft_node, extract_node),
        (extract_node, verify_node),
        (verify_node, output_node),
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
