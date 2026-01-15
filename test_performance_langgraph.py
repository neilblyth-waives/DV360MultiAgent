"""
Test script for LangGraph Performance Agent.

Compares old class-based agent vs new LangGraph agent.
"""
import asyncio
import sys
import os
import time
from uuid import uuid4

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from agents.performance_agent import performance_agent as old_agent
from agents.performance_agent_langgraph import performance_agent_langgraph as new_agent
from schemas.agent import AgentInput


async def test_both_agents():
    """Test both old and new agents with same query."""

    print("=" * 80)
    print("PERFORMANCE AGENT COMPARISON: Class-Based vs LangGraph")
    print("=" * 80)

    # Test query
    test_query = "How is campaign X performing?"
    test_input = AgentInput(
        message=test_query,
        session_id=uuid4(),
        user_id="test_user"
    )

    # Test OLD agent (class-based)
    print("\n" + "=" * 80)
    print("1. OLD AGENT (Class-Based with Hard-Coded Tools)")
    print("=" * 80)

    start = time.time()
    try:
        old_result = await old_agent.invoke(test_input)
        old_duration = time.time() - start

        print(f"\n✓ Execution time: {old_duration:.2f}s")
        print(f"✓ Tools used: {old_result.tools_used}")
        print(f"✓ Confidence: {old_result.confidence}")
        print(f"\nResponse preview:")
        print(old_result.response[:300] + "..." if len(old_result.response) > 300 else old_result.response)

    except Exception as e:
        print(f"\n✗ OLD agent failed: {e}")
        old_duration = None

    # Test NEW agent (LangGraph + ReAct)
    print("\n" + "=" * 80)
    print("2. NEW AGENT (LangGraph with ReAct Tool Selection)")
    print("=" * 80)

    start = time.time()
    try:
        new_result = await new_agent.invoke(test_input)
        new_duration = time.time() - start

        print(f"\n✓ Execution time: {new_duration:.2f}s")
        print(f"✓ Tools used: {new_result.tools_used}")
        print(f"✓ Confidence: {new_result.confidence}")
        print(f"\nResponse preview:")
        print(new_result.response[:300] + "..." if len(new_result.response) > 300 else new_result.response)

    except Exception as e:
        print(f"\n✗ NEW agent failed: {e}")
        import traceback
        traceback.print_exc()
        new_duration = None

    # Comparison
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    if old_duration and new_duration:
        print(f"\nExecution Time:")
        print(f"  Old: {old_duration:.2f}s")
        print(f"  New: {new_duration:.2f}s")
        print(f"  Difference: {new_duration - old_duration:+.2f}s ({(new_duration/old_duration - 1)*100:+.1f}%)")

    print(f"\nArchitecture:")
    print(f"  Old: Python class with hard-coded tool calls")
    print(f"  New: LangGraph StateGraph with ReAct agent")

    print(f"\nTool Selection:")
    print(f"  Old: Hard-coded (always calls get_campaign_performance)")
    print(f"  New: Dynamic (LLM chooses which tools to call)")

    print(f"\nBenefits of New Approach:")
    print(f"  ✓ Dynamic tool selection (LLM decides what data to fetch)")
    print(f"  ✓ Clear state flow through nodes")
    print(f"  ✓ Individual nodes are testable")
    print(f"  ✓ LangSmith shows graph visualization")
    print(f"  ✓ Can add conditional routing easily")

    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_both_agents())
