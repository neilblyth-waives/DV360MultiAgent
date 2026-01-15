"""
Performance Diagnosis Agent for analyzing DV360 campaign performance.
"""
from typing import Dict, Any, Optional
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


class PerformanceAgent(BaseAgent):
    """
    Performance Diagnosis Agent.

    Analyzes campaign performance data from Snowflake and provides:
    - Performance insights and trends
    - Issue identification (low CTR, high CPA, etc.)
    - Optimization recommendations
    - Contextual analysis using historical learnings
    """

    def __init__(self):
        """Initialize Performance Agent."""
        super().__init__(
            agent_name="performance_diagnosis",
            description="Analyzes DV360 campaign performance and provides optimization recommendations",
            tools=[],  # Tools called directly, not as LangChain tools
        )

    def get_system_prompt(self) -> str:
        """Return system prompt for the performance agent."""
        return """You are a DV360 Performance Diagnosis Agent, an expert in digital advertising campaign analysis.

Your role:
- Analyze campaign performance metrics (impressions, clicks, conversions, CTR, ROAS, cost)
- Identify performance issues and opportunities
- Provide data-driven optimization recommendations
- Consider historical learnings and patterns

Available data sources:
- Snowflake: DV360 campaign performance data
- Memory: Past learnings, patterns, and successful strategies

Analysis approach:
1. Retrieve relevant historical learnings about campaign performance
2. Query current campaign data from Snowflake
3. Calculate key metrics and identify trends
4. Compare against benchmarks and historical patterns
5. Identify specific issues (e.g., declining CTR, high CPA, budget pacing issues)
6. Provide actionable recommendations with expected impact

Output format:
- Clear summary of current performance
- Key metrics highlighted
- Issues identified with severity
- Specific, actionable recommendations
- Supporting data and reasoning

Be concise, data-driven, and actionable. Focus on insights that drive results."""

    async def process(self, input_data: AgentInput) -> AgentOutput:
        """
        Process a performance analysis request.

        Args:
            input_data: User query about campaign performance

        Returns:
            AgentOutput with analysis and recommendations
        """
        start_time = time.time()
        tools_used = []
        reasoning_steps = []

        try:
            # Step 1: Parse the request to extract campaign/advertiser IDs
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

            # Step 3: Query performance data from Snowflake
            reasoning_steps.append("Querying campaign performance data")
            performance_data = await snowflake_tool.get_campaign_performance(
                insertion_order=campaign_id,  # campaign_id maps to insertion_order in Snowflake
                advertiser=advertiser_id,  # advertiser_id maps to advertiser parameter
                limit=30  # Last 30 days
            )
            tools_used.append("snowflake_query")
            reasoning_steps.append(f"Retrieved {len(performance_data)} days of performance data")

            # Step 4: Analyze the data (using Python for metrics)
            analysis = self._analyze_performance(performance_data, session_memory)
            reasoning_steps.append("Completed performance analysis")

            # Step 5: Generate recommendations (using Python for rule-based insights)
            recommendations = self._generate_recommendations(analysis, session_memory)
            reasoning_steps.append("Generated optimization recommendations")

            # Step 6: Use LLM to generate natural language response
            reasoning_steps.append("Generating natural language analysis with LLM")
            response = await self._generate_llm_response(
                query=input_data.message,
                performance_data=performance_data,
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
                    decision_type="performance_analysis",
                    input_data={
                        "query": input_data.message,
                        "campaign_id": campaign_id,
                        "advertiser_id": advertiser_id,
                    },
                    output_data={
                        "analysis": analysis,
                        "recommendations": recommendations,
                        "data_points": len(performance_data),
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
                    "data_points": len(performance_data),
                    "learnings_used": len(session_memory.relevant_learnings) if session_memory else 0,
                },
            )

        except Exception as e:
            logger.error("Performance analysis failed", error_message=str(e))

            # Log failed decision
            if input_data.session_id:
                execution_time_ms = int((time.time() - start_time) * 1000)
                decision = AgentDecisionCreate(
                    session_id=input_data.session_id,
                    agent_name=self.agent_name,
                    decision_type="performance_analysis",
                    input_data={"query": input_data.message},
                    output_data={"error": str(e)},
                    tools_used=tools_used,
                    reasoning=f"Failed: {str(e)}",
                    execution_time_ms=execution_time_ms,
                )
                await decision_logger.log_decision(decision)

            return AgentOutput(
                response=f"I encountered an error analyzing campaign performance: {str(e)}",
                agent_name=self.agent_name,
                reasoning=f"Error: {str(e)}",
                tools_used=tools_used,
                confidence=0.0,
            )

    def _extract_ids_from_query(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract campaign ID and advertiser ID from query.

        Args:
            query: User query

        Returns:
            Tuple of (campaign_id, advertiser_id)
        """
        campaign_id = None
        advertiser_id = None

        # Look for campaign ID patterns
        campaign_match = re.search(r'campaign[_\s]+(?:id[:\s]+)?(\d+)', query, re.IGNORECASE)
        if campaign_match:
            campaign_id = campaign_match.group(1)

        # Look for advertiser ID patterns
        advertiser_match = re.search(r'advertiser[_\s]+(?:id[:\s]+)?(\d+)', query, re.IGNORECASE)
        if advertiser_match:
            advertiser_id = advertiser_match.group(1)

        return campaign_id, advertiser_id

    def _analyze_performance(
        self,
        data: list[Dict[str, Any]],
        session_memory: Optional[Any]
    ) -> Dict[str, Any]:
        """
        Analyze performance data and identify issues.

        Args:
            data: Performance data from Snowflake
            session_memory: Historical learnings

        Returns:
            Analysis dictionary with metrics and issues
        """
        if not data:
            return {
                "summary": "No performance data available",
                "metrics": {},
                "issues": ["No data found for the specified campaign"],
                "trends": {},
            }

        # Calculate aggregate metrics
        total_impressions = sum(row.get("IMPRESSIONS", 0) or 0 for row in data)
        total_clicks = sum(row.get("CLICKS", 0) or 0 for row in data)
        total_conversions = sum(row.get("CONVERSIONS", 0) or 0 for row in data)
        total_cost = sum(row.get("COST", 0) or 0 for row in data)
        total_revenue = sum(row.get("REVENUE", 0) or 0 for row in data)

        # Calculate key metrics
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        avg_cpc = (total_cost / total_clicks) if total_clicks > 0 else 0
        avg_cpa = (total_cost / total_conversions) if total_conversions > 0 else 0
        roas = (total_revenue / total_cost) if total_cost > 0 else 0

        metrics = {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "conversions": total_conversions,
            "cost": total_cost,
            "revenue": total_revenue,
            "ctr": avg_ctr,
            "cpc": avg_cpc,
            "cpa": avg_cpa,
            "roas": roas,
        }

        # Identify issues based on benchmarks
        issues = []
        if avg_ctr < 0.1:
            issues.append("CTR below industry benchmark (0.1%) - creative or targeting may need optimization")
        if roas < 1.0 and total_revenue > 0:
            issues.append("ROAS below 1.0 - campaign is not profitable")
        if total_conversions == 0 and total_clicks > 100:
            issues.append("No conversions despite significant clicks - check conversion tracking")

        # Analyze trends (last 7 days vs previous 7 days)
        trends = self._calculate_trends(data)

        return {
            "summary": f"Analyzed {len(data)} days of performance data",
            "metrics": metrics,
            "issues": issues,
            "trends": trends,
        }

    def _calculate_trends(self, data: list[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate week-over-week trends.

        Args:
            data: Performance data sorted by date DESC

        Returns:
            Dictionary of trend percentages
        """
        if len(data) < 14:
            return {"note": "Insufficient data for trend analysis"}

        # Split into recent week and previous week
        recent_week = data[:7]
        previous_week = data[7:14]

        def sum_metric(rows, metric):
            return sum(row.get(metric, 0) or 0 for row in rows)

        recent_impr = sum_metric(recent_week, "IMPRESSIONS")
        prev_impr = sum_metric(previous_week, "IMPRESSIONS")

        recent_clicks = sum_metric(recent_week, "CLICKS")
        prev_clicks = sum_metric(previous_week, "CLICKS")

        recent_conv = sum_metric(recent_week, "CONVERSIONS")
        prev_conv = sum_metric(previous_week, "CONVERSIONS")

        def calc_change(current, previous):
            if previous == 0:
                return 0.0
            return ((current - previous) / previous) * 100

        return {
            "impressions_change": calc_change(recent_impr, prev_impr),
            "clicks_change": calc_change(recent_clicks, prev_clicks),
            "conversions_change": calc_change(recent_conv, prev_conv),
        }

    def _generate_recommendations(
        self,
        analysis: Dict[str, Any],
        session_memory: Optional[Any]
    ) -> list[Dict[str, str]]:
        """
        Generate optimization recommendations based on analysis.

        Args:
            analysis: Performance analysis
            session_memory: Historical learnings

        Returns:
            List of recommendations
        """
        recommendations = []
        issues = analysis.get("issues", [])
        metrics = analysis.get("metrics", {})

        # Generate recommendations based on issues
        if any("CTR" in issue for issue in issues):
            recommendations.append({
                "priority": "high",
                "action": "Test new creative variations",
                "reason": "Low CTR indicates creative fatigue or poor ad relevance",
                "expected_impact": "10-30% CTR improvement",
            })
            recommendations.append({
                "priority": "high",
                "action": "Refine audience targeting",
                "reason": "Low engagement may indicate incorrect audience",
                "expected_impact": "15-25% CTR improvement",
            })

        if any("ROAS" in issue for issue in issues):
            recommendations.append({
                "priority": "critical",
                "action": "Review conversion tracking and attribution",
                "reason": "Negative ROAS requires immediate attention",
                "expected_impact": "Identify tracking issues or unprofitable segments",
            })

        if any("conversion" in issue.lower() for issue in issues):
            recommendations.append({
                "priority": "high",
                "action": "Verify conversion tags are firing correctly",
                "reason": "Clicks without conversions suggests tracking issues",
                "expected_impact": "Accurate conversion attribution",
            })

        # Add memory-based recommendations
        if session_memory and session_memory.relevant_learnings:
            for learning in session_memory.relevant_learnings[:2]:
                if learning.learning_type == "pattern":
                    recommendations.append({
                        "priority": "medium",
                        "action": f"Apply past learning: {learning.content}",
                        "reason": f"Similar situations showed {learning.confidence_score:.0%} success rate",
                        "expected_impact": "Based on historical patterns",
                    })

        # Default recommendation if no issues
        if not recommendations:
            recommendations.append({
                "priority": "low",
                "action": "Continue monitoring performance",
                "reason": "Campaign is performing within acceptable ranges",
                "expected_impact": "Maintain current performance",
            })

        return recommendations

    def _format_response(
        self,
        analysis: Dict[str, Any],
        recommendations: list[Dict[str, str]]
    ) -> str:
        """
        Format analysis and recommendations into readable response.

        Args:
            analysis: Performance analysis
            recommendations: List of recommendations

        Returns:
            Formatted response string
        """
        parts = []

        # Summary
        parts.append("# Campaign Performance Analysis")
        parts.append("")
        parts.append(analysis["summary"])
        parts.append("")

        # Key Metrics
        metrics = analysis.get("metrics", {})
        if metrics:
            parts.append("## Key Metrics")
            parts.append(f"- **Impressions**: {metrics.get('impressions', 0):,.0f}")
            parts.append(f"- **Clicks**: {metrics.get('clicks', 0):,.0f}")
            parts.append(f"- **Conversions**: {metrics.get('conversions', 0):,.0f}")
            parts.append(f"- **CTR**: {metrics.get('ctr', 0):.2f}%")
            parts.append(f"- **CPC**: ${metrics.get('cpc', 0):.2f}")
            parts.append(f"- **CPA**: ${metrics.get('cpa', 0):.2f}")
            parts.append(f"- **ROAS**: {metrics.get('roas', 0):.2f}x")
            parts.append("")

        # Trends
        trends = analysis.get("trends", {})
        if trends and "note" not in trends:
            parts.append("## Week-over-Week Trends")
            parts.append(f"- Impressions: {trends.get('impressions_change', 0):+.1f}%")
            parts.append(f"- Clicks: {trends.get('clicks_change', 0):+.1f}%")
            parts.append(f"- Conversions: {trends.get('conversions_change', 0):+.1f}%")
            parts.append("")

        # Issues
        issues = analysis.get("issues", [])
        if issues:
            parts.append("## Issues Identified")
            for issue in issues:
                parts.append(f"- ⚠️ {issue}")
            parts.append("")

        # Recommendations
        if recommendations:
            parts.append("## Recommendations")
            for i, rec in enumerate(recommendations, 1):
                priority = rec['priority'].upper()
                parts.append(f"### {i}. {rec['action']} [{priority}]")
                parts.append(f"**Reason**: {rec['reason']}")
                parts.append(f"**Expected Impact**: {rec['expected_impact']}")
                parts.append("")

        return "\n".join(parts)

    async def _generate_llm_response(
        self,
        query: str,
        performance_data: list[Dict[str, Any]],
        analysis: Dict[str, Any],
        recommendations: list[Dict[str, str]],
        session_memory: Optional[Any]
    ) -> str:
        """
        Use LLM to generate natural language analysis and recommendations.

        Args:
            query: Original user query
            performance_data: Raw performance data
            analysis: Python-generated analysis
            recommendations: Python-generated recommendations
            session_memory: Session memory context

        Returns:
            Natural language response from LLM
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        import json

        # Build context for LLM
        system_prompt = self.get_system_prompt()

        # Summarize data for LLM (don't send all 30 days, just summary)
        data_summary = {
            "total_days": len(performance_data),
            "key_metrics": analysis.get("metrics", {}),
            "trends": analysis.get("trends", {}),
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

Performance Data Summary:
{json.dumps(data_summary, indent=2)}

Detected Issues:
{chr(10).join(f'- {issue}' for issue in analysis.get('issues', []))}

Recommended Actions:
{recs_summary}
{memory_context}

Please generate a clear, actionable response that:
1. Summarizes the campaign's current performance
2. Explains key trends and metrics
3. Identifies any issues or concerns
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
            # Fallback to old template method if LLM fails
            return self._format_response(analysis, recommendations)


# Global instance
performance_agent = PerformanceAgent()
