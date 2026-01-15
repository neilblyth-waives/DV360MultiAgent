"""
Snowflake tool for querying DV360 data.
"""
from typing import Dict, Any, List, Optional
import hashlib
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

import snowflake.connector
from snowflake.connector import DictCursor
from langchain_core.tools import tool

from ..core.config import settings
from ..core.cache import get_query_cache, set_query_cache
from ..core.telemetry import get_logger


logger = get_logger(__name__)

# Thread pool for sync Snowflake connector
executor = ThreadPoolExecutor(max_workers=5)


class SnowflakeTool:
    """
    Tool for querying Snowflake DV360 data.

    Features:
    - Connection pooling
    - Query caching
    - Common DV360 query templates
    - Async execution wrapper
    """

    def __init__(self):
        """Initialize Snowflake connection with key pair or password authentication."""
        self.connection_params = {
            "account": settings.snowflake_account,
            "user": settings.snowflake_user,
            "warehouse": settings.snowflake_warehouse,
            "database": settings.snowflake_database,
            "schema": settings.snowflake_schema,
        }

        if settings.snowflake_role:
            self.connection_params["role"] = settings.snowflake_role

        # Check for key pair authentication (preferred - no 2FA!)
        if hasattr(settings, 'snowflake_private_key_path') and settings.snowflake_private_key_path:
            try:
                # Read private key file using the exact pattern from user
                with open(settings.snowflake_private_key_path, "rb") as key_file:
                    private_key = key_file.read()

                self.connection_params["private_key"] = private_key
                logger.info(
                    "Snowflake initialized with key pair authentication (no 2FA)",
                    database=settings.snowflake_database,
                    key_path=settings.snowflake_private_key_path
                )
            except Exception as e:
                logger.error(
                    "Failed to load private key, falling back to password auth",
                    error_message=str(e),
                    key_path=settings.snowflake_private_key_path
                )
                # Fall back to password if key loading fails
                if settings.snowflake_password:
                    self.connection_params["password"] = settings.snowflake_password
        else:
            # Use password authentication (may require 2FA)
            if settings.snowflake_password:
                self.connection_params["password"] = settings.snowflake_password
                logger.info(
                    "Snowflake initialized with password authentication",
                    database=settings.snowflake_database
                )
            else:
                logger.warning("No Snowflake authentication method configured")

        logger.info("Snowflake tool initialized", database=settings.snowflake_database)

    def _get_connection(self):
        """Get a Snowflake connection."""
        return snowflake.connector.connect(**self.connection_params)

    def _execute_query_sync(self, query: str) -> List[Dict[str, Any]]:
        """Execute query synchronously."""
        from datetime import date, datetime
        from decimal import Decimal
        
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor(DictCursor)
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()

            # Convert date/datetime/Decimal objects to JSON-serializable types
            serializable_results = []
            for row in results:
                serializable_row = {}
                for key, value in row.items():
                    if isinstance(value, (date, datetime)):
                        serializable_row[key] = value.isoformat()
                    elif isinstance(value, Decimal):
                        # Convert Decimal to float for JSON serialization
                        serializable_row[key] = float(value)
                    else:
                        serializable_row[key] = value
                serializable_results.append(serializable_row)

            return serializable_results
        finally:
            if conn:
                conn.close()

    async def execute_query(
        self,
        query: str,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute a Snowflake query asynchronously.

        Args:
            query: SQL query to execute
            use_cache: Whether to use query cache

        Returns:
            List of result dictionaries
        """
        start_time = time.time()

        # Check cache
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        if use_cache:
            cached = await get_query_cache(query_hash)
            if cached:
                logger.info("Query cache hit", query_hash=query_hash)
                return cached

        # Execute query in thread pool (Snowflake connector is sync)
        try:
            logger.info("Executing Snowflake query", query_preview=query[:100])

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                executor,
                self._execute_query_sync,
                query
            )

            duration = time.time() - start_time
            logger.info(
                "Query executed successfully",
                duration_seconds=round(duration, 2),
                result_count=len(results)
            )

            # Cache results
            if use_cache:
                await set_query_cache(query_hash, results)

            return results

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "Query execution failed",
                error=str(e),
                duration_seconds=round(duration, 2)
            )
            raise

    async def get_campaign_performance(
        self,
        insertion_order: Optional[str] = None,
        advertiser: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get campaign performance metrics.

        Args:
            insertion_order: Optional campaign ID filter
            advertiser: Optional advertiser ID filter
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            limit: Maximum number of results

        Returns:
            List of campaign performance records
        """
        # Build query with filters
        query_parts = ["""
            select 
            advertiser , 
            date ,
            insertion_order ,
            sum(spend_gbp) SPEND , 
            sum(impressions) impressions , 
            sum(clicks) clicks ,             
            sum(total_conversions_pm) TOTAL_CONVERSIONS , 
            sum(total_revenue_gbp_pm) TOTAL_REVENUE 
            from reports.reporting_revamp.ALL_PERFORMANCE_AGG
            where advertiser = 'Quiz'
        """]

        if insertion_order:
            query_parts.append(f"AND insertion_order = '{insertion_order}'")
        if advertiser:
            query_parts.append(f"AND advertiser = '{advertiser}'")
        if start_date:
            query_parts.append(f"AND date >= '{start_date}'")
        if end_date:
            query_parts.append(f"AND date <= '{end_date}'")

        query_parts.append(f"group by 1,2,3 ORDER BY date DESC LIMIT {limit}")

        query = "\n".join(query_parts)
        return await self.execute_query(query)

    async def get_budget_pacing(
        self,
        insertion_order_id: Optional[str] = None,
        io_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get budget pacing analysis for Quiz advertiser budgets.
        
        IMPORTANT CONTEXT:
        - All budgets are for advertiser 'Quiz' only
        - Budgets are at MONTHLY level (each row represents a monthly budget segment)
        - Table: reports.multi_agent.DV360_BUDGETS_QUIZ
        
        Available columns:
        - INSERTION_ORDER_ID: The insertion order ID
        - IO_NAME: Insertion order name
        - IO_STATUS: Status of the insertion order
        - SEGMENT_NUMBER: Monthly segment number
        - BUDGET_AMOUNT: Total budget for this monthly segment
        - SEGMENT_START_DATE: Start date of the monthly segment
        - SEGMENT_END_DATE: End date of the monthly segment
        - DAYS_IN_SEGMENT: Number of days in the segment
        - AVG_DAILY_BUDGET: Average daily budget for the segment
        - SEGMENT_STATUS: Status of the budget segment

        Args:
            insertion_order_id: Optional insertion order ID filter
            io_name: Optional insertion order name filter (supports partial match)
            start_date: Optional start date filter (YYYY-MM-DD) - filters by SEGMENT_START_DATE
            end_date: Optional end date filter (YYYY-MM-DD) - filters by SEGMENT_END_DATE

        Returns:
            List of budget pacing records (monthly segments)
        """
        query_parts = ["""
            SELECT 
                INSERTION_ORDER_ID,
                IO_NAME,
                IO_STATUS,
                SEGMENT_NUMBER,
                BUDGET_AMOUNT,
                SEGMENT_START_DATE,
                SEGMENT_END_DATE,
                DAYS_IN_SEGMENT,
                AVG_DAILY_BUDGET,
                SEGMENT_STATUS
            FROM reports.multi_agent.DV360_BUDGETS_QUIZ
            WHERE 1=1
        """]
        
        if insertion_order_id:
            query_parts.append(f"AND INSERTION_ORDER_ID = '{insertion_order_id}'")
        if io_name:
            query_parts.append(f"AND IO_NAME LIKE '%{io_name}%'")
        if start_date:
            query_parts.append(f"AND SEGMENT_START_DATE >= '{start_date}'")
        if end_date:
            query_parts.append(f"AND SEGMENT_END_DATE <= '{end_date}'")
        
        query_parts.append("ORDER BY SEGMENT_START_DATE DESC")
        
        query = "\n".join(query_parts)
        return await self.execute_query(query)

    async def get_audience_performance(
        self,
        advertiser_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_impressions: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get audience segment performance.

        Args:
            advertiser_id: Advertiser ID
            start_date: Optional start date
            end_date: Optional end date
            min_impressions: Minimum impressions filter

        Returns:
            List of audience performance records
        """
        query_parts = [f"""
            select 
            advertiser , 
            date ,
            insertion_order ,
            line_item ,
            sum(spend_gbp) SPEND , 
            sum(impressions) impressions , 
            sum(clicks) clicks ,             
            sum(total_conversions_pm) TOTAL_CONVERSIONS , 
            sum(total_revenue_gbp_pm) TOTAL_REVENUE 
            from reports.reporting_revamp.ALL_PERFORMANCE_AGG
            where advertiser = 'Quiz'
        """]

        if start_date:
            query_parts.append(f"AND date >= '{start_date}'")
        if end_date:
            query_parts.append(f"AND date <= '{end_date}'")

        query_parts.append("""
            group by 1,2,3,4
        """)

        query = "\n".join(query_parts)
        return await self.execute_query(query)

    async def get_creative_performance(
        self,
        campaign_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get creative performance metrics.

        Args:
            campaign_id: Campaign ID
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            List of creative performance records
        """
        query_parts = [f"""
            select 
            advertiser , 
            date ,
            insertion_order ,
            REGEXP_REPLACE(CREATIVE, '_[^_]*$', '') AS creative_name ,
            creative_size ,
            sum(spend_gbp) SPEND , 
            sum(impressions) impressions , 
            sum(clicks) clicks ,             
            sum(total_conversions_pm) TOTAL_CONVERSIONS , 
            sum(total_revenue_gbp_pm) TOTAL_REVENUE 
            from reports.reporting_revamp.creative_name_agg
            where advertiser = 'Quiz'
            """]

        if start_date:
            query_parts.append(f"AND date >= '{start_date}'")
        if end_date:
            query_parts.append(f"AND date <= '{end_date}'")

        query_parts.append("""
            group by 1,2,3,4,5
        """)

        query = "\n".join(query_parts)
        return await self.execute_query(query)


# Global instance
snowflake_tool = SnowflakeTool()
