"""
Orchestrator - Main coordinator using RouteFlow architecture.

This orchestrator replaces the Chat Conductor and implements the full
RouteFlow architecture with routing, gate, diagnosis, early exit,
recommendation, and validation phases.
"""
from typing import Dict, Any
from uuid import UUID
import time
import asyncio

from langgraph.graph import StateGraph, END

from .base import BaseAgent
from .routing_agent import routing_agent
from .gate_node import gate_node
from .diagnosis_agent import diagnosis_agent
from .early_exit_node import early_exit_node
from .recommendation_agent import recommendation_agent
from .validation_agent import validation_agent

# Import specialist agents (simplified ReAct versions)
from .performance_agent_simple import performance_agent_simple
from .audience_agent_simple import audience_agent_simple
from .creative_agent_simple import creative_agent_simple
from .budget_risk_agent import budget_risk_agent
# Legacy agents (kept for backward compatibility)
from .delivery_agent_langgraph import delivery_agent_langgraph

from ..schemas.agent import AgentInput, AgentOutput
from ..schemas.agent_state import OrchestratorState, create_initial_orchestrator_state
from ..tools.memory_tool import memory_retrieval_tool
from ..core.telemetry import get_logger


logger = get_logger(__name__)


class Orchestrator(BaseAgent):
    """
    Orchestrator using RouteFlow architecture.

    Flow:
    1. routing → Intelligent LLM-based routing
    2. gate → Validation and business rules
    3. invoke_agents → Parallel specialist agent execution
    4. diagnosis → Root cause analysis
    5. early_exit_check → Conditional exit if no recommendations needed
    6. recommendation → Generate recommendations
    7. validation → Validate recommendations
    8. generate_response → Final response generation
    """

    def __init__(self):
        """Initialize Orchestrator."""
        super().__init__(
            agent_name="orchestrator",
            description="Main orchestrator for routing and coordinating specialist agents",
            tools=[],
        )

        # Registry of specialist agents (simplified ReAct versions)
        self.specialist_agents = {
            "performance_diagnosis": performance_agent_simple,  # IO-level metrics
            "audience_targeting": audience_agent_simple,        # Line item metrics
            "creative_inventory": creative_agent_simple,        # Creative name/size
            "budget_risk": budget_risk_agent,                   # Budget pacing
            "delivery_optimization": delivery_agent_langgraph,  # Legacy combined agent
        }

        # Build LangGraph
        self.graph = self._build_graph()

    def get_system_prompt(self) -> str:
        """Return system prompt."""
        from datetime import datetime
        current_date = datetime.now().strftime("%B %Y")
        current_year = datetime.now().year
        
        return f"""You are the Orchestrator for a DV360 analysis system using RouteFlow architecture.

IMPORTANT: The current date is {current_date} (year {current_year}). All date references should be interpreted relative to {current_year} unless explicitly stated otherwise."""

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph StateGraph."""
        workflow = StateGraph(OrchestratorState)

        # Add nodes
        workflow.add_node("routing", self._routing_node)
        workflow.add_node("gate", self._gate_node)
        workflow.add_node("invoke_agents", self._invoke_agents_node)
        workflow.add_node("diagnosis", self._diagnosis_node)
        workflow.add_node("recommendation", self._recommendation_node)
        workflow.add_node("validation", self._validation_node)
        workflow.add_node("generate_response", self._generate_response_node)

        # Set entry point
        workflow.set_entry_point("routing")

        # Flow
        workflow.add_edge("routing", "gate")

        # Conditional: gate validates or blocks
        workflow.add_conditional_edges(
            "gate",
            self._gate_decision,
            {
                "proceed": "invoke_agents",
                "block": "generate_response"  # Generate error response
            }
        )

        workflow.add_edge("invoke_agents", "diagnosis")

        # Conditional: early exit or continue
        workflow.add_conditional_edges(
            "diagnosis",
            self._early_exit_decision,
            {
                "exit": "generate_response",
                "continue": "recommendation"
            }
        )

        workflow.add_edge("recommendation", "validation")
        workflow.add_edge("validation", "generate_response")
        workflow.add_edge("generate_response", END)

        return workflow.compile()

    async def _routing_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Route query to appropriate specialist agents."""
        query = state["query"]

        logger.info("Routing query", query=query[:50])

        # Use routing agent
        routing_result = await routing_agent.route(query)

        return {
            "routing_decision": routing_result,
            "routing_confidence": routing_result.get("confidence", 0.0),
            "selected_agents": routing_result.get("selected_agents", []),
            "reasoning_steps": [
                f"Routing: selected {', '.join(routing_result.get('selected_agents', []))} "
                f"with confidence {routing_result.get('confidence', 0.0):.2f}"
            ]
        }

    def _gate_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Validate routing decision."""
        query = state["query"]
        selected_agents = state["selected_agents"]
        routing_confidence = state["routing_confidence"]

        logger.info("Gate validation", selected_agents=selected_agents)

        # Use gate node
        gate_result = gate_node.validate(
            query=query,
            selected_agents=selected_agents,
            routing_confidence=routing_confidence,
            user_id=state["user_id"]
        )

        return {
            "gate_result": gate_result,
            "reasoning_steps": [
                f"Gate: approved {len(gate_result.get('approved_agents', []))} agents, "
                f"{len(gate_result.get('warnings', []))} warnings"
            ]
        }

    def _gate_decision(self, state: OrchestratorState) -> str:
        """Decision: proceed or block?"""
        gate_result = state.get("gate_result", {})
        valid = gate_result.get("valid", False)

        if valid:
            logger.info("Gate decision: proceed")
            return "proceed"
        else:
            logger.warning("Gate decision: block", reason=gate_result.get("reason"))
            return "block"

    async def _invoke_agents_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Invoke approved specialist agents."""
        gate_result = state.get("gate_result", {})
        approved_agents = gate_result.get("approved_agents", [])
        query = state["query"]
        session_id = state.get("session_id")
        user_id = state["user_id"]

        logger.info("Invoking agents", agents=approved_agents)

        agent_results = {}
        agent_errors = {}

        for agent_name in approved_agents:
            agent = self.specialist_agents.get(agent_name)
            if not agent:
                logger.warning(f"Agent {agent_name} not found")
                agent_errors[agent_name] = "Agent not found"
                continue

            try:
                # Create agent input
                agent_input = AgentInput(
                    message=query,
                    session_id=session_id,
                    user_id=user_id
                )

                # Invoke agent
                agent_output = await agent.invoke(agent_input)
                agent_results[agent_name] = agent_output

                logger.info(f"Agent {agent_name} completed", confidence=agent_output.confidence)

            except Exception as e:
                logger.error(f"Agent {agent_name} failed", error_message=str(e))
                agent_errors[agent_name] = str(e)

        return {
            "agent_results": agent_results,
            "agent_errors": agent_errors,
            "reasoning_steps": [
                f"Invoked {len(agent_results)} agents successfully, "
                f"{len(agent_errors)} failed"
            ]
        }

    async def _diagnosis_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Analyze agent results to find root causes."""
        agent_results = state["agent_results"]
        query = state["query"]
        gate_result = state.get("gate_result", {})
        approved_agents = gate_result.get("approved_agents", [])

        # Optimization: Skip diagnosis for single-agent informational queries
        # Diagnosis is valuable for multi-agent scenarios but adds overhead for simple queries
        if len(approved_agents) == 1 and self._is_informational_query(query):
            logger.info("Skipping diagnosis for single-agent informational query")
            
            # Use agent response directly as diagnosis summary
            agent_name = approved_agents[0]
            agent_output = agent_results.get(agent_name)
            
            if agent_output:
                diagnosis = {
                    "summary": agent_output.response,
                    "severity": "low",
                    "root_causes": [],
                    "correlations": [],
                    "issues": [],
                    "raw_response": None
                }
            else:
                # Fallback if no agent output
                diagnosis = {
                    "summary": "Query processed successfully",
                    "severity": "low",
                    "root_causes": [],
                    "correlations": [],
                    "issues": [],
                    "raw_response": None
                }
            
            return {
                "diagnosis": diagnosis,
                "correlations": [],
                "severity_assessment": "low",
                "reasoning_steps": [
                    "Diagnosis skipped: Single-agent informational query"
                ]
            }

        logger.info("Running diagnosis")

        # Use diagnosis agent for multi-agent or complex queries
        diagnosis = await diagnosis_agent.diagnose(agent_results, query)

        return {
            "diagnosis": diagnosis,
            "correlations": diagnosis.get("correlations", []),
            "severity_assessment": diagnosis.get("severity", "medium"),
            "reasoning_steps": [
                f"Diagnosis: {len(diagnosis.get('root_causes', []))} root causes, "
                f"severity={diagnosis.get('severity')}"
            ]
        }

    def _is_informational_query(self, query: str) -> bool:
        """
        Check if query is informational (asking for information) vs action-oriented.
        
        Informational queries: "what is", "how is", "show me", "tell me about", "explain"
        Action-oriented queries: "optimize", "fix", "improve", "why is", "what's wrong"
        """
        query_lower = query.lower()
        informational_keywords = [
            "what is", "what are", "what was", "what will",
            "how is", "how are", "how was", "how will",
            "show me", "tell me", "explain", "describe",
            "list", "give me", "provide"
        ]
        
        action_keywords = [
            "optimize", "fix", "improve", "why is", "why are",
            "what's wrong", "what went wrong", "issue", "problem",
            "recommend", "suggest", "should", "need to"
        ]
        
        # Check for action keywords first (higher priority)
        if any(keyword in query_lower for keyword in action_keywords):
            return False
        
        # Check for informational keywords
        return any(keyword in query_lower for keyword in informational_keywords)

    def _early_exit_decision(self, state: OrchestratorState) -> str:
        """Decision: exit early or continue to recommendations?"""
        diagnosis = state["diagnosis"]
        agent_results = state["agent_results"]
        query = state["query"]

        # Check if we should exit early
        exit_decision = early_exit_node.should_exit_early(diagnosis, agent_results, query)

        should_exit = exit_decision.get("exit", False)

        if should_exit:
            logger.info("Early exit triggered", reason=exit_decision.get("reason"))
            # Store early exit response
            state["final_response"] = exit_decision.get("final_response") or diagnosis.get("summary", "")
            state["should_exit_early"] = True
            state["early_exit_reason"] = exit_decision.get("reason")
            return "exit"
        else:
            logger.info("Continuing to recommendations")
            return "continue"

    async def _recommendation_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Generate recommendations."""
        diagnosis = state["diagnosis"]
        agent_results = state["agent_results"]
        query = state["query"]

        logger.info("Generating recommendations")

        # Use recommendation agent
        rec_result = await recommendation_agent.generate_recommendations(
            diagnosis, agent_results, query
        )

        return {
            "recommendations": rec_result.get("recommendations", []),
            "recommendation_confidence": rec_result.get("confidence", 0.0),
            "reasoning_steps": [
                f"Generated {len(rec_result.get('recommendations', []))} recommendations "
                f"with confidence {rec_result.get('confidence', 0.0):.2f}"
            ]
        }

    def _validation_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Validate recommendations."""
        recommendations = state["recommendations"]
        diagnosis = state["diagnosis"]
        agent_results = state["agent_results"]

        logger.info("Validating recommendations", count=len(recommendations))

        # Use validation agent
        validation_result = validation_agent.validate_recommendations(
            recommendations, diagnosis, agent_results
        )

        return {
            "validation_result": validation_result,
            "validated_recommendations": validation_result.get("validated_recommendations", []),
            "validation_warnings": validation_result.get("warnings", []),
            "reasoning_steps": [
                f"Validation: {len(validation_result.get('validated_recommendations', []))} "
                f"recommendations validated, {len(validation_result.get('warnings', []))} warnings"
            ]
        }

    def _generate_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """Generate final response."""
        # Check if early exit
        if state.get("should_exit_early"):
            final_response = state.get("final_response", "")
            confidence = 0.8
        else:
            # Check if gate blocked
            gate_result = state.get("gate_result", {})
            if not gate_result.get("valid", True):
                final_response = f"Unable to process query: {gate_result.get('reason', 'Invalid request')}"
                confidence = 0.0
            else:
                # Normal response with recommendations
                final_response = self._build_response(state)
                confidence = state.get("recommendation_confidence", 0.8)

        logger.info("Generated final response", length=len(final_response), confidence=confidence)

        return {
            "final_response": final_response,
            "confidence": confidence,
            "reasoning_steps": ["Generated final response"]
        }

    def _build_response(self, state: OrchestratorState) -> str:
        """Build final response from state."""
        parts = []

        # Header
        query = state["query"]
        parts.append(f"# Analysis Results\n")
        parts.append(f"**Query**: {query}\n")

        # Diagnosis summary
        diagnosis = state.get("diagnosis", {})
        if diagnosis:
            parts.append(f"\n## Diagnosis")
            parts.append(f"**Severity**: {diagnosis.get('severity', 'N/A').upper()}")
            if diagnosis.get("summary"):
                parts.append(f"\n{diagnosis['summary']}\n")

            if diagnosis.get("root_causes"):
                parts.append(f"\n**Root Causes**:")
                for cause in diagnosis["root_causes"]:
                    parts.append(f"- {cause}")

        # Recommendations
        validated_recs = state.get("validated_recommendations", [])
        if validated_recs:
            parts.append(f"\n## Recommendations")
            for i, rec in enumerate(validated_recs, 1):
                priority = rec.get("priority", "medium").upper()
                action = rec.get("action", "N/A")
                reason = rec.get("reason", "N/A")
                parts.append(f"\n### {i}. [{priority}] {action}")
                parts.append(f"**Why**: {reason}")

        # Warnings
        validation_warnings = state.get("validation_warnings", [])
        if validation_warnings:
            parts.append(f"\n## Notes")
            for warning in validation_warnings[:3]:
                parts.append(f"- {warning}")

        return "\n".join(parts)

    async def process(self, input_data: AgentInput) -> AgentOutput:
        """Process a query through the orchestrator."""
        start_time = time.time()

        try:
            # Create initial state
            initial_state = create_initial_orchestrator_state(
                query=input_data.message,
                session_id=input_data.session_id,
                user_id=input_data.user_id
            )

            # Invoke graph (async because nodes are async)
            # NOTE: In LangSmith traces, this shows as "LangGraph" (framework name) but it IS the orchestrator
            # The trace structure is: LangGraph → routing → gate → invoke_agents → diagnosis → early_exit
            from langchain_core.runnables import RunnableConfig
            
            config = RunnableConfig(
                tags=["orchestrator", "routeflow"],
                metadata={"agent_name": "orchestrator", "query": input_data.message[:100]}
            )
            
            logger.info("Invoking orchestrator graph", query=input_data.message[:50])
            final_state = await self.graph.ainvoke(initial_state, config=config)

            execution_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Orchestrator completed",
                execution_time_ms=execution_time_ms,
                confidence=final_state.get("confidence", 0.0)
            )

            return AgentOutput(
                response=final_state["final_response"],
                agent_name=self.agent_name,
                reasoning="\n".join(final_state.get("reasoning_steps", [])),
                tools_used=final_state.get("tools_used", []),
                confidence=final_state.get("confidence", 0.0),
                metadata={
                    "execution_time_ms": execution_time_ms,
                    "agents_invoked": list(final_state.get("agent_results", {}).keys()),
                    "severity": final_state.get("severity_assessment", ""),
                    "recommendations_count": len(final_state.get("validated_recommendations", []))
                }
            )

        except Exception as e:
            logger.error("Orchestrator failed", error_message=str(e))
            execution_time_ms = int((time.time() - start_time) * 1000)

            return AgentOutput(
                response=f"I encountered an error processing your request: {str(e)}",
                agent_name=self.agent_name,
                reasoning=f"Error: {str(e)}",
                tools_used=[],
                confidence=0.0,
                metadata={"execution_time_ms": execution_time_ms, "error": str(e)}
            )


# Global instance
orchestrator = Orchestrator()
