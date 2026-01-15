#!/usr/bin/env python3
"""
Quick test to verify LangSmith tracing is working
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set environment variables for LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "true")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "dv360-agent-system")
os.environ["LANGSMITH_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

print("=" * 60)
print("LangSmith Configuration Test")
print("=" * 60)
print()
print(f"LANGCHAIN_TRACING_V2: {os.environ.get('LANGCHAIN_TRACING_V2')}")
print(f"LANGCHAIN_API_KEY: {os.environ.get('LANGCHAIN_API_KEY')[:20]}...")
print(f"LANGCHAIN_PROJECT: {os.environ.get('LANGCHAIN_PROJECT')}")
print(f"LANGSMITH_ENDPOINT: {os.environ.get('LANGSMITH_ENDPOINT')}")
print()

# Now import LangChain components
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

print("Testing LangSmith tracing...")
print()

# Create LLM
llm = ChatAnthropic(
    model="claude-3-opus-20240229",
    temperature=0.1,
    api_key=os.getenv("ANTHROPIC_API_KEY"),
)

print(f"✓ LLM initialized: {llm.model}")
print()

# Make a simple call (this should create a trace)
print("Sending test message to Claude...")
response = llm.invoke([HumanMessage(content="Say 'LangSmith test successful!' and nothing else.")])

print(f"✓ Response received: {response.content}")
print()

# Try to get the run URL if available
try:
    from langsmith import Client
    client = Client()
    print("✓ LangSmith client connected")
    print(f"  API URL: {client.api_url}")

    # Try to list recent runs
    print()
    print("Fetching recent runs...")
    runs = client.list_runs(
        project_name="dv360-agent-system",
        limit=5
    )

    run_list = list(runs)
    if run_list:
        print(f"✓ Found {len(run_list)} recent runs in project 'dv360-agent-system'")
        print()
        print("Recent runs:")
        for run in run_list[:3]:
            print(f"  - {run.name}: {run.status} ({run.run_type}) - {run.id}")
            if run.url:
                print(f"    URL: {run.url}")
    else:
        print("⚠️  No runs found in project 'dv360-agent-system'")
        print()
        print("Possible issues:")
        print("  1. Project name mismatch")
        print("  2. API key doesn't have access to this project")
        print("  3. Traces haven't synced yet (wait 30 seconds)")

except Exception as e:
    print(f"⚠️  Could not connect to LangSmith: {e}")
    print()
    print("This might mean:")
    print("  1. API key is invalid or expired")
    print("  2. Network connection issue")
    print("  3. Project doesn't exist yet")

print()
print("=" * 60)
print("Check your LangSmith dashboard:")
print("https://smith.langchain.com/")
print()
print("Expected project: 'dv360-agent-system'")
print("=" * 60)
