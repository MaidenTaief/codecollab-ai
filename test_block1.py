from codecollab.agents import BaseAgent, AgentState, AgentCapability
from codecollab.agents.base_agent import AgentConfig
from codecollab.core.communication_hub import AgentRole

config = AgentConfig(
    name='TestAgent',
    role=AgentRole.DEVELOPER,
    capabilities={AgentCapability.CODE_GENERATION}
)

print('✅ Block 1 working! AgentConfig created:', config.name)
print('✅ State enum:', AgentState.IDLE.value)
print('✅ Capability enum:', AgentCapability.CODE_GENERATION.value)
print('✅ BaseAgent class imported successfully') 