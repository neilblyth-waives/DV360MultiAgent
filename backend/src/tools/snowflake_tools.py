"""
LangChain-compatible Snowflake tools for DV360 analysis.

Each tool is a separate function that agents can choose to call.
The LLM will see these tool descriptions and decide which ones to use.
"""
from typing import Optional, List, Dict, Any
import json
import re
from langchain_core.tools import tool

from .snowflake_tool import snowflake_tool
from ..core.telemetry import get_logger


logger = get_logger(__name__)


def normalize_sql_column_names(query: str) -> str:
    """
    Normalize SQL query to enforce UPPERCASE column names.
    
    Snowflake is case-sensitive, so column names must match exactly.
    This function:
    1. Converts column names to UPPERCASE in SELECT, GROUP BY, ORDER BY
    2. Preserves string literals (quoted values)
    3. Preserves function names and their syntax
    4. Handles aliases consistently
    
    Args:
        query: SQL query string
        
    Returns:
        Normalized SQL query with uppercase column names
    """
    normalized_query = query
    
    # Helper function to uppercase identifiers while preserving quoted strings
    def uppercase_identifiers_in_text(text: str) -> str:
        """Uppercase identifiers but preserve quoted strings and function calls."""
        result = []
        i = 0
        in_single_quote = False
        in_double_quote = False
        in_function = False
        paren_depth = 0
        
        while i < len(text):
            char = text[i]
            
            # Track quoted strings
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                result.append(char)
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                result.append(char)
            elif in_single_quote or in_double_quote:
                # Inside quotes - preserve as-is
                result.append(char)
            elif char == '(':
                paren_depth += 1
                result.append(char)
            elif char == ')':
                paren_depth -= 1
                result.append(char)
            elif re.match(r'[A-Za-z_]', char):
                # Start of identifier - collect the whole identifier
                start = i
                while i < len(text) and re.match(r'[A-Za-z0-9_]', text[i]):
                    i += 1
                identifier = text[start:i]
                
                # Check if it's a SQL keyword or function (keep uppercase)
                sql_keywords = {
                    'SELECT', 'FROM', 'WHERE', 'GROUP', 'BY', 'ORDER', 'AS', 'AND', 'OR',
                    'SUM', 'COUNT', 'AVG', 'MAX', 'MIN', 'EXTRACT', 'DATEADD', 'DATEDIFF',
                    'CURRENT_DATE', 'CURRENT_TIMESTAMP', 'ROUND', 'NULLIF', 'COALESCE',
                    'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'ASC', 'DESC', 'HAVING',
                    'LIMIT', 'OFFSET', 'DISTINCT'
                }
                if identifier.upper() in sql_keywords:
                    result.append(identifier.upper())
                else:
                    # Column name - uppercase it
                    result.append(identifier.upper())
                i -= 1  # Adjust because we'll increment in the loop
            else:
                result.append(char)
            
            i += 1
        
        return ''.join(result)
    
    # Normalize SELECT clause
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', normalized_query, re.IGNORECASE | re.DOTALL)
    if select_match:
        select_clause = select_match.group(1)
        normalized_select = uppercase_identifiers_in_text(select_clause)
        normalized_query = (
            normalized_query[:select_match.start(1)] +
            normalized_select +
            normalized_query[select_match.end(1):]
        )
    
    # Normalize GROUP BY clause
    group_by_match = re.search(r'GROUP\s+BY\s+(.*?)(?:\s+ORDER\s+BY|\s+HAVING|\s+$|$)', normalized_query, re.IGNORECASE | re.DOTALL)
    if group_by_match:
        group_by_clause = group_by_match.group(1).strip()
        normalized_group_by = uppercase_identifiers_in_text(group_by_clause)
        normalized_query = (
            normalized_query[:group_by_match.start(1)] +
            normalized_group_by +
            normalized_query[group_by_match.end(1):]
        )
    
    # Normalize ORDER BY clause
    order_by_match = re.search(r'ORDER\s+BY\s+(.*?)(?:\s+LIMIT|$)', normalized_query, re.IGNORECASE | re.DOTALL)
    if order_by_match:
        order_by_clause = order_by_match.group(1).strip()
        normalized_order_by = uppercase_identifiers_in_text(order_by_clause)
        normalized_query = (
            normalized_query[:order_by_match.start(1)] +
            normalized_order_by +
            normalized_query[order_by_match.end(1):]
        )
    
    return normalized_query


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
    **CRITICAL - COLUMN NAME CASE SENSITIVITY:**
    - Snowflake is CASE-SENSITIVE for column names
    - ALL column names MUST be UPPERCASE
    - Use UPPERCASE in SELECT, GROUP BY, ORDER BY clauses
    - Example: Use INSERTION_ORDER not insertion_order, SPEND_GBP not spend_gbp
    - Aliases should also be UPPERCASE: SUM(spend_gbp) AS TOTAL_SPEND
    
    - Date filtering: Use EXTRACT(MONTH FROM date) and EXTRACT(YEAR FROM date)
    - Date format: Use 'YYYY-MM-DD' format (e.g., '2026-01-01')
    - Aggregations: Use SUM(), COUNT(DISTINCT column), AVG() with GROUP BY
    - Always include ORDER BY for consistent results
    - Currency: All financial values are in BRITISH POUNDS (GBP/£)
    
    EXAMPLE QUERIES:
    ================
    -- IO-level performance (NOTE: All column names in UPPERCASE):
    SELECT INSERTION_ORDER, SUM(SPEND_GBP) AS TOTAL_SPEND, SUM(IMPRESSIONS) AS TOTAL_IMPRESSIONS
    FROM reports.reporting_revamp.ALL_PERFORMANCE_AGG
    WHERE ADVERTISER = 'Quiz' AND DATE >= '2026-01-01' AND DATE <= '2026-01-31'
    GROUP BY INSERTION_ORDER ORDER BY TOTAL_SPEND DESC
    
    -- Monthly budgets (NOTE: All column names in UPPERCASE):
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

        # Normalize SQL to enforce UPPERCASE column names
        normalized_query = normalize_sql_column_names(query)
        
        # Log if query was modified
        if normalized_query != query:
            logger.info(
                "SQL query normalized to uppercase column names",
                original_preview=query[:100],
                normalized_preview=normalized_query[:100]
            )

        results = await snowflake_tool.execute_query(normalized_query)

        return json.dumps(results, default=str)

    except Exception as e:
        error_msg = str(e)
        logger.error("execute_custom_snowflake_query failed", error=error_msg)
        
        # Return structured error that LLM can understand and act on
        error_response = {
            "error": True,
            "error_type": type(e).__name__,
            "error_message": error_msg,
            "suggestion": "Please review the SQL query syntax and try again. Common issues: incorrect table/column names, invalid date formats, or missing WHERE clauses."
        }
        return json.dumps(error_response)


# Export all tools as a list for easy agent registration
# NOTE: Only execute_custom_snowflake_query is available - agents build SQL queries themselves
ALL_SNOWFLAKE_TOOLS = [
    execute_custom_snowflake_query,
]
