"""
Comprehensive test suite for BaseAgent and related systems
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from codecollab.agents.base_agent import BaseAgent, AgentConfig, AgentState, AgentCapability
from codecollab.agents.memory import AgentMemory, MemoryType, MemoryPriority
from codecollab.agents.tools import ToolManager
from codecollab.core.communication_hub import CommunicationHub, Message, AgentRole, MessageType


# Concrete implementation for testing
class TestAgent(BaseAgent):
    """Test implementation of BaseAgent."""
    
    async def initialize(self):
        """Test agent initialization."""
        self.test_initialized = True
    
    async def cleanup(self):
        """Test agent cleanup."""
        self.test_cleaned_up = True
    
    async def handle_message(self, message: Message) -> str:
        """Handle test messages."""
        if "error" in message.content.lower():
            raise Exception("Simulated error")
        return f"Processed: {message.content}"
    
    async def get_capabilities_description(self) -> str:
        """Return test capabilities."""
        return "Test agent capable of processing messages and simulating errors"


class TestAgentIntegration:
    """Test suite for agent integration with all systems."""
    
    @pytest_asyncio.fixture
    async def communication_hub(self):
        """Create a test communication hub."""
        hub = CommunicationHub()
        await hub.start()
        yield hub
        await hub.stop()
    
    @pytest.fixture
    def agent_config(self):
        """Create test agent configuration."""
        return AgentConfig(
            name="TestAgent",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.CODE_GENERATION, AgentCapability.TESTING},
            max_memory_size=100,
            response_timeout=5.0,
            enable_learning=True
        )
    
    @pytest_asyncio.fixture
    async def test_agent(self, agent_config, communication_hub):
        """Create a test agent."""
        agent = TestAgent(agent_config, communication_hub)
        await agent.start()
        yield agent
        await agent.stop()
    
    @pytest.mark.asyncio
    async def test_agent_initialization(self, agent_config, communication_hub):
        """Test agent initialization process."""
        agent = TestAgent(agent_config, communication_hub)
        
        # Check initial state
        assert agent.state == AgentState.INITIALIZING
        assert agent.config.name == "TestAgent"
        assert agent.agent_id is not None
        
        # Start agent
        await agent.start()
        
        # Check post-initialization state
        assert agent.state == AgentState.IDLE
        assert hasattr(agent, 'test_initialized')
        assert agent.test_initialized
        
        await agent.stop()
        assert hasattr(agent, 'test_cleaned_up')
        assert agent.test_cleaned_up
    
    @pytest.mark.asyncio
    async def test_message_handling(self, test_agent):
        """Test basic message handling."""
        # Create test message
        message = Message(
            id="test-msg-1",
            sender=AgentRole.PRODUCT_MANAGER,
            recipient=AgentRole.DEVELOPER,
            message_type=MessageType.TASK_REQUEST,
            content="Process this test message",
            requires_response=True
        )
        
        # Handle message
        await test_agent._handle_message(message)
        
        # Check metrics
        assert test_agent.metrics.messages_received == 1
        assert test_agent.metrics.tasks_completed == 1
        assert len(test_agent.conversation_history) == 1
    
    @pytest.mark.asyncio
    async def test_error_handling(self, test_agent):
        """Test agent error handling."""
        # Create message that will cause error
        error_message = Message(
            id="error-msg-1",
            sender=AgentRole.PRODUCT_MANAGER,
            recipient=AgentRole.DEVELOPER,
            message_type=MessageType.TASK_REQUEST,
            content="This will cause an error",
            requires_response=True
        )
        
        # Handle message (should handle error gracefully)
        await test_agent._handle_message(error_message)
        
        # Check error was handled
        assert test_agent.metrics.tasks_failed == 1
        assert test_agent.last_error is not None
        assert test_agent.error_count == 1
    
    @pytest.mark.asyncio
    async def test_state_management(self, test_agent):
        """Test agent state transitions."""
        state_changes = []
        
        async def state_callback(old_state, new_state):
            state_changes.append((old_state, new_state))
        
        # Add state change callback
        test_agent.add_state_change_callback(state_callback)
        
        # Change states
        await test_agent._change_state(AgentState.PROCESSING)
        await test_agent._change_state(AgentState.WAITING_FOR_RESPONSE)
        await test_agent._change_state(AgentState.IDLE)
        
        # Check state changes were recorded
        assert len(state_changes) == 3
        assert state_changes[0] == (AgentState.IDLE, AgentState.PROCESSING)
        assert state_changes[1] == (AgentState.PROCESSING, AgentState.WAITING_FOR_RESPONSE)
        assert state_changes[2] == (AgentState.WAITING_FOR_RESPONSE, AgentState.IDLE)
    
    @pytest.mark.asyncio
    async def test_agent_status(self, test_agent):
        """Test agent status reporting."""
        status = test_agent.get_status()
        
        # Check status structure
        assert 'agent_id' in status
        assert 'name' in status
        assert 'role' in status
        assert 'state' in status
        assert 'capabilities' in status
        assert 'metrics' in status
        assert 'memory_usage' in status
        assert 'error_info' in status
        
        # Check values
        assert status['name'] == "TestAgent"
        assert status['role'] == "dev"
        assert status['state'] == "idle"
        assert len(status['capabilities']) == 2


class TestAgentMemoryIntegration:
    """Test memory system integration with agents."""
    
    @pytest.fixture
    def agent_memory(self):
        """Create test agent memory."""
        return AgentMemory("test-agent-123", max_size=50)
    
    @pytest.mark.asyncio
    async def test_memory_storage_and_retrieval(self, agent_memory):
        """Test basic memory operations."""
        # Store memories
        conv_id = await agent_memory.remember_conversation(
            "msg-1", "User asked about testing", "user",
            {"project": "test-suite"}
        )
        
        task_id = await agent_memory.remember_task_outcome(
            "task-1", "Test completed successfully", True,
            {"tests_passed": 10, "coverage": 95}
        )
        
        # Search memories
        results = await agent_memory.search_memories("testing", limit=5)
        assert len(results) >= 1
        
        # Check memory stats
        stats = agent_memory.get_memory_stats()
        assert stats['agent_id'] == "test-agent-123"
        assert stats['total_memories'] >= 2
    
    @pytest.mark.asyncio
    async def test_context_management(self, agent_memory):
        """Test context stack management."""
        # Set initial context
        agent_memory.set_context({"task": "coding", "file": "main.py"})
        assert agent_memory.current_context["task"] == "coding"
        
        # Push new context
        agent_memory.push_context({"task": "testing", "file": "test_main.py"})
        assert agent_memory.current_context["task"] == "testing"
        assert len(agent_memory.context_stack) == 1
        
        # Pop context
        old_context = agent_memory.pop_context()
        assert old_context["task"] == "testing"
        assert agent_memory.current_context["task"] == "coding"
    
    @pytest.mark.asyncio
    async def test_learning_patterns(self, agent_memory):
        """Test learning from success and failure patterns."""
        # Record success
        await agent_memory.remember_task_outcome(
            "success-task", "Task completed", True, {"approach": "methodical"}
        )
        
        # Record failure
        await agent_memory.remember_task_outcome(
            "failure-task", "Task failed", False, {"approach": "rushed"}
        )
        
        # Check patterns
        assert len(agent_memory.success_patterns) == 1
        assert len(agent_memory.failure_patterns) == 1
        
        # Test feedback learning
        await agent_memory.learn_from_feedback(
            "Good approach, but could be faster",
            {"task_type": "coding", "complexity": "medium"}
        )
        
        # Search for learning memories
        learning_results = await agent_memory.search_memories(
            "feedback", MemoryType.LEARNING
        )
        assert len(learning_results) >= 1


class TestToolIntegration:
    """Test tool system integration."""
    
    @pytest.fixture
    def tool_manager(self):
        """Create test tool manager."""
        return ToolManager("test-agent-tools")
    
    @pytest.mark.asyncio
    async def test_tool_execution(self, tool_manager):
        """Test tool execution and results."""
        # Test code analysis tool
        sample_code = "def hello(): print('Hello, World!')"
        
        result = await tool_manager.execute_tool(
            "code_analyzer",
            context={"task": "analysis"},
            code=sample_code,
            language="python"
        )
        
        assert result.is_success()
        assert result.tool_name == "code_analyzer"
        assert isinstance(result.result, dict)
        assert 'lines_of_code' in result.result
    
    @pytest.mark.asyncio
    async def test_multiple_tool_execution(self, tool_manager):
        """Test executing multiple tools in sequence."""
        sample_code = "def calculate(x, y): return x + y"
        
        # Execute multiple tools
        analysis_result = await tool_manager.execute_tool(
            "code_analyzer", code=sample_code
        )
        
        doc_result = await tool_manager.execute_tool(
            "doc_generator", content="Calculator function", doc_type="api"
        )
        
        test_result = await tool_manager.execute_tool(
            "test_generator", code=sample_code, test_framework="pytest"
        )
        
        # Check all succeeded
        assert analysis_result.is_success()
        assert doc_result.is_success()
        assert test_result.is_success()
        
        # Check execution history
        stats = tool_manager.get_usage_stats()
        assert stats['total_executions'] == 3
        assert stats['success_rate'] == 1.0
    
    def test_tool_recommendations(self, tool_manager):
        """Test tool recommendation system."""
        # Test context-based recommendations
        context1 = {"code": True, "language": "python"}
        recommendations1 = tool_manager.get_tool_recommendations(context1)
        assert "code_analyzer" in recommendations1
        
        context2 = {"documentation": True, "project": "api"}
        recommendations2 = tool_manager.get_tool_recommendations(context2)
        assert "doc_generator" in recommendations2
    
    def test_tool_registry(self, tool_manager):
        """Test tool registry functionality."""
        # Get available tools
        tools = tool_manager.get_available_tools()
        assert len(tools) >= 3  # Built-in tools
        
        # Check tool schemas
        for tool in tools:
            assert 'name' in tool
            assert 'description' in tool
            assert 'category' in tool
            assert 'parameters' in tool


class TestFullAgentIntegration:
    """Test full integration of all agent systems."""
    
    @pytest_asyncio.fixture
    async def full_system(self):
        """Set up complete agent system."""
        # Communication hub
        hub = CommunicationHub()
        await hub.start()
        
        # Agent config
        config = AgentConfig(
            name="FullTestAgent",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.CODE_GENERATION, AgentCapability.TESTING},
            enable_learning=True
        )
        
        # Create agent
        agent = TestAgent(config, hub)
        await agent.start()
        
        yield {
            'hub': hub,
            'agent': agent,
            'config': config
        }
        
        # Cleanup
        await agent.stop()
        await hub.stop()
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self, full_system):
        """Test complete end-to-end agent workflow."""
        agent = full_system['agent']
        hub = full_system['hub']
        
        # Simulate a complete workflow
        messages_received = []
        
        async def response_handler(message):
            messages_received.append(message)
        
        # Subscribe to responses
        hub.subscribe(AgentRole.PRODUCT_MANAGER, response_handler)
        
        # Send task request
        task_message = Message(
            id="workflow-test-1",
            sender=AgentRole.PRODUCT_MANAGER,
            recipient=AgentRole.DEVELOPER,
            message_type=MessageType.TASK_REQUEST,
            content="Generate tests for the login function",
            requires_response=True
        )
        
        await hub.send_message(task_message)
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Check agent processed the message
        assert agent.metrics.messages_received >= 1
        assert len(agent.conversation_history) >= 1
        
        # Check response was sent
        assert len(messages_received) >= 1
        response = messages_received[0]
        assert "Processed:" in response.content
    
    @pytest.mark.asyncio
    async def test_agent_collaboration(self, full_system):
        """Test agents working together through the hub."""
        hub = full_system['hub']
        
        # Create second agent
        config2 = AgentConfig(
            name="ReviewerAgent",
            role=AgentRole.REVIEWER,
            capabilities={AgentCapability.CODE_REVIEW}
        )
        
        reviewer = TestAgent(config2, hub)
        await reviewer.start()
        
        try:
            # Test collaboration via negotiation
            negotiation_id = await hub.start_negotiation(
                participants=[AgentRole.DEVELOPER, AgentRole.REVIEWER],
                topic="Code review standards",
                initial_data={"deadline": "2 days"}
            )
            
            # Wait for negotiation messages
            await asyncio.sleep(0.5)
            
            # Check both agents received negotiation messages
            dev_agent = full_system['agent']
            assert len(dev_agent.conversation_history) >= 1
            assert len(reviewer.conversation_history) >= 1
            
            # Check negotiation was created
            assert negotiation_id in hub.active_negotiations
            
        finally:
            await reviewer.stop()


# Performance tests
class TestAgentPerformance:
    """Performance tests for agent systems."""
    
    @pytest.mark.asyncio
    async def test_high_volume_messages(self):
        """Test agent performance with high message volume."""
        hub = CommunicationHub()
        await hub.start()
        
        config = AgentConfig(
            name="PerformanceAgent",
            role=AgentRole.DEVELOPER,
            capabilities={AgentCapability.CODE_GENERATION}
        )
        
        agent = TestAgent(config, hub)
        await agent.start()
        
        try:
            # Send many messages
            message_count = 50
            for i in range(message_count):
                message = Message(
                    id=f"perf-test-{i}",
                    sender=AgentRole.PRODUCT_MANAGER,
                    recipient=AgentRole.DEVELOPER,
                    message_type=MessageType.STATUS_UPDATE,
                    content=f"Performance test message {i}"
                )
                await hub.send_message(message)
            
            # Wait for processing
            await asyncio.sleep(2.0)
            
            # Check all messages were processed
            assert agent.metrics.messages_received == message_count
            assert agent.metrics.average_response_time < 1.0  # Should be fast
            
        finally:
            await agent.stop()
            await hub.stop()
    
    @pytest.mark.asyncio
    async def test_memory_performance(self):
        """Test memory system performance."""
        memory = AgentMemory("perf-test-agent", max_size=200)
        
        # Store many memories
        memory_count = 100
        for i in range(memory_count):
            await memory.remember(
                f"Test memory content {i}",
                MemoryType.FACT,
                MemoryPriority.MEDIUM,
                tags=[f"tag-{i % 10}"]
            )
        
        # Test search performance
        import time
        start_time = time.time()
        results = await memory.search_memories("Test", limit=20)
        search_time = time.time() - start_time
        
        assert len(results) <= 20
        assert search_time < 1.0  # Should be fast
        
        # Check memory stats
        stats = memory.get_memory_stats()
        assert stats['total_memories'] == memory_count


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"]) 