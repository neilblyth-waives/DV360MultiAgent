#!/usr/bin/env python3
"""
Test script for budget risk agent.
"""
import asyncio
import json
from backend.src.agents.budget_risk_agent import budget_risk_agent
from backend.src.schemas.agent import AgentInput


async def test_budget_query():
    """Test budget query."""
    query = "what is the current budget for Quiz for Jan"
    
    print(f"Testing query: {query}\n")
    
    input_data = AgentInput(
        message=query,
        session_id=None,
        user_id="test_user",
        context={}
    )
    
    try:
        output = await budget_risk_agent.process(input_data)
        
        print("=" * 60)
        print("RESPONSE:")
        print("=" * 60)
        print(output.response)
        print("\n" + "=" * 60)
        print("METADATA:")
        print("=" * 60)
        print(f"Agent: {output.agent_name}")
        print(f"Tools Used: {output.tools_used}")
        print(f"Confidence: {output.confidence}")
        print(f"Reasoning: {output.reasoning}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_budget_query())

