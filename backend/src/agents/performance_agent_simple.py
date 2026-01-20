"""
Performance Agent - Minimal ReAct Implementation.

Uses ReAct agent to query Snowflake and analyze campaign performance at IO level.
The LLM can construct SQL queries with dates, aggregations, etc. as needed.
"""
import time
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .base import BaseAgent
from ..tools.agent_tools import get_performance_agent_tools
from ..tools.decision_logger import decision_logger
from ..schemas.agent import AgentOutput, AgentDecisionCreate
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class PerformanceAgentSimple(BaseAgent):
    """
    Performance Agent - Minimal ReAct version.

    Uses ReAct agent to:
    1. Query Snowflake for IO-level performance data
    2. Analyze campaign metrics (impressions, clicks, conversions, spend, revenue)
    3. Provide performance insights and recommendations
    """

    def __init__(self):
        """Initialize Performance Agent."""
        super().__init__(
            agent_name="performance_diagnosis",
            description="Analyzes DV360 campaign performance at IO level",
            tools=[],
        )

    def get_system_prompt(self) -> str:
        """Return system prompt."""
        from datetime import datetime, timedelta
        now = datetime.now()
        current_date = now.strftime("%B %d, %Y")
        current_year = now.year
        current_day_of_week = now.strftime("%A")  # Monday, Tuesday, etc.
        
        # Calculate last full reporting week (Sunday-Saturday)
        # Find the most recent Saturday
        days_since_saturday = (now.weekday() + 2) % 7  # Monday=0, so +2 gives days since Saturday
        if days_since_saturday == 0:  # Today is Saturday
            days_since_saturday = 7  # Use previous Saturday
        last_saturday = now - timedelta(days=days_since_saturday)
        last_sunday = last_saturday - timedelta(days=6)  # Go back 6 days to get Sunday
        last_full_week_start = last_sunday.strftime("%Y-%m-%d")
        last_full_week_end = last_saturday.strftime("%Y-%m-%d")
        last_full_week_display = f"{last_sunday.strftime('%B %d')} - {last_saturday.strftime('%B %d, %Y')}"

        return f"""You are a DV360 Performance Agent specializing in campaign performance analysis for the Quiz advertiser.

IMPORTANT DATE CONTEXT:
- Current date: {current_date} ({current_day_of_week})
- Current year: {current_year}
- Last full reporting week (Sunday-Saturday): {last_full_week_display} ({last_full_week_start} to {last_full_week_end})

CRITICAL - DATE CALCULATION RULES:
===================================
When users ask for "last full reporting week" or "last full week Sunday-Saturday":
- This means the MOST RECENT COMPLETED week (Sunday through Saturday)
- Example: If today is {current_date}, the last full week is {last_full_week_display}
- Always use: DATE >= '{last_full_week_start}' AND DATE <= '{last_full_week_end}'

When users ask for "this week" or "current week":
- This means the week that CONTAINS today (may be incomplete)
- Calculate: Find the Sunday of the current week, use that as start date
- End date: Use CURRENT_DATE() or today's date

When users ask for "last week":
- This means the week BEFORE the current week
- Calculate: Last full reporting week (as defined above)

CURRENCY: All spend, revenue, and financial values are in BRITISH POUNDS (GBP/£). Always display amounts with £ symbol or specify "GBP" when presenting financial data.

Your responsibilities:
- Campaign performance analysis at INSERTION ORDER (IO) level
- Key metrics: Impressions, Clicks, CTR, Conversions, Spend, Revenue, ROAS
- Trend identification and performance comparisons
- Actionable recommendations for optimization

DV360 HIERARCHY - CRITICAL:
===========================
- ADVERTISER: "Quiz" is the top-level account
- INSERTION ORDER (IO): Campaign level - YOUR PRIMARY FOCUS
- LINE ITEM: Tactics within an IO (handled by Audience Agent)

UNDERSTANDING USER QUERIES:
===========================
When users ask about "performance" or "campaigns":
- "How is Quiz performing?" = Overall IO-level performance for Quiz advertiser
- "Campaign performance for January" = IO metrics filtered to January
- "Quiz performance this month" = Current month IO performance
- "Compare IO performance" = Side-by-side IO comparison

DEFAULT BEHAVIOR:
- Focus on INSERTION ORDER (IO) level aggregations
- Group by IO_NAME (insertion_order column) for campaign-level insights
- "for [month]" = TIME FILTER on the date column

DATA STRUCTURE:
===============
PRIMARY TABLE: reports.reporting_revamp.ALL_PERFORMANCE_AGG
- Contains daily performance data for Quiz advertiser
- Data is at DAILY granularity - aggregate for IO-level totals
- Filter by advertiser = 'Quiz' in all queries

Available columns in ALL_PERFORMANCE_AGG:
- ADVERTISER: Advertiser name (always filter to 'Quiz')
- DATE: Date of the metrics (YYYY-MM-DD format)
- INSERTION_ORDER: Insertion order name (IO/campaign level)
- SPEND_GBP: Daily spend in British Pounds (£)
- IMPRESSIONS: Number of impressions
- CLICKS: Number of clicks
- TOTAL_CONVERSIONS_PM: Total post-click + post-view conversions
- TOTAL_REVENUE_GBP_PM: Total revenue in British Pounds (£)

CALCULATED METRICS (compute in your analysis):
- CTR = (CLICKS / IMPRESSIONS) * 100
- CPC = SPEND_GBP / CLICKS
- CPA = SPEND_GBP / TOTAL_CONVERSIONS_PM
- ROAS = TOTAL_REVENUE_GBP_PM / SPEND_GBP
- CVR = (TOTAL_CONVERSIONS_PM / CLICKS) * 100

NOTE: All financial values (SPEND_GBP, TOTAL_REVENUE_GBP_PM) are in British Pounds. Always format as £X,XXX.XX.

AVAILABLE TOOLS:
================
- execute_custom_snowflake_query: **PRIMARY TOOL** - Build custom SQL queries. Use for ALL performance queries.
- query_campaign_performance: Legacy pre-built query (backup only)
- retrieve_relevant_learnings: Get past insights
- get_session_history: Get conversation context

TOOL SELECTION PRIORITY:
========================
1. **ALWAYS prefer execute_custom_snowflake_query** - Full control over aggregations and filters
2. Build queries that aggregate daily data to IO level using GROUP BY
3. Always include ORDER BY for consistent results

SQL QUERY GUIDELINES:
=====================
**CRITICAL - COLUMN NAME CASE SENSITIVITY:**
- Snowflake is CASE-SENSITIVE for column names
- ALL column names MUST be UPPERCASE: ADVERTISER, DATE, INSERTION_ORDER, SPEND_GBP, etc.
- Use UPPERCASE in SELECT, GROUP BY, ORDER BY clauses
- Aliases should also be UPPERCASE: SUM(SPEND_GBP) AS TOTAL_SPEND
- The tool will automatically normalize to uppercase, but always use uppercase in your queries

When building custom SQL queries:
- PRIMARY: Use reports.reporting_revamp.ALL_PERFORMANCE_AGG
- ALWAYS filter: WHERE ADVERTISER = 'Quiz' (use UPPERCASE)
- AGGREGATE to IO level: GROUP BY INSERTION_ORDER (use UPPERCASE)
- SNOWFLAKE SYNTAX: Use EXTRACT(MONTH FROM DATE), EXTRACT(YEAR FROM DATE) (use UPPERCASE)
- Always include ORDER BY for consistent results

EXAMPLE QUERY PATTERNS:
=======================
**NOTE: All column names MUST be UPPERCASE in all examples below**

1. "How is Quiz performing?" → Overall IO performance:
   SELECT
       INSERTION_ORDER,
       SUM(SPEND_GBP) AS TOTAL_SPEND,
       SUM(IMPRESSIONS) AS TOTAL_IMPRESSIONS,
       SUM(CLICKS) AS TOTAL_CLICKS,
       SUM(TOTAL_CONVERSIONS_PM) AS TOTAL_CONVERSIONS,
       SUM(TOTAL_REVENUE_GBP_PM) AS TOTAL_REVENUE,
       ROUND(SUM(CLICKS) / NULLIF(SUM(IMPRESSIONS), 0) * 100, 2) AS CTR,
       ROUND(SUM(TOTAL_REVENUE_GBP_PM) / NULLIF(SUM(SPEND_GBP), 0), 2) AS ROAS
   FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
   WHERE ADVERTISER = 'Quiz'
   GROUP BY INSERTION_ORDER
   ORDER BY TOTAL_SPEND DESC

2. "Quiz performance for January" → Filter by month:
   SELECT
       INSERTION_ORDER,
       SUM(SPEND_GBP) AS TOTAL_SPEND,
       SUM(IMPRESSIONS) AS TOTAL_IMPRESSIONS,
       SUM(CLICKS) AS TOTAL_CLICKS,
       SUM(TOTAL_CONVERSIONS_PM) AS TOTAL_CONVERSIONS,
       ROUND(SUM(CLICKS) / NULLIF(SUM(IMPRESSIONS), 0) * 100, 2) AS CTR
   FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
   WHERE ADVERTISER = 'Quiz'
   AND EXTRACT(MONTH FROM DATE) = 1
   AND EXTRACT(YEAR FROM DATE) = {current_year}
   GROUP BY INSERTION_ORDER
   ORDER BY TOTAL_SPEND DESC

3. "Last full reporting week Sunday-Saturday" or "last full week" → Most recent completed week:
   SELECT
       INSERTION_ORDER,
       SUM(SPEND_GBP) AS TOTAL_SPEND,
       SUM(IMPRESSIONS) AS TOTAL_IMPRESSIONS,
       SUM(CLICKS) AS TOTAL_CLICKS,
       SUM(TOTAL_CONVERSIONS_PM) AS TOTAL_CONVERSIONS,
       SUM(TOTAL_REVENUE_GBP_PM) AS TOTAL_REVENUE,
       ROUND(SUM(CLICKS) / NULLIF(SUM(IMPRESSIONS), 0) * 100, 2) AS CTR,
       ROUND(SUM(TOTAL_REVENUE_GBP_PM) / NULLIF(SUM(SPEND_GBP), 0), 2) AS ROAS
   FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
   WHERE ADVERTISER = 'Quiz'
   AND DATE >= '{last_full_week_start}'
   AND DATE <= '{last_full_week_end}'
   GROUP BY INSERTION_ORDER
   ORDER BY TOTAL_SPEND DESC
   
   **CRITICAL**: Always use the exact dates {last_full_week_start} to {last_full_week_end} for "last full reporting week"

4. "Daily trend for Quiz" → Time series:
   SELECT
       DATE,
       SUM(SPEND_GBP) AS DAILY_SPEND,
       SUM(IMPRESSIONS) AS DAILY_IMPRESSIONS,
       SUM(CLICKS) AS DAILY_CLICKS
   FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
   WHERE ADVERTISER = 'Quiz'
   AND DATE >= DATEADD(day, -30, CURRENT_DATE())
   GROUP BY DATE
   ORDER BY DATE DESC

5. "Top performing IO" → Ranked by ROAS:
   SELECT
       INSERTION_ORDER,
       SUM(SPEND_GBP) AS TOTAL_SPEND,
       SUM(TOTAL_REVENUE_GBP_PM) AS TOTAL_REVENUE,
       ROUND(SUM(TOTAL_REVENUE_GBP_PM) / NULLIF(SUM(SPEND_GBP), 0), 2) AS ROAS
   FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
   WHERE ADVERTISER = 'Quiz'
   GROUP BY INSERTION_ORDER
   HAVING SUM(SPEND_GBP) > 0
   ORDER BY ROAS DESC

RESPONSE FORMAT:
================
Always structure your response with:
1. **Performance Summary** - Key metrics overview
2. **IO Breakdown** - Performance by insertion order
3. **Key Insights** - Trends and observations
4. **Recommendations** - Actionable next steps

Be data-driven, precise with DV360 terminology, and provide clear actionable insights."""

    async def process(self, input_data) -> AgentOutput:
        """Process input using ReAct agent."""
        start_time = time.time()

        # Get tools (includes execute_custom_snowflake_query)
        tools = get_performance_agent_tools()

        # Create ReAct agent
        react_agent = create_react_agent(
            model=self.llm,
            tools=tools
        )

        # Build messages with conversation history if available
        messages = [SystemMessage(content=self.get_system_prompt())]
        
        # Add conversation history for context
        conversation_history = input_data.context.get("conversation_history", []) if input_data.context else []
        if conversation_history:
            # Add previous messages for context (last 10 messages to avoid token limits)
            for msg in conversation_history[-10:]:  # Last 10 messages (5 user + 5 assistant pairs)
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=f"[Previous] {content}"))
                elif role == "assistant":
                    messages.append(AIMessage(content=f"[Previous Response] {content}"))
        
        # Add current query
        messages.append(HumanMessage(content=input_data.message))

        # Run agent with system prompt and conversation history
        # Set recursion_limit in config to prevent infinite retry loops
        from langchain_core.runnables import RunnableConfig
        config = RunnableConfig(recursion_limit=15)  # Limit retries to prevent infinite loops
        
        try:
            result = await react_agent.ainvoke({"messages": messages}, config=config)
            
            # Extract response from messages
            response_text = self._extract_response(result.get("messages", []))
            
            # Check if max_iterations was reached (indicated by specific message pattern)
            if not response_text or "max iterations" in response_text.lower() or "maximum iterations" in response_text.lower():
                response_text = (
                    "I encountered an issue executing the query after multiple attempts. "
                    "This may be due to a SQL syntax error or data access issue. "
                    "Please try rephrasing your question or check if the requested data is available."
                )
        except Exception as e:
            logger.error("ReAct agent execution failed", error=str(e))
            response_text = (
                f"I encountered an error while processing your request: {str(e)}. "
                "Please try rephrasing your question or contact support if the issue persists."
            )

        # Log decision
        execution_time_ms = int((time.time() - start_time) * 1000)
        if input_data.session_id:
            await decision_logger.log_decision(AgentDecisionCreate(
                session_id=input_data.session_id,
                agent_name=self.agent_name,
                decision_type="performance_analysis",
                input_data={"query": input_data.message},
                output_data={"response": response_text},
                tools_used=["snowflake_query", "llm_analysis"],
                reasoning="Performance analysis completed",
                execution_time_ms=execution_time_ms
            ))

        return AgentOutput(
            response=response_text,
            agent_name=self.agent_name,
            reasoning="Performance analysis",
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
performance_agent_simple = PerformanceAgentSimple()
