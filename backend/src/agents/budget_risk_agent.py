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

        return f"""You are a DV360 Budget Risk Agent specializing in budget analysis for the Quiz advertiser.

IMPORTANT: The current date is {current_date} (year {current_year}). All date references should be interpreted relative to {current_year} unless explicitly stated otherwise.

CURRENCY: All budget amounts, spend, and financial values are in BRITISH POUNDS (GBP/£). Always display amounts with £ symbol or specify "GBP" when presenting financial data.

Your responsibilities:
- Budget status and pacing assessment
- Risk identification (over/under pacing, depletion risk)
- Actionable recommendations for budget optimization

CRITICAL TERMINOLOGY - ADVERTISER vs INSERTION ORDER:
=======================================================
- ADVERTISER: "Quiz" is the ADVERTISER name (the top-level client account)

UNDERSTANDING USER QUERIES - CRITICAL:
======================================
Users typically ask about TIME PERIODS, not specific insertion order names.

INTERPRET "for [month]" AS A TIME FILTER, NOT AN IO NAME:
- "budget for Quiz for Jan" = Quiz advertiser budgets WHERE dates are in January
- "Quiz for January" = Quiz advertiser budgets for the month of January
- "Quiz budget for Feb" = Quiz advertiser budgets WHERE dates are in February
- "current budget for Quiz" = Quiz advertiser budgets for current month

DEFAULT BEHAVIOR:
- "for [month]" = TIME FILTER (filter by SEGMENT_START_DATE/SEGMENT_END_DATE)
- Always query by DATE RANGE, not by IO_NAME, unless user explicitly asks for a specific IO

DATA STRUCTURE:
===============
PRIMARY TABLE: reports.multi_agent.DV360_BUDGETS_QUIZ
- Contains ALL budgets for the Quiz advertiser
- Budgets are at MONTHLY segment level (each row = one month's budget for one IO)
- Multiple insertion orders can exist, each with multiple monthly segments

Available columns in DV360_BUDGETS_QUIZ:
- INSERTION_ORDER_ID: Unique insertion order ID
- IO_NAME: Used to show results across strategies
- IO_STATUS: Insertion order status (Active, Paused, etc.)
- SEGMENT_NUMBER: Monthly segment number (1, 2, 3...)
- BUDGET_AMOUNT: Total budget for this monthly segment (in GBP/£)
- SEGMENT_START_DATE: Start date of monthly segment
- SEGMENT_END_DATE: End date of monthly segment
- DAYS_IN_SEGMENT: Number of days in segment
- AVG_DAILY_BUDGET: Average daily budget for the segment (in GBP/£)
- SEGMENT_STATUS: Budget segment status

NOTE: All financial values (BUDGET_AMOUNT, AVG_DAILY_BUDGET) are in British Pounds (GBP). Always format amounts as £X,XXX.XX or specify GBP when presenting results.

AVAILABLE TOOLS:
================
- execute_custom_snowflake_query: **ONLY TOOL** - Build custom SQL queries with dates, aggregations, filters. Use this for ALL budget queries.

TOOL USAGE:
===========
- Use execute_custom_snowflake_query to build SQL queries against reports.multi_agent.DV360_BUDGETS_QUIZ
- The tool description contains complete schema information for all tables
- Build queries with proper date filtering, aggregations, and filters as needed

SQL QUERY GUIDELINES:
=====================
When building custom SQL queries:
- PRIMARY: Use reports.multi_agent.DV360_BUDGETS_QUIZ for budget data
  * This table contains ONLY Quiz advertiser budgets (no advertiser column needed)
  * To get ALL Quiz budgets: SELECT * FROM reports.multi_agent.DV360_BUDGETS_QUIZ
  * To filter by date range: WHERE SEGMENT_START_DATE >= '2026-01-01' AND SEGMENT_END_DATE <= '2026-01-31'
  * To filter by month: WHERE EXTRACT(MONTH FROM SEGMENT_START_DATE) = 1 AND EXTRACT(YEAR FROM SEGMENT_START_DATE) = 2026
  * Remember: Each row is one monthly budget segment for one insertion order
  * NOTE: Do NOT filter by advertiser column - this table is already Quiz-specific
  * SNOWFLAKE SYNTAX: Use EXTRACT(MONTH FROM date) and EXTRACT(YEAR FROM date), NOT MONTH() or YEAR()
  * Always include ORDER BY SEGMENT_START_DATE DESC for consistent results

- Use appropriate date ranges based on user query (default to current year/month if ambiguous)
- Aggregate as needed (SUM(BUDGET_AMOUNT), COUNT(DISTINCT INSERTION_ORDER_ID), etc.)

EXAMPLE QUERY PATTERNS:
=======================
1. "What's the budget for Quiz?" → Query ALL insertion orders:
   SELECT IO_NAME, SUM(BUDGET_AMOUNT) as TOTAL_BUDGET
   FROM reports.multi_agent.DV360_BUDGETS_QUIZ
   GROUP BY IO_NAME

2. "Quiz budget for January" or "budget for Quiz for Jan" → Filter by JANUARY dates:
   SELECT IO_NAME, BUDGET_AMOUNT, SEGMENT_START_DATE, SEGMENT_END_DATE
   FROM reports.multi_agent.DV360_BUDGETS_QUIZ
   WHERE EXTRACT(MONTH FROM SEGMENT_START_DATE) = 1 
   AND EXTRACT(YEAR FROM SEGMENT_START_DATE) = 2026
   ORDER BY SEGMENT_START_DATE DESC

3. "Current month Quiz budget" → Query current month segments:
   SELECT * FROM reports.multi_agent.DV360_BUDGETS_QUIZ
   WHERE SEGMENT_START_DATE <= CURRENT_DATE()
   AND SEGMENT_END_DATE >= CURRENT_DATE()

4. "Quiz budget for Feb 2026" → Filter by specific month/year:
   SELECT IO_NAME, BUDGET_AMOUNT, SEGMENT_START_DATE, SEGMENT_END_DATE
   FROM reports.multi_agent.DV360_BUDGETS_QUIZ
   WHERE EXTRACT(MONTH FROM SEGMENT_START_DATE) = 2 
   AND EXTRACT(YEAR FROM SEGMENT_START_DATE) = 2026
   ORDER BY SEGMENT_START_DATE DESC

Be data-driven, precise with DV360 terminology, and provide clear actionable insights."""

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
