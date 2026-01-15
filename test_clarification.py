"""
Test script for clarification routing in Performance Agent.
"""
import asyncio
import sys
import os
from uuid import uuid4

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from agents.performance_agent_langgraph import performance_agent_langgraph
from schemas.agent import AgentInput


async def test_clarification():
    """Test clarification routing with different queries."""

    print("=" * 80)
    print("TESTING CONDITIONAL ROUTING: Ask for Clarification")
    print("=" * 80)

    # Test 1: Vague query (should ask for clarification)
    print("\n" + "-" * 80)
    print("TEST 1: Vague Query (should ask for clarification)")
    print("-" * 80)

    vague_query = "How is it?"
    test_input = AgentInput(
        message=vague_query,
        session_id=uuid4(),
        user_id="test_user"
    )

    print(f"\nQuery: '{vague_query}'")
    print("Expected: Should ask for campaign ID and more details")

    try:
        result = await performance_agent_langgraph.invoke(test_input)

        print(f"\n✓ Response received")
        print(f"✓ Confidence: {result.confidence}")
        print(f"✓ Needs clarification: {'clarification' in result.response.lower() or 'need' in result.response.lower()}")
        print(f"\nResponse:")
        print(result.response)

    except Exception as e:
        print(f"\n✗ Failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Specific query (should proceed with analysis)
    print("\n" + "-" * 80)
    print("TEST 2: Specific Query (should proceed with analysis)")
    print("-" * 80)

    specific_query = "How is campaign ABC123 performing?"
    test_input = AgentInput(
        message=specific_query,
        session_id=uuid4(),
        user_id="test_user"
    )

    print(f"\nQuery: '{specific_query}'")
    print("Expected: Should proceed with full analysis")

    try:
        result = await performance_agent_langgraph.invoke(test_input)

        print(f"\n✓ Response received")
        print(f"✓ Confidence: {result.confidence}")
        print(f"✓ Has metrics: {'metrics' in result.response.lower() or 'performance' in result.response.lower()}")
        print(f"\nResponse preview:")
        print(result.response[:300] + "..." if len(result.response) > 300 else result.response)

    except Exception as e:
        print(f"\n✗ Failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Medium confidence query
    print("\n" + "-" * 80)
    print("TEST 3: Medium Confidence Query")
    print("-" * 80)

    medium_query = "campaign performance"
    test_input = AgentInput(
        message=medium_query,
        session_id=uuid4(),
        user_id="test_user"
    )

    print(f"\nQuery: '{medium_query}'")
    print("Expected: Borderline - might ask for clarification")

    try:
        result = await performance_agent_langgraph.invoke(test_input)

        print(f"\n✓ Response received")
        print(f"✓ Confidence: {result.confidence}")
        print(f"\nResponse preview:")
        print(result.response[:300] + "..." if len(result.response) > 300 else result.response)

    except Exception as e:
        print(f"\n✗ Failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("Tests complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_clarification())
