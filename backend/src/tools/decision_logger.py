"""
Decision logging tool to track all agent decisions.
"""
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import date, datetime
import time
import json

from ..core.database import get_pg_connection
from ..core.telemetry import get_logger, log_db_query
from ..schemas.agent import AgentDecisionCreate


logger = get_logger(__name__)


def json_serializer(obj: Any) -> str:
    """
    Custom JSON serializer for objects not serializable by default json code.
    Handles date, datetime, and other common non-serializable types.
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


class DecisionLogger:
    """
    Logs agent decisions to the database for audit and learning.

    Every agent decision should be logged with:
    - Input data
    - Output data
    - Tools used
    - Reasoning
    - Execution time
    """

    async def log_decision(self, decision: AgentDecisionCreate) -> UUID:
        """
        Log an agent decision to the database.

        Args:
            decision: Decision data to log

        Returns:
            UUID of the created decision record
        """
        start_time = time.time()

        try:
            async with get_pg_connection() as conn:
                query = """
                    INSERT INTO agent_decisions (
                        session_id,
                        message_id,
                        agent_name,
                        decision_type,
                        input_data,
                        output_data,
                        tools_used,
                        reasoning,
                        execution_time_ms
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                """

                decision_id = await conn.fetchval(
                    query,
                    decision.session_id,
                    decision.message_id,
                    decision.agent_name,
                    decision.decision_type,
                    json.dumps(decision.input_data, default=json_serializer) if decision.input_data else None,
                    json.dumps(decision.output_data, default=json_serializer) if decision.output_data else None,
                    json.dumps(decision.tools_used, default=json_serializer) if decision.tools_used else None,
                    decision.reasoning,
                    decision.execution_time_ms,
                )

                duration = time.time() - start_time
                log_db_query("insert", "agent_decisions", duration)

                logger.info(
                    "Decision logged",
                    decision_id=str(decision_id),
                    agent_name=decision.agent_name,
                    decision_type=decision.decision_type,
                )

                return decision_id

        except Exception as e:
            duration = time.time() - start_time
            log_db_query("insert", "agent_decisions", duration, error=str(e))
            logger.error("Failed to log decision", error=str(e))
            raise

    async def get_session_decisions(
        self,
        session_id: UUID,
        agent_name: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all decisions for a session.

        Args:
            session_id: Session ID
            agent_name: Optional filter by agent name
            limit: Maximum number of decisions to return

        Returns:
            List of decision records
        """
        start_time = time.time()

        try:
            async with get_pg_connection() as conn:
                if agent_name:
                    query = """
                        SELECT id, session_id, message_id, agent_name, decision_type,
                               input_data, output_data, tools_used, reasoning,
                               timestamp, execution_time_ms
                        FROM agent_decisions
                        WHERE session_id = $1 AND agent_name = $2
                        ORDER BY timestamp DESC
                        LIMIT $3
                    """
                    rows = await conn.fetch(query, session_id, agent_name, limit)
                else:
                    query = """
                        SELECT id, session_id, message_id, agent_name, decision_type,
                               input_data, output_data, tools_used, reasoning,
                               timestamp, execution_time_ms
                        FROM agent_decisions
                        WHERE session_id = $1
                        ORDER BY timestamp DESC
                        LIMIT $2
                    """
                    rows = await conn.fetch(query, session_id, limit)

                duration = time.time() - start_time
                log_db_query("select", "agent_decisions", duration)

                return [dict(row) for row in rows]

        except Exception as e:
            duration = time.time() - start_time
            log_db_query("select", "agent_decisions", duration, error=str(e))
            logger.error("Failed to get session decisions", error=str(e))
            raise

    async def get_agent_stats(self, agent_name: str, days: int = 7) -> Dict[str, Any]:
        """
        Get statistics for an agent over the last N days.

        Args:
            agent_name: Agent name
            days: Number of days to look back

        Returns:
            Statistics dictionary
        """
        start_time = time.time()

        try:
            async with get_pg_connection() as conn:
                query = """
                    SELECT
                        COUNT(*) as total_decisions,
                        COUNT(DISTINCT session_id) as unique_sessions,
                        AVG(execution_time_ms) as avg_execution_ms,
                        MAX(execution_time_ms) as max_execution_ms,
                        MIN(execution_time_ms) as min_execution_ms
                    FROM agent_decisions
                    WHERE agent_name = $1
                      AND timestamp > NOW() - INTERVAL '$2 days'
                """

                row = await conn.fetchrow(query, agent_name, days)

                duration = time.time() - start_time
                log_db_query("select", "agent_decisions", duration)

                return dict(row) if row else {}

        except Exception as e:
            duration = time.time() - start_time
            log_db_query("select", "agent_decisions", duration, error=str(e))
            logger.error("Failed to get agent stats", error=str(e))
            raise

    async def get_most_used_tools(
        self,
        agent_name: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get most frequently used tools.

        Args:
            agent_name: Optional filter by agent name
            limit: Maximum number of tools to return

        Returns:
            List of tools with usage counts
        """
        start_time = time.time()

        try:
            async with get_pg_connection() as conn:
                if agent_name:
                    query = """
                        SELECT
                            jsonb_array_elements_text(tools_used) as tool_name,
                            COUNT(*) as usage_count
                        FROM agent_decisions
                        WHERE agent_name = $1
                        GROUP BY tool_name
                        ORDER BY usage_count DESC
                        LIMIT $2
                    """
                    rows = await conn.fetch(query, agent_name, limit)
                else:
                    query = """
                        SELECT
                            jsonb_array_elements_text(tools_used) as tool_name,
                            COUNT(*) as usage_count
                        FROM agent_decisions
                        GROUP BY tool_name
                        ORDER BY usage_count DESC
                        LIMIT $1
                    """
                    rows = await conn.fetch(query, limit)

                duration = time.time() - start_time
                log_db_query("select", "agent_decisions", duration)

                return [dict(row) for row in rows]

        except Exception as e:
            duration = time.time() - start_time
            log_db_query("select", "agent_decisions", duration, error=str(e))
            logger.error("Failed to get most used tools", error=str(e))
            raise


# Global instance
decision_logger = DecisionLogger()
