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
async def query_campaign_performance(
    insertion_order: Optional[str] = None,
    advertiser: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 30
) -> str:
    """
    Query DV360 campaign performance metrics from Snowflake.

    Returns daily performance data including:
    - Impressions, clicks, conversions
    - Spend and revenue
    - Calculated metrics (CTR, CPC, CPA, ROAS)

    Use this tool when analyzing overall campaign performance, metrics trends,
    or diagnosing performance issues.

    Args:
        insertion_order: Campaign ID to filter (optional)
        advertiser: Advertiser name to filter (optional)
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        limit: Maximum number of days to return (default 30)

    Returns:
        JSON string with daily performance records
    """
    try:
        logger.info(
            "LLM calling query_campaign_performance",
            insertion_order=insertion_order,
            advertiser=advertiser,
            limit=limit
        )

        results = await snowflake_tool.get_campaign_performance(
            insertion_order=insertion_order,
            advertiser=advertiser,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        # Return as JSON string for LLM
        return json.dumps(results, default=str)

    except Exception as e:
        logger.error("query_campaign_performance failed", error=str(e))
        return json.dumps({"error": str(e)})


@tool
async def query_budget_pacing(
    insertion_order_id: Optional[str] = None,
    io_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    Query DV360 budget pacing data from Snowflake for Quiz advertiser.
    
    IMPORTANT CONTEXT:
    - All budgets are for advertiser 'Quiz' only
    - Budgets are at MONTHLY level (each row = one monthly budget segment)
    - Table: reports.multi_agent.DV360_BUDGETS_QUIZ
    
    Returns monthly budget segments with:
    - INSERTION_ORDER_ID: Insertion order ID
    - IO_NAME: Insertion order name
    - IO_STATUS: Insertion order status
    - SEGMENT_NUMBER: Monthly segment number
    - BUDGET_AMOUNT: Total budget for the monthly segment
    - SEGMENT_START_DATE: Start date of monthly segment
    - SEGMENT_END_DATE: End date of monthly segment
    - DAYS_IN_SEGMENT: Number of days in segment
    - AVG_DAILY_BUDGET: Average daily budget
    - SEGMENT_STATUS: Budget segment status

    Use this tool when analyzing budget allocation, monthly budget segments,
    or understanding budget structure for Quiz campaigns.

    Args:
        insertion_order_id: Optional insertion order ID to filter by
        io_name: Optional insertion order name to filter by (supports partial match, e.g., "Quiz")
        start_date: Optional start date in YYYY-MM-DD format (filters by SEGMENT_START_DATE)
        end_date: Optional end date in YYYY-MM-DD format (filters by SEGMENT_END_DATE)

    Returns:
        JSON string with list of monthly budget segment records
    """
    try:
        logger.info(
            "LLM calling query_budget_pacing",
            insertion_order_id=insertion_order_id,
            io_name=io_name,
            start_date=start_date,
            end_date=end_date
        )

        results = await snowflake_tool.get_budget_pacing(
            insertion_order_id=insertion_order_id,
            io_name=io_name,
            start_date=start_date,
            end_date=end_date
        )

        return json.dumps(results, default=str)

    except Exception as e:
        logger.error("query_budget_pacing failed", error=str(e))
        return json.dumps({"error": str(e)})


@tool
async def query_audience_performance(
    advertiser_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_impressions: int = 1000
) -> str:
    """
    Query DV360 audience segment performance from Snowflake.

    Returns performance data by audience segment/line item including:
    - Impressions, clicks, conversions per segment
    - Spend and revenue per segment
    - Segment-level CTR, CPC, CPA, ROAS

    Use this tool when analyzing audience targeting effectiveness,
    comparing segment performance, or optimizing audience strategy.

    Args:
        advertiser_id: Advertiser ID to filter
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        min_impressions: Minimum impressions to include segment (default 1000)

    Returns:
        JSON string with audience segment performance records
    """
    try:
        logger.info(
            "LLM calling query_audience_performance",
            advertiser_id=advertiser_id,
            min_impressions=min_impressions
        )

        results = await snowflake_tool.get_audience_performance(
            advertiser_id=advertiser_id,
            start_date=start_date,
            end_date=end_date,
            min_impressions=min_impressions
        )

        return json.dumps(results, default=str)

    except Exception as e:
        logger.error("query_audience_performance failed", error=str(e))
        return json.dumps({"error": str(e)})


@tool
async def query_creative_performance(
    campaign_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    Query DV360 creative asset performance from Snowflake.

    Returns performance data by creative including:
    - Impressions, clicks, conversions per creative
    - Spend and revenue per creative
    - Creative-level CTR, CVR, CPC, CPA, ROAS
    - Creative size/format breakdown

    Use this tool when analyzing creative effectiveness, detecting fatigue,
    comparing creative variants, or planning creative refresh.

    Args:
        campaign_id: Campaign ID to filter
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)

    Returns:
        JSON string with creative performance records
    """
    try:
        logger.info(
            "LLM calling query_creative_performance",
            campaign_id=campaign_id
        )

        results = await snowflake_tool.get_creative_performance(
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date
        )

        return json.dumps(results, default=str)

    except Exception as e:
        logger.error("query_creative_performance failed", error=str(e))
        return json.dumps({"error": str(e)})


@tool
async def execute_custom_snowflake_query(query: str) -> str:
    """
    Execute a custom SQL query against Snowflake DV360 data.

    Use this tool when you need specific data that isn't available
    from the specialized query tools. Be careful with query syntax.

    Available tables:
    - reports.reporting_revamp.ALL_PERFORMANCE_AGG (main performance data)
    - reports.reporting_revamp.creative_name_agg (creative data)
    - reports.multi_agent.DV360_BUDGETS_QUIZ (budget data)

    Args:
        query: SQL query string to execute

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
ALL_SNOWFLAKE_TOOLS = [
    query_campaign_performance,
    query_budget_pacing,
    query_audience_performance,
    query_creative_performance,
    execute_custom_snowflake_query,
]
