"""Real end-to-end integration test against the running Trailytics deployment."""

import time
import uuid
import pytest
import trailytics
from trailytics import Client, context, flush, track


def test_e2e_real_trace_lifecycle():
    """Verify end-to-end trace generation, transmission, and retrieval."""
    test_id = str(uuid.uuid4())[:8]
    project_name = f"E2E-Phase2-{test_id}"

    # Configure Trailytics
    trailytics.configure(
        project_name=project_name,
        url="http://localhost:5173/api/",
    )

    captured_trace_id = None

    @trailytics.track(
        name="e2e_outer_workflow",
        tags=["e2e", "integration", f"run-{test_id}"],
        metadata={"test_run": test_id},
    )
    def outer_task(prompt: str) -> dict:
        nonlocal captured_trace_id
        # Capture the active trace ID from context
        trace_data = context.get_current_trace_data()
        if trace_data:
            captured_trace_id = trace_data.id

        return inner_task(prompt)

    @trailytics.track(name="e2e_inner_task")
    def inner_task(text: str) -> dict:
        return {"processed": text.upper(), "length": len(text)}

    # Execute the workflow
    output = outer_task("hello trailytics")
    assert output == {"processed": "HELLO TRAILYTICS", "length": 16}
    assert captured_trace_id is not None

    # Flush traces to backend
    flushed = trailytics.flush(timeout=10)
    assert flushed is True

    # Allow ClickHouse ingestion a brief moment if needed
    client = Client(project_name=project_name)

    # Poll with retries up to 10 seconds for the trace to appear in the backend
    trace_record = None
    for _ in range(20):
        try:
            trace_record = client.get_trace_content(id=captured_trace_id)
            if trace_record is not None:
                break
        except Exception:
            pass
        time.sleep(0.5)

    assert trace_record is not None, f"Trace {captured_trace_id} was not found in backend"
    assert trace_record.name == "e2e_outer_workflow"
    assert trace_record.input == {"prompt": "hello trailytics"}
    assert trace_record.output == {"processed": "HELLO TRAILYTICS", "length": 16}
    assert "e2e" in trace_record.tags
    assert trace_record.metadata.get("test_run") == test_id
