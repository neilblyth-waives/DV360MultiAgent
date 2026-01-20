"""
Recommendation Agent - Generates actionable recommendations.

This agent takes diagnosis results and generates prioritized,
actionable recommendations for the user.
"""
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_anthropic import ChatAnthropic

from ..core.config import settings
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class RecommendationAgent:
    """
    Recommendation Agent for generating actionable recommendations.

    Takes diagnosis results and generates prioritized recommendations
    based on root causes and severity.
    """

    def __init__(self):
        """Initialize Recommendation Agent."""
        self.llm = ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.3,  # Lower temperature for faster, more consistent recommendations
        )

    async def generate_recommendations(
        self,
        diagnosis: Dict[str, Any],
        agent_results: Dict[str, Any],
        query: str
    ) -> Dict[str, Any]:
        """
        Generate actionable recommendations.

        Args:
            diagnosis: Diagnosis results with root causes
            agent_results: Results from specialist agents
            query: Original user query

        Returns:
            Dict with:
            - recommendations: List[Dict] - Prioritized recommendations
            - confidence: float - Confidence in recommendations
            - action_plan: str - Summary action plan
        """
        import json

        # Extract context
        root_causes = diagnosis.get("root_causes", [])
        severity = diagnosis.get("severity", "medium")
        correlations = diagnosis.get("correlations", [])
        diagnosis_summary = diagnosis.get("summary", "")

        # Include key agent results for context (but keep it concise)
        agent_context = ""
        if agent_results:
            agent_summaries = []
            for agent_name, output in list(agent_results.items())[:2]:  # Limit to 2 agents for speed
                if hasattr(output, 'response') and output.response:
                    # Truncate to first 300 chars per agent to keep prompt short
                    response_preview = output.response[:300] + "..." if len(output.response) > 300 else output.response
                    agent_summaries.append(f"{agent_name}: {response_preview}")
            if agent_summaries:
                agent_context = f"\n\nAgent Findings:\n" + "\n".join(f"- {s}" for s in agent_summaries)

        # Build prompt (more concise for faster generation)
        recommendation_prompt = f"""You are a recommendation agent generating actionable recommendations for DV360 campaign optimization.

User Query: "{query}"

Diagnosis:
- Severity: {severity}
- Root Causes: {', '.join(root_causes[:5]) if root_causes else 'None identified'}{agent_context}

Task: Generate 3-4 prioritized, actionable recommendations that address root causes.

Format:
RECOMMENDATION 1:
Priority: [high/medium/low]
Action: [Specific action]
Reason: [Why this helps]
Expected Impact: [What improves]

(Continue for 3-4 recommendations)

CONFIDENCE: [0.0-1.0]
ACTION_PLAN: [2-3 sentence summary]

Your recommendations:"""

        try:
            messages = [
                SystemMessage(content="You are a recommendation expert for DV360 campaign optimization."),
                HumanMessage(content=recommendation_prompt)
            ]

            response = self.llm.invoke(messages)
            response_text = response.content.strip()

            logger.info("Recommendation LLM response", response_preview=response_text[:200])

            # Parse response
            recommendations = []
            confidence = 0.8
            action_plan = ""

            current_rec = None
            for line in response_text.split('\n'):
                line = line.strip()

                if line.startswith("RECOMMENDATION"):
                    if current_rec:
                        recommendations.append(current_rec)
                    current_rec = {}
                elif line.startswith("Priority:") and current_rec is not None:
                    priority = line.replace("Priority:", "").strip().lower()
                    current_rec["priority"] = priority if priority in ["high", "medium", "low"] else "medium"
                elif line.startswith("Action:") and current_rec is not None:
                    current_rec["action"] = line.replace("Action:", "").strip()
                elif line.startswith("Reason:") and current_rec is not None:
                    current_rec["reason"] = line.replace("Reason:", "").strip()
                elif line.startswith("Expected Impact:") and current_rec is not None:
                    current_rec["expected_impact"] = line.replace("Expected Impact:", "").strip()
                elif line.startswith("CONFIDENCE:"):
                    try:
                        conf_str = line.replace("CONFIDENCE:", "").strip()
                        confidence = float(conf_str)
                        confidence = max(0.0, min(1.0, confidence))
                    except ValueError:
                        pass
                elif line.startswith("ACTION_PLAN:"):
                    action_plan = line.replace("ACTION_PLAN:", "").strip()

            # Add last recommendation
            if current_rec and "action" in current_rec:
                recommendations.append(current_rec)

            # Ensure all recommendations have required fields
            recommendations = [
                rec for rec in recommendations
                if "action" in rec and "reason" in rec and "priority" in rec
            ]

            logger.info(
                "Recommendations generated",
                count=len(recommendations),
                confidence=confidence
            )

            return {
                "recommendations": recommendations,
                "confidence": confidence,
                "action_plan": action_plan or "Follow the recommendations in priority order",
                "raw_response": response_text
            }

        except Exception as e:
            logger.error("Recommendation generation failed", error_message=str(e))

            # Fallback: extract recommendations from agent responses
            fallback_recs = self._extract_recommendations_from_agents(agent_results)

            return {
                "recommendations": fallback_recs,
                "confidence": 0.6,
                "action_plan": "Review individual agent recommendations",
                "raw_response": None
            }

    def _extract_recommendations_from_agents(
        self,
        agent_results: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Extract recommendations from individual agent outputs."""
        recommendations = []

        for agent_name, output in agent_results.items():
            # Try to extract recommendations from metadata
            if hasattr(output, 'metadata') and 'recommendations' in output.metadata:
                agent_recs = output.metadata.get('recommendations', [])
                for rec in agent_recs[:2]:  # Limit to 2 per agent
                    if isinstance(rec, dict):
                        recommendations.append(rec)

        return recommendations[:5]  # Max 5 recommendations


# Global instance
recommendation_agent = RecommendationAgent()
