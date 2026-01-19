"""
LangChain-compatible Snowflake tools for DV360 analysis.

Each tool is a separate function that agents can choose to call.
The LLM will see these tool descriptions and decide which ones to use.
"""
from typing import Optional, List, Dict, Any
import json
from langchain_core.tools import tool

from .snowflake_tool import snowflake_tool
from ..core.telemetry import get_logger


logger = get_logger(__name__)


@tool
async def execute_custom_snowflake_query(query: str) -> str:
    """
    Execute a custom SQL query against Snowflake DV360 data.

    **PRIMARY TOOL** - Use this for ALL Snowflake queries. Build SQL queries with dates, aggregations, filters as needed.

    AVAILABLE TABLES:
    =================
    
    1. reports.reporting_revamp.ALL_PERFORMANCE_AGG (main performance data)
       - Daily metrics at IO and line item level
       - Columns: advertiser, date, insertion_order, line_item, spend_gbp, impressions, clicks, total_conversions_pm, total_revenue_gbp_pm
       - ALWAYS filter: WHERE advertiser = 'Quiz'
       - Use for: Campaign performance, IO-level metrics, audience/line item analysis
    
    2. reports.reporting_revamp.creative_name_agg (creative performance)
       - Daily metrics by creative name and size
       - Columns: advertiser, date, insertion_order, creative, creative_size, spend_gbp, impressions, clicks, total_conversions_pm, total_revenue_gbp_pm
       - ALWAYS filter: WHERE advertiser = 'Quiz'
       - Use for: Creative effectiveness, creative size performance, creative fatigue
    
    3. reports.multi_agent.DV360_BUDGETS_QUIZ (budget data)
       - Monthly budget segments for Quiz advertiser
       - Columns: INSERTION_ORDER_ID, IO_NAME, IO_STATUS, SEGMENT_NUMBER, BUDGET_AMOUNT, SEGMENT_START_DATE, SEGMENT_END_DATE, DAYS_IN_SEGMENT, AVG_DAILY_BUDGET, SEGMENT_STATUS
       - NO advertiser filter needed (already Quiz-specific)
       - Use for: Budget allocation, monthly budgets, budget pacing
    
    SQL SYNTAX NOTES:
    =================
    - Date filtering: Use EXTRACT(MONTH FROM date) and EXTRACT(YEAR FROM date)
    - Date format: Use 'YYYY-MM-DD' format (e.g., '2026-01-01')
    - Aggregations: Use SUM(), COUNT(DISTINCT column), AVG() with GROUP BY
    - Always include ORDER BY for consistent results
    - Currency: All financial values are in BRITISH POUNDS (GBP/£)
    
    EXAMPLE QUERIES:
    ================
    -- IO-level performance:
    SELECT insertion_order, SUM(spend_gbp) as TOTAL_SPEND, SUM(impressions) as TOTAL_IMPRESSIONS
    FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
    WHERE advertiser = 'Quiz' AND date >= '2026-01-01' AND date <= '2026-01-31'
    GROUP BY insertion_order ORDER BY TOTAL_SPEND DESC
    
    -- Monthly budgets:
    SELECT IO_NAME, BUDGET_AMOUNT, SEGMENT_START_DATE, SEGMENT_END_DATE
    FROM reports.multi_agent.DV360_BUDGETS_QUIZ
    WHERE EXTRACT(MONTH FROM SEGMENT_START_DATE) = 1 AND EXTRACT(YEAR FROM SEGMENT_START_DATE) = 2026
    ORDER BY SEGMENT_START_DATE DESC

    Args:
        query: SQL query string to execute (must be valid Snowflake SQL)

    Returns:
        JSON string with query results
    """
    try:
        logger.info(
            "LLM calling execute_custom_snowflake_query",
            query_preview=query[:100]
        )

        results = await snowflake_tool.execute_query(query)

        return json.dumps(results, default=str)

    except Exception as e:
        logger.error("execute_custom_snowflake_query failed", error=str(e))
        return json.dumps({"error": str(e)})


# Export all tools as a list for easy agent registration
# NOTE: Only execute_custom_snowflake_query is available - agents build SQL queries themselves
ALL_SNOWFLAKE_TOOLS = [
    execute_custom_snowflake_query,
]
