"""
Gate Node - Validates routing decisions and applies business rules.

This node acts as a gatekeeper that validates queries before they
proceed to specialist agents.
"""
from typing import Dict, Any, List, Optional
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class GateNode:
    """
    Gate Node for validating routing decisions.

    Applies business rules and validation logic before queries
    proceed to specialist agents.
    """

    def __init__(self):
        """Initialize Gate Node."""
        self.min_query_length = 3  # Minimum words in query
        self.max_agents = 3  # Maximum agents to invoke at once

    def validate(
        self,
        query: str,
        selected_agents: List[str],
        routing_confidence: float,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a routing decision.

        Args:
            query: User query
            selected_agents: Agents selected by routing agent
            routing_confidence: Confidence score from routing agent
            user_id: Optional user ID for rate limiting

        Returns:
            Dict with:
            - valid: bool - Whether to proceed
            - proceed: bool - Whether to proceed (same as valid)
            - reason: str - Explanation
            - warnings: List[str] - Any warnings
            - approved_agents: List[str] - Agents approved to proceed
        """
        warnings = []
        valid = True
        reason = "Validation passed"

        # Rule 1: Check query length
        words = query.split()
        if len(words) < self.min_query_length:
            warnings.append(f"Query is very short ({len(words)} words)")
            # Don't block, but warn
            if routing_confidence < 0.6:
                valid = False
                reason = "Query too vague and routing confidence low"
                logger.warning(
                    "Gate blocked query",
                    query=query[:50],
                    word_count=len(words),
                    confidence=routing_confidence
                )

        # Rule 2: Check number of agents
        if len(selected_agents) > self.max_agents:
            warnings.append(f"Too many agents selected ({len(selected_agents)}), limiting to {self.max_agents}")
            selected_agents = selected_agents[:self.max_agents]

        # Rule 3: Check routing confidence
        if routing_confidence < 0.4:
            warnings.append(f"Low routing confidence ({routing_confidence:.2f})")
            # Still proceed, but flag it

        # Rule 4: Validate agent names
        valid_agent_names = [
            "performance_diagnosis",
            "budget_risk",
            "delivery_optimization",
            "audience_targeting",
            "creative_inventory"
        ]
        approved_agents = [a for a in selected_agents if a in valid_agent_names]
        if len(approved_agents) < len(selected_agents):
            invalid_agents = [a for a in selected_agents if a not in valid_agent_names]
            warnings.append(f"Invalid agent names removed: {', '.join(invalid_agents)}")

        # Rule 5: Ensure at least one agent
        if not approved_agents:
            warnings.append("No valid agents selected, defaulting to performance_diagnosis")
            approved_agents = ["performance_diagnosis"]

        logger.info(
            "Gate validation complete",
            query=query[:50],
            valid=valid,
            approved_agents=approved_agents,
            warnings_count=len(warnings)
        )

        return {
            "valid": valid,
            "proceed": valid,
            "reason": reason,
            "warnings": warnings,
            "approved_agents": approved_agents
        }

    def check_rate_limit(self, user_id: str) -> Dict[str, Any]:
        """
        Check if user has exceeded rate limits.

        Args:
            user_id: User ID

        Returns:
            Dict with rate limit status
        """
        # TODO: Implement actual rate limiting with Redis
        # For now, always allow
        return {
            "allowed": True,
            "remaining": 100,
            "reset_time": None
        }


# Global instance
gate_node = GateNode()
