# GridVision assistant router

Run the Ollama supervisor from the repository root:

```sh
.venv/bin/python -m ai.govt --query "Show the redistribution plan for 2018-09-24"
.venv/bin/python -m ai.govt --query "What anomalies were found on 2019-05-03?"
```

The supervisor uses `qwen3:8b` by default to classify the request as an anomaly
question, a government-grid question, or a question that needs clarification.
It supplies the model with examples from `ai/anamoly/demo_queries.txt` and
`ai/Govt_interpretion+redistribution_plan/docs/QUERY_EXAMPLES.md`. It then
dispatches the original question to the existing assistant, preserving that
assistant's own data validation and response logic.

Start Ollama and make sure the router model is available. Configure the routing
model with `GRIDVISION_ROUTER_MODEL` (default `qwen3:8b`) and the routing server
with `GRIDVISION_ROUTER_OLLAMA_URL`. If the URL is not set, the router uses the
anomaly assistant's Ollama URL and then `OLLAMA_HOST`.

The anomaly route loads the existing backend application and assistant service,
so the backend's Python dependencies and anomaly dataset/model configuration
must be available. Government queries use the existing government assistant's
default Ollama query and response models.

## Government & Utilities page

The Flask `AssistantService` uses this router for every Government persona
request. Anomaly questions continue through the existing anomaly assistant;
government-grid, demand, and redistribution questions use the existing 2018
assistant. The same router is included in the backend Docker image built by
`automation.py`.

When the government assistant generates an image or CSV, the API returns a
same-origin artifact URL. PNG images are rendered inside the chat message and
CSV files appear as download links. Generated files are served only from the
configured assistant output directory and the container mounts the output and
network state so they persist across restarts.
