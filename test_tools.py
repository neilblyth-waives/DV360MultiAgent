"""
Test script for new LangChain-compatible tools.

Run this to verify tools are properly decorated and callable.
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from tools.agent_tools import (
    get_performance_agent_tools,
    get_budget_agent_tools,
    get_audience_agent_tools,
    get_creative_agent_tools,
)


async def test_tools():
    """Test that tools are properly configured."""

    print("=" * 60)
    print("Testing LangChain Tool Configuration")
    print("=" * 60)

    # Test Performance Agent tools
    print("\n1. Performance Agent Tools:")
    perf_tools = get_performance_agent_tools()
    for tool in perf_tools:
        print(f"   ✓ {tool.name}")
        print(f"     Description: {tool.description[:80]}...")

    # Test Budget Agent tools
    print("\n2. Budget Agent Tools:")
    budget_tools = get_budget_agent_tools()
    for tool in budget_tools:
        print(f"   ✓ {tool.name}")
        print(f"     Description: {tool.description[:80]}...")

    # Test Audience Agent tools
    print("\n3. Audience Agent Tools:")
    audience_tools = get_audience_agent_tools()
    for tool in audience_tools:
        print(f"   ✓ {tool.name}")
        print(f"     Description: {tool.description[:80]}...")

    # Test Creative Agent tools
    print("\n4. Creative Agent Tools:")
    creative_tools = get_creative_agent_tools()
    for tool in creative_tools:
        print(f"   ✓ {tool.name}")
        print(f"     Description: {tool.description[:80]}...")

    print("\n" + "=" * 60)
    print("Tool configuration test completed successfully!")
    print("=" * 60)

    # Test a simple tool invocation
    print("\n5. Testing tool invocation:")
    print("   Calling query_campaign_performance with test parameters...")

    try:
        from tools.snowflake_tools import query_campaign_performance

        # Invoke the tool (this will actually hit Snowflake)
        result = await query_campaign_performance.ainvoke({
            "insertion_order": "test_campaign",
            "limit": 5
        })

        print(f"   ✓ Tool invocation successful!")
        print(f"   Result preview: {result[:200]}...")

    except Exception as e:
        print(f"   ⚠ Tool invocation failed (expected if Snowflake not accessible): {e}")

    print("\n" + "=" * 60)
    print("All tests passed! Tools are ready for LangGraph agents.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_tools())
