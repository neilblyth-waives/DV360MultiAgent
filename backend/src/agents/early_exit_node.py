"""
Early Exit Node - Determines if further processing is needed.

This node checks if the query can be answered without generating
recommendations (e.g., all metrics are good, no issues found).
"""
from typing import Dict, Any
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class EarlyExitNode:
    """
    Early Exit Node for conditional flow control.

    Determines if the orchestrator should skip recommendation/validation
    and return results early.
    """

    def __init__(self):
        """Initialize Early Exit Node."""
        pass

    def should_exit_early(
        self,
        diagnosis: Dict[str, Any],
        agent_results: Dict[str, Any],
        query: str
    ) -> Dict[str, Any]:
        """
        Determine if we should exit early without recommendations.

        Args:
            diagnosis: Diagnosis results
            agent_results: Results from specialist agents
            query: Original user query

        Returns:
            Dict with:
            - exit: bool - Whether to exit early
            - reason: str - Reason for the decision
            - final_response: Optional[str] - Response if exiting early
        """
        # Check severity
        severity = diagnosis.get("severity", "medium")
        if severity in ["critical", "high"]:
            # Don't exit early if issues are severe
            logger.info("Not exiting early - severity is high", severity=severity)
            return {
                "exit": False,
                "reason": f"Severity is {severity}, recommendations needed"
            }

        # Check if there are issues
        issues = diagnosis.get("issues", [])
        root_causes = diagnosis.get("root_causes", [])

        if not issues and not root_causes:
            # No issues found - can exit early
            logger.info("Exiting early - no issues found")
            return {
                "exit": True,
                "reason": "No actionable issues found",
                "final_response": self._build_no_issues_response(agent_results, query)
            }

        # Check if all metrics are within acceptable ranges
        # (This would require parsing agent responses for metrics)
        # For now, use a simple heuristic

        # Check if query is purely informational (not asking for recommendations)
        informational_keywords = ["how is", "what is", "show me", "tell me about", "explain"]
        query_lower = query.lower()
        if any(keyword in query_lower for keyword in informational_keywords):
            if len(issues) <= 2:
                # Informational query with few issues - can exit early
                logger.info("Exiting early - informational query with minimal issues")
                return {
                    "exit": True,
                    "reason": "Informational query answered, minimal issues",
                    "final_response": None  # Use diagnosis summary
                }

        # Default: don't exit early
        logger.info("Not exiting early - continuing to recommendations")
        return {
            "exit": False,
            "reason": "Issues found, recommendations needed"
        }

    def _build_no_issues_response(
        self,
        agent_results: Dict[str, Any],
        query: str
    ) -> str:
        """Build a response when no issues are found."""
        response_parts = [f"Based on your query: \"{query}\"\n"]

        response_parts.append("I've analyzed the data and found no significant issues.")

        # Add brief summary from each agent
        for agent_name, output in agent_results.items():
            agent_display = agent_name.replace("_", " ").title()
            response_parts.append(f"\n**{agent_display}**: All metrics within acceptable ranges.")

        response_parts.append("\nEverything looks good! No immediate action required.")

        return "\n".join(response_parts)


# Global instance
early_exit_node = EarlyExitNode()
