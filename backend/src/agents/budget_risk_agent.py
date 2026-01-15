"""
Budget Risk Agent - Minimal ReAct Implementation.

Uses ReAct agent to query Snowflake and analyze budget data.
The LLM can construct SQL queries with dates, aggregations, etc. as needed.
"""
import time
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseAgent
from ..tools.agent_tools import get_budget_agent_tools
from ..tools.decision_logger import decision_logger
from ..schemas.agent import AgentOutput, AgentDecisionCreate
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class BudgetRiskAgent(BaseAgent):
    """
    Budget Risk Agent - Minimal ReAct version.
    
    Uses ReAct agent to:
    1. Query Snowflake (can build custom SQL with dates/aggregations)
    2. Analyze budget data
    3. Provide recommendations
    """

    def __init__(self):
        """Initialize Budget Risk Agent."""
        super().__init__(
            agent_name="budget_risk",
            description="Analyzes DV360 budget pacing and risk",
            tools=[],
        )

    def get_system_prompt(self) -> str:
        """Return system prompt."""
        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year
        
        return f"""You are a DV360 Budget Risk Agent.

IMPORTANT: The current date is {current_date} (year {current_year}). All date references should be interpreted relative to {current_year} unless explicitly stated otherwise.

Analyze budget data and provide:
- Budget status and pacing assessment
- Risk identification (over/under pacing, depletion risk)
- Actionable recommendations

IMPORTANT CONTEXT:
- All budgets are for advertiser 'Quiz' only
- Budgets are at MONTHLY level (each row = one monthly budget segment)

PRIMARY TABLE: reports.multi_agent.DV360_BUDGETS_QUIZ

Available columns in DV360_BUDGETS_QUIZ:
- INSERTION_ORDER_ID: Insertion order ID
- IO_NAME: Insertion order name (e.g., "Quiz for Jan")
- IO_STATUS: Insertion order status
- SEGMENT_NUMBER: Monthly segment number
- BUDGET_AMOUNT: Total budget for the monthly segment
- SEGMENT_START_DATE: Start date of monthly segment
- SEGMENT_END_DATE: End date of monthly segment
- DAYS_IN_SEGMENT: Number of days in segment
- AVG_DAILY_BUDGET: Average daily budget for the segment
- SEGMENT_STATUS: Budget segment status

You can query Snowflake data using:
- execute_custom_snowflake_query: Build SQL queries with dates, aggregations, filters as needed
- query_budget_pacing: Pre-built budget pacing queries (returns monthly segments)
- query_campaign_performance: Campaign performance for context (spend/performance data)

When building custom SQL queries:
- PRIMARY: Use reports.multi_agent.DV360_BUDGETS_QUIZ for budget-related queries
  - Filter by INSERTION_ORDER_ID or IO_NAME (supports LIKE '%Quiz%' for partial match)
  - Use SEGMENT_START_DATE and SEGMENT_END_DATE for date filtering
  - Remember: budgets are monthly, so each row is one month's budget
- SECONDARY: Use reports.reporting_revamp.ALL_PERFORMANCE_AGG only if you need spend/performance context
- Use appropriate date ranges based on the user's question (default to current year/month if not specified)
- Add aggregations (SUM, AVG, etc.) as needed
- You can dynamically adapt and use other tables if needed for the specific query

Be data-driven and provide clear, actionable insights."""

    async def process(self, input_data) -> AgentOutput:
        """Process input using ReAct agent."""
        start_time = time.time()
        
        # Get tools (includes execute_custom_snowflake_query)
        tools = get_budget_agent_tools()
        
        # Create ReAct agent
        react_agent = create_react_agent(
            model=self.llm,
            tools=tools
        )
        
        # Run agent with system prompt in initial messages
        result = await react_agent.ainvoke({
            "messages": [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=input_data.message)
            ]
        })
        
        # Extract response from messages
        response_text = self._extract_response(result.get("messages", []))
        
        # Log decision
        execution_time_ms = int((time.time() - start_time) * 1000)
        if input_data.session_id:
            await decision_logger.log_decision(AgentDecisionCreate(
                session_id=input_data.session_id,
                agent_name=self.agent_name,
                decision_type="budget_analysis",
                input_data={"query": input_data.message},
                output_data={"response": response_text},
                tools_used=["snowflake_query", "llm_analysis"],
                reasoning="Budget analysis completed",
                execution_time_ms=execution_time_ms
            ))
        
        return AgentOutput(
            response=response_text,
            agent_name=self.agent_name,
            reasoning="Budget analysis",
            tools_used=["snowflake_query", "llm_analysis"],
            confidence=0.9
        )

    def _extract_response(self, messages) -> str:
        """Extract final response from ReAct agent messages."""
        # Get the last AI message (the final response)
        for msg in reversed(messages):
            if hasattr(msg, 'content') and msg.content and hasattr(msg, 'type'):
                if msg.type == 'ai':
                    return msg.content
        return "Analysis complete"


# Global instance
budget_risk_agent = BudgetRiskAgent()
