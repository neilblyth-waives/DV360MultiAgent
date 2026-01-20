"""
Diagnosis Agent - Analyzes results from multiple agents to find root causes.

This agent takes outputs from specialist agents and identifies patterns,
correlations, and root causes across different perspectives.
"""
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_anthropic import ChatAnthropic

from ..core.config import settings
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class DiagnosisAgent:
    """
    Diagnosis Agent for root cause analysis.

    Analyzes results from multiple specialist agents to identify
    patterns, correlations, and root causes.
    """

    def __init__(self):
        """Initialize Diagnosis Agent."""
        self.llm = ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.3,
        )

    async def diagnose(
        self,
        agent_results: Dict[str, Any],
        query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        gate_warnings: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze results from multiple agents.

        Args:
            agent_results: Dict of {agent_name: AgentOutput}
            query: Original user query
            conversation_history: Optional list of previous messages for context
            gate_warnings: Optional list of warnings from gate validation

        Returns:
            Dict with:
            - issues: List[str] - All issues identified
            - root_causes: List[str] - Root causes
            - severity: str - Overall severity (critical, high, medium, low)
            - correlations: List[str] - Cross-agent correlations
            - summary: str - Diagnosis summary
        """
        import json

        # Extract key information from each agent
        agent_summaries = {}
        all_issues = []

        for agent_name, output in agent_results.items():
            # Include full response for diagnosis (not truncated)
            # The LLM needs complete information to properly diagnose
            agent_summaries[agent_name] = {
                "response": output.response if output.response else "",
                "confidence": output.confidence,
                "tools_used": output.tools_used,
                "agent_name": output.agent_name if hasattr(output, 'agent_name') else agent_name
            }
            all_issues.extend(self._extract_issues_from_response(output.response))

        # Build context section
        context_sections = []
        
        # Add conversation history if available (truncated to last 3 messages for relevance)
        if conversation_history:
            recent_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
            context_sections.append("CONVERSATION CONTEXT (recent messages):")
            for msg in recent_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                # Truncate long messages
                if len(content) > 200:
                    content = content[:200] + "..."
                context_sections.append(f"- {role.upper()}: {content}")
        
        # Add gate warnings if available
        if gate_warnings:
            context_sections.append(f"\nGATE VALIDATION WARNINGS:")
            for warning in gate_warnings:
                context_sections.append(f"- {warning}")
        
        context_text = "\n".join(context_sections) if context_sections else "None"

        # Use LLM for diagnosis
        # Format agent results for better readability (full responses included)
        diagnosis_prompt = f"""You are a diagnosis agent analyzing results from multiple DV360 specialist agents.

User Query: "{query}"

{context_text}

Agent Results (Full Responses):
{json.dumps(agent_summaries, indent=2, ensure_ascii=False)}

Identified Issues:
{chr(10).join(f'- {issue}' for issue in all_issues) if all_issues else 'None identified'}

Your task:
1. Identify ROOT CAUSES (not just symptoms)
2. Find CORRELATIONS between different agent findings
3. Assess overall SEVERITY (critical/high/medium/low)
4. Provide a brief SUMMARY of the diagnosis

Respond in this format:

ROOT_CAUSES:
- [List root causes, one per line]

CORRELATIONS:
- [List correlations between agent findings]

SEVERITY: [critical/high/medium/low]

SUMMARY: [2-3 sentence summary of the diagnosis]

Your diagnosis:"""

        try:
            messages = [
                SystemMessage(content="You are a diagnosis expert analyzing multi-agent results."),
                HumanMessage(content=diagnosis_prompt)
            ]

            response = self.llm.invoke(messages)
            response_text = response.content.strip()

            logger.info("Diagnosis LLM response", response_preview=response_text[:200])

            # Parse response
            root_causes = []
            correlations = []
            severity = "medium"
            summary = ""

            current_section = None
            for line in response_text.split('\n'):
                line = line.strip()

                if line.startswith("ROOT_CAUSES:"):
                    current_section = "root_causes"
                elif line.startswith("CORRELATIONS:"):
                    current_section = "correlations"
                elif line.startswith("SEVERITY:"):
                    severity_text = line.replace("SEVERITY:", "").strip().lower()
                    if severity_text in ["critical", "high", "medium", "low"]:
                        severity = severity_text
                    current_section = None
                elif line.startswith("SUMMARY:"):
                    summary = line.replace("SUMMARY:", "").strip()
                    current_section = None
                elif line.startswith("-") and current_section:
                    item = line.lstrip("- ").strip()
                    if current_section == "root_causes":
                        root_causes.append(item)
                    elif current_section == "correlations":
                        correlations.append(item)

            logger.info(
                "Diagnosis complete",
                root_causes_count=len(root_causes),
                correlations_count=len(correlations),
                severity=severity
            )

            return {
                "issues": all_issues,
                "root_causes": root_causes,
                "severity": severity,
                "correlations": correlations,
                "summary": summary or "No clear diagnosis available",
                "raw_response": response_text
            }

        except Exception as e:
            logger.error("Diagnosis failed", error_message=str(e))
            return {
                "issues": all_issues,
                "root_causes": ["Unable to determine root causes"],
                "severity": "medium",
                "correlations": [],
                "summary": f"Diagnosis failed: {str(e)}",
                "raw_response": None
            }

    def _extract_issues_from_response(self, response: str) -> List[str]:
        """Extract issues from agent response text."""
        issues = []

        # Look for common issue indicators
        lines = response.split('\n')
        for line in lines:
            lower_line = line.lower()
            if any(keyword in lower_line for keyword in ["issue", "problem", "concern", "warning", "underperforming"]):
                issues.append(line.strip())

        return issues[:10]  # Limit to 10 issues


# Global instance
diagnosis_agent = DiagnosisAgent()
