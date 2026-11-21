#!/usr/bin/env python3
"""Minimal example demonstrating Trailytics instrumentation."""

import trailytics

# 1. Configure Trailytics to log to a specific project
trailytics.configure(
    project_name="Trailytics Demo",
    url="http://localhost:5173/api/",
)


# 2. Instrument a function with @trailytics.track
@trailytics.track(tags=["demo", "phase2"], metadata={"model": "rule-based-mock"})
def generate_response(prompt: str) -> dict:
    """Generate a mock LLM response."""
    return {
        "prompt": prompt,
        "response": f"Trailytics response: '{prompt}'",
        "tokens": len(prompt.split()),
    }


def main():
    print("Executing tracked function...")
    result = generate_response("Explain machine learning in simple terms")
    print("Function result:", result)

    print("Flushing traces to Trailytics backend...")
    success = trailytics.flush(timeout=10)
    print("Flush status:", success)

    # Inspect the trace data using Trailytics Client
    client = trailytics.Client()
    traces = client.search_traces(project_name="Trailytics Demo", max_results=5)
    print(f"Verified: Found {len(traces)} traces in project 'Trailytics Demo'.")
    if traces:
        print(f"Latest Trace ID: {traces[0].id}, Name: {traces[0].name}")


if __name__ == "__main__":
    main()
