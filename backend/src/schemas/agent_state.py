"""
State definitions for LangGraph agents.

These TypedDict classes define the state schema that flows through
agent nodes in LangGraph workflows.
"""
from typing import TypedDict, Optional, List, Dict, Any, Annotated
from uuid import UUID
from datetime import datetime
import operator


# ============================================================================
# Conductor State
# ============================================================================

class ConductorState(TypedDict):
    """
    State for the Chat Conductor agent (supervisor).

    Flows through: route → invoke_agents → aggregate → respond
    """
    # Input
    user_message: str
    session_id: Optional[UUID]
    user_id: str

    # Context
    session_history: List[Dict[str, Any]]  # Recent messages
    relevant_learnings: List[Dict[str, Any]]  # Semantic search results

    # Routing decision
    selected_agents: List[str]  # e.g., ["performance_diagnosis", "budget_pacing"]
    routing_reasoning: str  # LLM's explanation for routing choice

    # Agent execution
    agent_responses: Dict[str, str]  # {agent_name: response_text}
    agent_metadata: Dict[str, Dict[str, Any]]  # {agent_name: {exec_time, tools_used}}

    # Final output
    final_response: str
    confidence: float

    # Tracking
    tools_used: Annotated[List[str], operator.add]  # Aggregates across nodes
    reasoning_steps: Annotated[List[str], operator.add]  # Aggregates reasoning
    errors: List[str]  # Any errors encountered


class OrchestratorState(TypedDict):
    """
    State for the Orchestrator agent (RouteFlow architecture).

    Flows through: routing → gate → invoke_agents → diagnosis → early_exit_check →
                   recommendation → validation → respond
    """
    # Input
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Context
    session_history: List[Dict[str, Any]]
    relevant_learnings: List[Dict[str, Any]]

    # Routing phase
    routing_decision: Dict[str, Any]  # From routing_agent
    routing_confidence: float
    selected_agents: List[str]

    # Gate phase
    gate_result: Dict[str, Any]  # Validation result
    approved_agents: List[str]  # Agents approved by gate
    gate_warnings: List[str]

    # Agent execution phase
    agent_results: Dict[str, Any]  # {agent_name: AgentOutput}
    agent_errors: Dict[str, str]  # {agent_name: error_message}

    # Diagnosis phase
    diagnosis: Dict[str, Any]  # Root cause analysis
    correlations: List[str]  # Cross-agent correlations
    severity_assessment: str  # critical, high, medium, low

    # Early exit check
    should_exit_early: bool
    early_exit_reason: Optional[str]

    # Recommendation phase
    recommendations: List[Dict[str, str]]  # Consolidated recommendations
    recommendation_confidence: float

    # Validation phase
    validation_result: Dict[str, Any]
    validated_recommendations: List[Dict[str, str]]
    validation_warnings: List[str]

    # Final output
    final_response: str
    confidence: float

    # Tracking
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int


# ============================================================================
# Specialist Agent States
# ============================================================================

class PerformanceAgentState(TypedDict):
    """
    State for Performance Diagnosis Agent.

    Flows through: parse_query → check_confidence → [ask_clarification OR retrieve_memory] → query_data → analyze → recommend → respond
    """
    # Input
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Parsed entities
    campaign_id: Optional[str]
    advertiser_id: Optional[str]

    # Clarification handling
    needs_clarification: bool  # Whether we need to ask user for more info
    clarification_questions: List[str]  # Questions to ask user
    parse_confidence: float  # Confidence in query parsing (0-1)

    # Context
    session_history: List[Dict[str, Any]]
    relevant_learnings: List[Dict[str, Any]]

    # Data retrieved
    performance_data: Optional[List[Dict[str, Any]]]  # Raw Snowflake results
    data_summary: Optional[Dict[str, Any]]  # Aggregated metrics

    # Analysis results
    metrics: Optional[Dict[str, float]]  # CTR, ROAS, etc.
    trends: Optional[Dict[str, float]]  # % changes
    issues: List[str]  # Detected issues
    insights: List[str]  # Key insights

    # Recommendations
    recommendations: List[Dict[str, str]]  # [{priority, action, reason}]

    # Final output
    response: str
    confidence: float

    # Tracking
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int


class BudgetAgentState(TypedDict):
    """
    State for Budget Pacing Agent.

    Flows through: parse_query → retrieve_memory → query_data → analyze → recommend → respond
    """
    # Input
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Parsed entities
    campaign_id: Optional[str]
    advertiser_id: Optional[str]

    # Context
    session_history: List[Dict[str, Any]]
    relevant_learnings: List[Dict[str, Any]]

    # Data retrieved
    budget_data: Optional[Dict[str, Any]]  # Raw budget metrics

    # Analysis results
    budget_metrics: Optional[Dict[str, float]]  # spend_%, pacing_ratio, etc.
    pacing_status: Optional[str]  # "over_pacing", "under_pacing", "on_pace"
    forecast: Optional[Dict[str, float]]  # Projected spend, days to depletion
    issues: List[str]  # Detected budget issues
    insights: List[str]  # Key insights

    # Recommendations
    recommendations: List[Dict[str, str]]  # [{priority, action, reason}]

    # Final output
    response: str
    confidence: float

    # Tracking
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int


class AudienceAgentState(TypedDict):
    """
    State for Audience Targeting Agent.

    Flows through: parse_query → retrieve_memory → query_data → analyze → recommend → respond
    """
    # Input
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Parsed entities
    campaign_id: Optional[str]
    advertiser_id: Optional[str]

    # Context
    session_history: List[Dict[str, Any]]
    relevant_learnings: List[Dict[str, Any]]

    # Data retrieved
    audience_data: Optional[List[Dict[str, Any]]]  # Raw segment data

    # Analysis results
    segments: List[Dict[str, Any]]  # Analyzed segments with metrics
    top_performers: List[Dict[str, Any]]  # Top 3 segments
    bottom_performers: List[Dict[str, Any]]  # Bottom 3 segments
    summary_metrics: Optional[Dict[str, float]]  # Aggregate metrics
    issues: List[str]  # Detected targeting issues
    insights: List[str]  # Key insights

    # Recommendations
    recommendations: List[Dict[str, str]]  # [{priority, action, reason}]

    # Final output
    response: str
    confidence: float

    # Tracking
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int


class CreativeAgentState(TypedDict):
    """
    State for Creative Inventory Agent.

    Flows through: parse_query → retrieve_memory → query_data → analyze → recommend → respond
    """
    # Input
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Parsed entities
    campaign_id: Optional[str]
    advertiser_id: Optional[str]

    # Context
    session_history: List[Dict[str, Any]]
    relevant_learnings: List[Dict[str, Any]]

    # Data retrieved
    creative_data: Optional[List[Dict[str, Any]]]  # Raw creative data

    # Analysis results
    creatives: List[Dict[str, Any]]  # Analyzed creatives with metrics
    top_performers: List[Dict[str, Any]]  # Top 3 creatives
    bottom_performers: List[Dict[str, Any]]  # Bottom 3 creatives
    size_performance: List[Dict[str, Any]]  # Performance by size/format
    fatigue_indicators: List[str]  # Signs of creative fatigue
    summary_metrics: Optional[Dict[str, float]]  # Aggregate metrics
    issues: List[str]  # Detected creative issues
    insights: List[str]  # Key insights

    # Recommendations
    recommendations: List[Dict[str, str]]  # [{priority, action, reason}]

    # Final output
    response: str
    confidence: float

    # Tracking
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int


class DeliveryAgentState(TypedDict):
    """
    State for Delivery Agent (combines Creative + Audience).

    Flows through: parse_query → check_confidence → [ask_clarification OR retrieve_memory] → query_data → analyze → recommend → respond
    """
    # Input
    query: str
    session_id: Optional[UUID]
    user_id: str

    # Parsed entities
    campaign_id: Optional[str]
    advertiser_id: Optional[str]

    # Clarification handling
    needs_clarification: bool
    clarification_questions: List[str]
    parse_confidence: float  # 0-1

    # Context
    session_history: List[Dict[str, Any]]
    relevant_learnings: List[Dict[str, Any]]

    # Data retrieved
    creative_data: Optional[List[Dict[str, Any]]]  # Raw creative data
    audience_data: Optional[List[Dict[str, Any]]]  # Raw audience data
    data_summary: Optional[Dict[str, Any]]  # Combined data summary

    # Creative analysis
    creatives: List[Dict[str, Any]]  # Analyzed creatives with metrics
    creative_top_performers: List[Dict[str, Any]]  # Top 3 creatives
    creative_bottom_performers: List[Dict[str, Any]]  # Bottom 3 creatives
    size_performance: List[Dict[str, Any]]  # Performance by size/format
    fatigue_indicators: List[str]  # Signs of creative fatigue

    # Audience analysis
    audience_segments: List[Dict[str, Any]]  # Analyzed segments
    audience_top_performers: List[Dict[str, Any]]  # Top 3 segments
    audience_bottom_performers: List[Dict[str, Any]]  # Bottom 3 segments

    # Combined analysis
    summary_metrics: Optional[Dict[str, float]]  # Aggregate metrics
    issues: List[str]  # Detected delivery issues
    insights: List[str]  # Key insights
    correlations: List[str]  # Creative-audience correlations

    # Recommendations
    recommendations: List[Dict[str, str]]  # [{priority, action, reason}]

    # Final output
    response: str
    confidence: float

    # Tracking
    tools_used: Annotated[List[str], operator.add]
    reasoning_steps: Annotated[List[str], operator.add]
    execution_time_ms: int


# ============================================================================
# Helper Types
# ============================================================================

class AgentDecision(TypedDict):
    """
    Decision made by an agent node.

    Used for conditional routing in graphs.
    """
    next_step: str  # Name of next node to execute
    reason: str  # Why this decision was made
    confidence: float  # Confidence in this decision


class ToolCallResult(TypedDict):
    """
    Result from a tool invocation within an agent.
    """
    tool_name: str
    success: bool
    result: Any
    error: Optional[str]
    duration_ms: int


# ============================================================================
# State Reducers
# ============================================================================

def append_to_list(existing: List[Any], new: List[Any]) -> List[Any]:
    """
    Reducer function for list fields that should accumulate.

    Used with Annotated[List[T], append_to_list] to merge lists
    across multiple node updates.
    """
    return existing + new


def merge_dicts(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reducer function for dict fields that should merge.

    Used with Annotated[Dict[K, V], merge_dicts] to combine dicts
    across multiple node updates.
    """
    merged = existing.copy()
    merged.update(new)
    return merged


# ============================================================================
# State Initialization Helpers
# ============================================================================

def create_initial_conductor_state(
    user_message: str,
    session_id: Optional[UUID],
    user_id: str
) -> ConductorState:
    """Create initial state for Conductor agent."""
    return ConductorState(
        user_message=user_message,
        session_id=session_id,
        user_id=user_id,
        session_history=[],
        relevant_learnings=[],
        selected_agents=[],
        routing_reasoning="",
        agent_responses={},
        agent_metadata={},
        final_response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        errors=[],
    )


def create_initial_orchestrator_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> OrchestratorState:
    """Create initial state for Orchestrator agent (RouteFlow)."""
    return OrchestratorState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        session_history=[],
        relevant_learnings=[],
        routing_decision={},
        routing_confidence=0.0,
        selected_agents=[],
        gate_result={},
        approved_agents=[],
        gate_warnings=[],
        agent_results={},
        agent_errors={},
        diagnosis={},
        correlations=[],
        severity_assessment="",
        should_exit_early=False,
        early_exit_reason=None,
        recommendations=[],
        recommendation_confidence=0.0,
        validation_result={},
        validated_recommendations=[],
        validation_warnings=[],
        final_response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0,
    )


def create_initial_performance_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> PerformanceAgentState:
    """Create initial state for Performance Agent."""
    return PerformanceAgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        campaign_id=None,
        advertiser_id=None,
        needs_clarification=False,
        clarification_questions=[],
        parse_confidence=0.0,
        session_history=[],
        relevant_learnings=[],
        performance_data=None,
        data_summary=None,
        metrics=None,
        trends=None,
        issues=[],
        insights=[],
        recommendations=[],
        response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0,
    )


def create_initial_budget_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> BudgetAgentState:
    """Create initial state for Budget Agent."""
    return BudgetAgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        campaign_id=None,
        advertiser_id=None,
        session_history=[],
        relevant_learnings=[],
        budget_data=None,
        budget_metrics=None,
        pacing_status=None,
        forecast=None,
        issues=[],
        insights=[],
        recommendations=[],
        response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0,
    )


def create_initial_audience_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> AudienceAgentState:
    """Create initial state for Audience Agent."""
    return AudienceAgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        campaign_id=None,
        advertiser_id=None,
        session_history=[],
        relevant_learnings=[],
        audience_data=None,
        segments=[],
        top_performers=[],
        bottom_performers=[],
        summary_metrics=None,
        issues=[],
        insights=[],
        recommendations=[],
        response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0,
    )


def create_initial_creative_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> CreativeAgentState:
    """Create initial state for Creative Agent."""
    return CreativeAgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        campaign_id=None,
        advertiser_id=None,
        session_history=[],
        relevant_learnings=[],
        creative_data=None,
        creatives=[],
        top_performers=[],
        bottom_performers=[],
        size_performance=[],
        fatigue_indicators=[],
        summary_metrics=None,
        issues=[],
        insights=[],
        recommendations=[],
        response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0,
    )


def create_initial_delivery_state(
    query: str,
    session_id: Optional[UUID],
    user_id: str
) -> DeliveryAgentState:
    """Create initial state for Delivery Agent."""
    return DeliveryAgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        campaign_id=None,
        advertiser_id=None,
        needs_clarification=False,
        clarification_questions=[],
        parse_confidence=0.0,
        session_history=[],
        relevant_learnings=[],
        creative_data=None,
        audience_data=None,
        data_summary=None,
        creatives=[],
        creative_top_performers=[],
        creative_bottom_performers=[],
        size_performance=[],
        fatigue_indicators=[],
        audience_segments=[],
        audience_top_performers=[],
        audience_bottom_performers=[],
        summary_metrics=None,
        issues=[],
        insights=[],
        correlations=[],
        recommendations=[],
        response="",
        confidence=0.0,
        tools_used=[],
        reasoning_steps=[],
        execution_time_ms=0,
    )
