"""
Audience Targeting Agent for analyzing DV360 audience segment performance.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
import time
import re

from .base import BaseAgent
from ..tools.snowflake_tool import snowflake_tool
from ..tools.memory_tool import memory_retrieval_tool
from ..tools.decision_logger import decision_logger
from ..schemas.agent import AgentInput, AgentOutput, AgentDecisionCreate
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class AudienceTargetingAgent(BaseAgent):
    """
    Audience Targeting Agent.

    Analyzes audience segment performance from Snowflake and provides:
    - Audience segment performance comparison
    - Targeting effectiveness analysis
    - Audience expansion recommendations
    - Segment optimization insights
    """

    def __init__(self):
        """Initialize Audience Targeting Agent."""
        super().__init__(
            agent_name="audience_targeting",
            description="Analyzes DV360 audience targeting effectiveness and provides optimization recommendations",
            tools=[],  # Tools called directly, not as LangChain tools
        )

    def get_system_prompt(self) -> str:
        """Return system prompt for the audience targeting agent."""
        return """You are a DV360 Audience Targeting Agent, an expert in audience segmentation and targeting optimization.

Your role:
- Analyze audience segment performance across campaigns
- Identify high-performing and underperforming segments
- Recommend audience expansion or refinement strategies
- Optimize targeting to improve campaign efficiency

Available data sources:
- Snowflake: DV360 audience performance data by segment
- Memory: Past learnings about audience targeting strategies

Analysis approach:
1. Retrieve relevant historical learnings about audience performance
2. Query audience segment data from Snowflake
3. Calculate performance metrics by segment (CTR, CPA, ROAS)
4. Compare segments to identify winners and losers
5. Provide actionable targeting recommendations

Output format:
- Clear summary of audience performance
- Top/bottom performing segments highlighted
- Key insights about targeting effectiveness
- Specific, actionable recommendations
- Segment-level data and comparisons

Be data-driven and focused on maximizing targeting efficiency."""

    async def process(self, input_data: AgentInput) -> AgentOutput:
        """
        Process an audience targeting analysis request.

        Args:
            input_data: User query about audience targeting

        Returns:
            AgentOutput with audience analysis and recommendations
        """
        start_time = time.time()
        tools_used = []
        reasoning_steps = []

        try:
            # Step 1: Parse the request to extract advertiser ID
            campaign_id, advertiser_id = self._extract_ids_from_query(input_data.message)

            reasoning_steps.append(f"Extracted IDs - Campaign: {campaign_id}, Advertiser: {advertiser_id}")

            # Step 2: Retrieve relevant memories
            session_memory = None
            if input_data.session_id:
                reasoning_steps.append("Retrieving relevant historical learnings")
                session_memory = await memory_retrieval_tool.retrieve_context(
                    query=input_data.message,
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    top_k=5,
                    min_similarity=0.6,
                )
                tools_used.append("memory_retrieval")
                reasoning_steps.append(
                    f"Retrieved {len(session_memory.relevant_learnings)} relevant learnings"
                )

            # Step 3: Query audience data from Snowflake
            reasoning_steps.append("Querying audience segment performance data")
            audience_data = await snowflake_tool.get_audience_performance(
                advertiser_id=advertiser_id or "Quiz",
                min_impressions=1000
            )
            tools_used.append("snowflake_query")
            reasoning_steps.append(f"Retrieved {len(audience_data)} audience segment records")

            # Step 4: Analyze the data (using Python for metrics)
            analysis = self._analyze_audience_performance(audience_data, session_memory)
            reasoning_steps.append("Completed audience targeting analysis")

            # Step 5: Generate recommendations (using Python for rule-based insights)
            recommendations = self._generate_recommendations(analysis, session_memory)
            reasoning_steps.append("Generated audience targeting recommendations")

            # Step 6: Use LLM to generate natural language response
            reasoning_steps.append("Generating natural language analysis with LLM")
            response = await self._generate_llm_response(
                query=input_data.message,
                audience_data=audience_data,
                analysis=analysis,
                recommendations=recommendations,
                session_memory=session_memory
            )
            tools_used.append("llm_analysis")
            reasoning_steps.append("LLM generated final response")

            # Step 7: Log decision
            execution_time_ms = int((time.time() - start_time) * 1000)

            if input_data.session_id:
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="audience_targeting_analysis",
                    input_data={
                        "query": input_data.message,
                        "campaign_id": campaign_id,
                        "advertiser_id": advertiser_id,
                    },
                    output_data={
                        "analysis": analysis,
                        "recommendations": recommendations,
                        "segments_analyzed": len(audience_data),
                    },
                    tools_used=tools_used,
                    reasoning="\n".join(reasoning_steps),
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=response,
                agent_name=self.agent_name,
                reasoning="\n".join(reasoning_steps),
                tools_used=tools_used,
                confidence=0.9,
                metadata={
                    "campaign_id": campaign_id,
                    "advertiser_id": advertiser_id,
                    "segments_analyzed": len(audience_data),
                    "learnings_used": len(session_memory.relevant_learnings) if session_memory else 0,
                },
            )

        except Exception as e:
            logger.error("Audience targeting analysis failed", error_message=str(e))

            # Log failed decision
            if input_data.session_id:
                execution_time_ms = int((time.time() - start_time) * 1000)
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="audience_targeting_analysis",
                    input_data={"query": input_data.message},
                    output_data={"error": str(e)},
                    tools_used=tools_used,
                    reasoning=f"Failed: {str(e)}",
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=f"I encountered an error analyzing audience targeting: {str(e)}",
                agent_name=self.agent_name,
                reasoning=f"Error: {str(e)}",
                tools_used=tools_used,
                confidence=0.0,
            )

    def _extract_ids_from_query(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """Extract campaign and advertiser IDs from query."""
        campaign_id = None
        advertiser_id = None

        # Try to extract campaign/insertion order ID
        campaign_patterns = [
            r"campaign\s+([A-Za-z0-9_-]+)",
            r"insertion[_\s]order\s+([A-Za-z0-9_-]+)",
            r"IO\s+([A-Za-z0-9_-]+)",
        ]

        for pattern in campaign_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                campaign_id = match.group(1)
                break

        # Try to extract advertiser ID
        advertiser_patterns = [
            r"advertiser\s+([A-Za-z0-9_-]+)",
        ]

        for pattern in advertiser_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                advertiser_id = match.group(1)
                break

        return campaign_id, advertiser_id

    def _analyze_audience_performance(
        self,
        audience_data: List[Dict[str, Any]],
        session_memory: Optional[Any]
    ) -> Dict[str, Any]:
        """
        Analyze audience segment performance.

        Args:
            audience_data: Audience segment data from Snowflake
            session_memory: Session memory with learnings

        Returns:
            Analysis dictionary with metrics and insights
        """
        if not audience_data:
            return {
                "segments": [],
                "summary": {},
                "issues": ["No audience data available"]
            }

        # Aggregate by line_item (which often represents audience segments)
        segment_metrics = {}

        for row in audience_data:
            segment = row.get("LINE_ITEM", "Unknown")

            if segment not in segment_metrics:
                segment_metrics[segment] = {
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                    "spend": 0,
                    "revenue": 0
                }

            segment_metrics[segment]["impressions"] += row.get("IMPRESSIONS", 0) or 0
            segment_metrics[segment]["clicks"] += row.get("CLICKS", 0) or 0
            segment_metrics[segment]["conversions"] += row.get("TOTAL_CONVERSIONS", 0) or 0
            segment_metrics[segment]["spend"] += row.get("SPEND", 0) or 0
            segment_metrics[segment]["revenue"] += row.get("TOTAL_REVENUE", 0) or 0

        # Calculate derived metrics for each segment
        segments = []
        for segment_name, metrics in segment_metrics.items():
            ctr = (metrics["clicks"] / metrics["impressions"] * 100) if metrics["impressions"] > 0 else 0
            cpc = metrics["spend"] / metrics["clicks"] if metrics["clicks"] > 0 else 0
            cpa = metrics["spend"] / metrics["conversions"] if metrics["conversions"] > 0 else 0
            roas = metrics["revenue"] / metrics["spend"] if metrics["spend"] > 0 else 0

            segments.append({
                "name": segment_name,
                "impressions": metrics["impressions"],
                "clicks": metrics["clicks"],
                "conversions": metrics["conversions"],
                "spend": metrics["spend"],
                "revenue": metrics["revenue"],
                "ctr": ctr,
                "cpc": cpc,
                "cpa": cpa,
                "roas": roas,
            })

        # Sort by impressions (largest first)
        segments.sort(key=lambda x: x["impressions"], reverse=True)

        # Calculate summary metrics
        total_impressions = sum(s["impressions"] for s in segments)
        total_clicks = sum(s["clicks"] for s in segments)
        total_spend = sum(s["spend"] for s in segments)

        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

        # Identify top/bottom performers
        top_segments = sorted([s for s in segments if s["clicks"] > 0], key=lambda x: x["ctr"], reverse=True)[:3]
        bottom_segments = sorted([s for s in segments if s["clicks"] > 0], key=lambda x: x["ctr"])[:3]

        # Identify issues
        issues = []
        if len(segments) == 0:
            issues.append("No audience segments found")

        low_performing = [s for s in segments if s["ctr"] < avg_ctr * 0.5 and s["impressions"] > 1000]
        if low_performing:
            issues.append(f"{len(low_performing)} segments performing significantly below average CTR")

        no_conversion_segments = [s for s in segments if s["conversions"] == 0 and s["clicks"] > 10]
        if no_conversion_segments:
            issues.append(f"{len(no_conversion_segments)} segments with clicks but no conversions")

        return {
            "segments": segments,
            "top_performers": top_segments,
            "bottom_performers": bottom_segments,
            "summary": {
                "total_segments": len(segments),
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_spend": total_spend,
                "avg_ctr": avg_ctr,
            },
            "issues": issues,
        }

    def _generate_recommendations(
        self,
        analysis: Dict[str, Any],
        session_memory: Optional[Any]
    ) -> list[Dict[str, str]]:
        """Generate audience targeting recommendations."""
        recommendations = []

        top_performers = analysis.get("top_performers", [])
        bottom_performers = analysis.get("bottom_performers", [])
        summary = analysis.get("summary", {})

        # Recommend scaling top performers
        if top_performers:
            top_segment = top_performers[0]
            recommendations.append({
                "priority": "high",
                "action": f"Scale budget for '{top_segment['name']}'",
                "reason": f"Top performing segment with {top_segment['ctr']:.2f}% CTR, significantly above average"
            })

        # Recommend pausing/optimizing bottom performers
        if bottom_performers:
            bottom_segment = bottom_performers[0]
            recommendations.append({
                "priority": "high",
                "action": f"Pause or optimize '{bottom_segment['name']}'",
                "reason": f"Underperforming segment with only {bottom_segment['ctr']:.2f}% CTR"
            })

        # Recommend audience expansion
        if len(analysis.get("segments", [])) < 5:
            recommendations.append({
                "priority": "medium",
                "action": "Expand audience targeting",
                "reason": "Limited number of audience segments - consider adding similar audiences or lookalikes"
            })

        # Recommend conversion tracking check
        no_conversion_count = len([s for s in analysis.get("segments", []) if s["conversions"] == 0 and s["clicks"] > 10])
        if no_conversion_count > 0:
            recommendations.append({
                "priority": "medium",
                "action": "Review conversion tracking for non-converting segments",
                "reason": f"{no_conversion_count} segments have clicks but no conversions"
            })

        return recommendations

    async def _generate_llm_response(
        self,
        query: str,
        audience_data: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        recommendations: list[Dict[str, str]],
        session_memory: Optional[Any]
    ) -> str:
        """
        Use LLM to generate natural language audience analysis.
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        import json

        # Build context for LLM
        system_prompt = self.get_system_prompt()

        # Summarize data for LLM
        data_summary = {
            "total_segments": len(analysis.get("segments", [])),
            "summary_metrics": analysis.get("summary", {}),
            "top_performers": analysis.get("top_performers", [])[:3],
            "bottom_performers": analysis.get("bottom_performers", [])[:3],
            "issues": analysis.get("issues", []),
        }

        # Build memory context
        memory_context = ""
        if session_memory and session_memory.relevant_learnings:
            memory_context = "\n\nRelevant past learnings:\n"
            for learning in session_memory.relevant_learnings[:3]:
                memory_context += f"- {learning.content} (confidence: {learning.confidence_score:.0%})\n"

        # Build recommendations summary
        recs_summary = "\n".join([
            f"- [{rec['priority']}] {rec['action']}: {rec['reason']}"
            for rec in recommendations[:5]
        ])

        user_prompt = f"""User Query: "{query}"

Audience Performance Data Summary:
{json.dumps(data_summary, indent=2)}

Detected Issues:
{chr(10).join(f'- {issue}' for issue in analysis.get('issues', []))}

Recommended Actions:
{recs_summary}
{memory_context}

Please generate a clear, actionable response that:
1. Summarizes overall audience targeting performance
2. Highlights top and bottom performing segments
3. Identifies any targeting concerns or opportunities
4. Provides specific, prioritized recommendations

Format your response in markdown with clear sections."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = self.llm.invoke(messages)
            return response.content

        except Exception as e:
            logger.error("LLM response generation failed, falling back to template", error_message=str(e))
            # Fallback to simple template
            return f"Audience analysis error: {str(e)}"


# Global instance
audience_targeting_agent = AudienceTargetingAgent()
