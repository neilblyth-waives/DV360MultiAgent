# Class Architecture: BaseAgent and Inheritance Pattern

## Overview

All agents in the system inherit from `BaseAgent`, which provides common functionality. The `Orchestrator` is a special case that coordinates multiple specialist agents.

---

## BaseAgent: The Foundation

### What It Is

`BaseAgent` is an **abstract base class** (ABC) that provides shared functionality for all agents.

### Key Features

```python
class BaseAgent(ABC):
    def __init__(self, agent_name: str, description: str, tools: List[Any]):
        self.agent_name = agent_name      # Agent identifier
        self.description = description    # What agent does
        self.tools = tools or []          # Available tools
        self.llm = self._initialize_llm()  # LLM instance (Claude/GPT)
        self.graph = None                 # LangGraph (optional)
```

### What BaseAgent Provides

1. **LLM Initialization** (`_initialize_llm()`)
   - Automatically initializes Claude (Anthropic) or GPT (OpenAI)
   - Priority: Claude > GPT
   - Configures LangSmith tracing
   - Sets temperature to 0.1

2. **Common Attributes**
   - `self.agent_name`: Unique identifier
   - `self.description`: Agent purpose
   - `self.tools`: List of LangChain tools
   - `self.llm`: Ready-to-use LLM instance

3. **Helper Methods**
   - `_format_messages()`: Converts message dicts to LangChain messages
   - `_build_context()`: Builds context from memories and input
   - `invoke()`: Wrapper with logging and error handling

4. **Abstract Methods** (Must be implemented by subclasses)
   - `get_system_prompt()`: Returns agent-specific system prompt
   - `process()`: Main processing logic

---

## Inheritance Pattern

### Standard Pattern

All specialist agents follow this pattern:

```python
class SpecialistAgent(BaseAgent):
    def __init__(self):
        # Call parent constructor
        super().__init__(
            agent_name="specialist_name",
            description="What this agent does",
            tools=get_specialist_tools()  # Agent-specific tools
        )
    
    def get_system_prompt(self) -> str:
        # Return agent-specific prompt
        return "You are a specialist agent..."
    
    async def process(self, input_data: AgentInput) -> AgentOutput:
        # Implement agent logic
        # Query Snowflake, analyze data, return response
        return AgentOutput(...)
```

### Example: BudgetRiskAgent

```python
class BudgetRiskAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="budget_risk",
            description="Analyzes DV360 budget pacing and risk",
            tools=[],  # Tools loaded in process() method
        )
        # ✅ Gets self.llm automatically from BaseAgent
        # ✅ Gets self.agent_name = "budget_risk"
        # ✅ Gets logging infrastructure
    
    def get_system_prompt(self) -> str:
        # ✅ Must implement (abstract method)
        return "You are a DV360 Budget Risk Agent..."
    
    async def process(self, input_data: AgentInput) -> AgentOutput:
        # ✅ Must implement (abstract method)
        # Gets tools, creates ReAct agent, processes query
        tools = get_budget_agent_tools()
        react_agent = create_react_agent(model=self.llm, tools=tools)
        result = await react_agent.ainvoke({...})
        return AgentOutput(...)
```

### What Happens When You Create an Agent

```python
budget_agent = BudgetRiskAgent()
```

**Step-by-step**:

1. **`BudgetRiskAgent.__init__()` is called**
2. **`super().__init__()` is called** → `BaseAgent.__init__()`
   - Sets `self.agent_name = "budget_risk"`
   - Sets `self.description = "Analyzes DV360 budget pacing..."`
   - Sets `self.tools = []`
   - **Calls `self._initialize_llm()`** → Creates Claude/GPT instance
   - Sets `self.graph = None`
   - Logs initialization
3. **Returns to `BudgetRiskAgent.__init__()`**
   - Any additional initialization (none in this case)
4. **Agent is ready to use!**
   - `budget_agent.llm` → Ready-to-use LLM
   - `budget_agent.agent_name` → "budget_risk"
   - `budget_agent.process()` → Can be called

---

## Orchestrator: Special Case

### How It's Different

The `Orchestrator` inherits from `BaseAgent` but works differently:

```python
class Orchestrator(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="orchestrator",
            description="Main orchestrator...",
            tools=[],  # Orchestrator doesn't use tools directly
        )
        
        # ✅ Gets self.llm from BaseAgent (but doesn't use it directly)
        # ✅ Gets self.agent_name = "orchestrator"
        
        # 🆕 EXTRA: Registers specialist agents
        self.specialist_agents = {
            "budget_risk": budget_risk_agent,
            "performance_diagnosis": performance_agent_simple,
            # ... etc
        }
        
        # 🆕 EXTRA: Builds LangGraph workflow
        self.graph = self._build_graph()
```

### Key Differences

1. **Doesn't Use LLM Directly**
   - Orchestrator's `self.llm` is initialized but not used
   - Instead, it calls other agents that use their own LLMs
   - Routing agent, diagnosis agent, etc. have their own LLM instances

2. **Has a LangGraph Workflow**
   - `self.graph` is built at initialization
   - Complex multi-node workflow (routing → gate → agents → diagnosis → etc.)
   - Uses `self.graph.ainvoke(state)` to execute

3. **Coordinates Other Agents**
   - `self.specialist_agents` dictionary maps names to agent instances
   - Orchestrator invokes specialist agents: `agent.invoke(input_data)`

4. **Custom `process()` Method**
   - Doesn't use ReAct agent like specialist agents
   - Instead, executes LangGraph workflow
   - Manages state flow through multiple nodes

---

## Class Hierarchy Diagram

```
BaseAgent (Abstract Base Class)
│
├── Provides:
│   ├── self.llm (LLM instance)
│   ├── self.agent_name
│   ├── self.description
│   ├── self.tools
│   ├── _initialize_llm()
│   ├── invoke() (wrapper with logging)
│   └── Helper methods
│
├── Requires (Abstract Methods):
│   ├── get_system_prompt() → str
│   └── process() → AgentOutput
│
├── BudgetRiskAgent
│   ├── Inherits: Everything from BaseAgent
│   ├── Implements: get_system_prompt(), process()
│   └── Uses: ReAct agent with tools
│
├── PerformanceAgentSimple
│   ├── Inherits: Everything from BaseAgent
│   ├── Implements: get_system_prompt(), process()
│   └── Uses: ReAct agent with tools
│
├── AudienceAgentSimple
│   ├── Inherits: Everything from BaseAgent
│   ├── Implements: get_system_prompt(), process()
│   └── Uses: ReAct agent with tools
│
├── CreativeAgentSimple
│   ├── Inherits: Everything from BaseAgent
│   ├── Implements: get_system_prompt(), process()
│   └── Uses: ReAct agent with tools
│
└── Orchestrator (Special Case)
    ├── Inherits: Everything from BaseAgent
    ├── Implements: get_system_prompt(), process()
    ├── EXTRA: self.specialist_agents (registry)
    ├── EXTRA: self.graph (LangGraph workflow)
    └── Uses: LangGraph workflow, invokes specialist agents
```

---

## How Classes Work Together

### 1. Initialization Flow

```
User creates: orchestrator = Orchestrator()

Orchestrator.__init__()
  ↓
super().__init__() → BaseAgent.__init__()
  ├── Sets agent_name = "orchestrator"
  ├── Sets description = "..."
  ├── Sets tools = []
  ├── Calls _initialize_llm()
  │   └── Creates Claude/GPT instance → self.llm
  └── Sets self.graph = None
  ↓
Back to Orchestrator.__init__()
  ├── Creates self.specialist_agents = {...}
  └── Calls self._build_graph()
      └── Creates LangGraph workflow → self.graph
  ↓
orchestrator is ready!
```

### 2. Execution Flow

```
User calls: await orchestrator.invoke(AgentInput(...))

orchestrator.invoke() [from BaseAgent]
  ↓
orchestrator.process() [from Orchestrator]
  ├── Creates initial state
  ├── Calls self.graph.ainvoke(initial_state)
  │   ├── Executes routing node
  │   ├── Executes gate node
  │   ├── Executes invoke_agents node
  │   │   └── Calls specialist_agents["budget_risk"].invoke()
  │   │       └── budget_agent.process()
  │   │           └── Uses budget_agent.llm (from BaseAgent)
  │   ├── Executes diagnosis node
  │   └── ... etc
  └── Returns AgentOutput
```

### 3. Specialist Agent Execution

```
orchestrator calls: await budget_risk_agent.invoke(AgentInput(...))

budget_risk_agent.invoke() [from BaseAgent]
  ↓
budget_risk_agent.process() [from BudgetRiskAgent]
  ├── Gets tools: get_budget_agent_tools()
  ├── Creates ReAct agent: create_react_agent(model=self.llm, tools=tools)
  │   └── Uses self.llm (inherited from BaseAgent)
  ├── Executes ReAct agent
  └── Returns AgentOutput
```

---

## Key Concepts

### 1. Abstract Base Class (ABC)

**What It Means**:
- `BaseAgent` is abstract - you can't instantiate it directly
- Subclasses MUST implement abstract methods (`get_system_prompt()`, `process()`)
- Provides common functionality to all subclasses

**Why Use It**:
- **DRY (Don't Repeat Yourself)**: LLM initialization, logging, etc. written once
- **Consistency**: All agents have same interface (`invoke()`, `process()`)
- **Type Safety**: Ensures all agents implement required methods

### 2. Inheritance (`super().__init__()`)

**What It Does**:
- Calls parent class constructor
- Initializes base functionality before subclass-specific code

**Example**:
```python
class BudgetRiskAgent(BaseAgent):
    def __init__(self):
        super().__init__(...)  # ← Gets BaseAgent functionality
        # Now self.llm exists, self.agent_name exists, etc.
```

### 3. Method Overriding

**What It Means**:
- Subclasses override abstract methods to provide specific behavior
- `BaseAgent.process()` is abstract → each agent implements it differently

**Example**:
- `BudgetRiskAgent.process()`: Uses ReAct agent with Snowflake tools
- `Orchestrator.process()`: Executes LangGraph workflow

### 4. Composition vs Inheritance

**Orchestrator Uses Both**:

**Inheritance**:
- Inherits from `BaseAgent` → Gets LLM, logging, etc.

**Composition**:
- Has `self.specialist_agents` dictionary → Contains other agent instances
- Orchestrator doesn't inherit from specialist agents, it **uses** them

---

## Benefits of This Architecture

### 1. Code Reuse
- LLM initialization written once in `BaseAgent`
- Logging, error handling shared across all agents
- Common patterns (invoke wrapper) reused

### 2. Consistency
- All agents have same interface: `invoke(AgentInput) -> AgentOutput`
- Same logging format, same error handling
- Easy to swap agents or add new ones

### 3. Flexibility
- Each agent can implement `process()` differently
- Specialist agents use ReAct pattern
- Orchestrator uses LangGraph workflow
- Easy to add new agent types

### 4. Maintainability
- Change LLM initialization → Update `BaseAgent` → All agents benefit
- Add new common functionality → Add to `BaseAgent` → All agents get it
- Fix bug in `invoke()` → Fix in `BaseAgent` → All agents fixed

---

## Creating a New Agent

### Step 1: Create Class
```python
class MyNewAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="my_new_agent",
            description="What this agent does",
            tools=get_my_agent_tools(),
        )
```

### Step 2: Implement Abstract Methods
```python
    def get_system_prompt(self) -> str:
        return "You are a specialist agent that..."
    
    async def process(self, input_data: AgentInput) -> AgentOutput:
        # Your agent logic here
        # Use self.llm (already initialized!)
        # Use self.tools (already set!)
        return AgentOutput(...)
```

### Step 3: Use It
```python
my_agent = MyNewAgent()
output = await my_agent.invoke(AgentInput(message="...", user_id="..."))
```

**That's it!** You automatically get:
- ✅ LLM initialized (`self.llm`)
- ✅ Logging infrastructure
- ✅ Error handling (`invoke()` wrapper)
- ✅ Consistent interface

---

## Summary

**BaseAgent**:
- Abstract base class providing common functionality
- Initializes LLM, provides logging, error handling
- Requires subclasses to implement `get_system_prompt()` and `process()`

**Specialist Agents**:
- Inherit from `BaseAgent`
- Implement `process()` using ReAct pattern
- Use `self.llm` and `self.tools` from BaseAgent

**Orchestrator**:
- Inherits from `BaseAgent` (gets common functionality)
- Also has `self.specialist_agents` registry (composition)
- Also has `self.graph` LangGraph workflow
- Coordinates multiple specialist agents

**Pattern**:
- **Inheritance**: Get common functionality from BaseAgent
- **Composition**: Orchestrator uses specialist agents
- **Polymorphism**: All agents implement same interface (`invoke()`)

This architecture provides **code reuse**, **consistency**, and **flexibility** while keeping the codebase maintainable.

