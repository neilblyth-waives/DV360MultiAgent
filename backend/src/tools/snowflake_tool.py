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
            import os
            from pathlib import Path

            # Try multiple paths: configured path (Docker) and local development paths
            configured_path = settings.snowflake_private_key_path.strip()
            project_root = Path(__file__).parent.parent.parent.parent

            possible_paths = [
                configured_path,                                    # Docker: /app/rsa_key.p8
                project_root / "backend" / "rsa_key.p8",           # Local: backend/rsa_key.p8
                Path(configured_path.replace("/app/", str(project_root) + "/backend/")),  # Mapped path
            ]

            key_loaded = False
            for key_path in possible_paths:
                key_path = Path(key_path)
                if key_path.exists():
                    try:
                        logger.info(
                            "Attempting to load private key",
                            key_path=str(key_path),
                            file_exists=True
                        )

                        with open(key_path, "rb") as key_file:
                            private_key = key_file.read()

                        self.connection_params["private_key"] = private_key
                        logger.info(
                            "Snowflake initialized with key pair authentication (no 2FA)",
                            database=settings.snowflake_database,
                            key_path=str(key_path)
                        )
                        key_loaded = True
                        break
                    except Exception as e:
                        logger.warning(
                            "Failed to load private key from path",
                            key_path=str(key_path),
                            error=str(e)
                        )
                        continue

            if not key_loaded:
                logger.error(
                    "Private key file not found in any location, falling back to password auth",
                    tried_paths=[str(p) for p in possible_paths],
                    current_dir=os.getcwd()
                )
                if settings.snowflake_password:
                    self.connection_params["password"] = settings.snowflake_password
                    logger.warning("Using password authentication as fallback")
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

# Global instance
snowflake_tool = SnowflakeTool()
