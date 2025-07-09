# codecollab/agents/base_agent.py
"""
BaseAgent - Abstract foundation for all CodeCollab AI agents
Provides common functionality for memory, communication, and lifecycle management
"""

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

from codecollab.core.communication_hub import (
    CommunicationHub, Message, AgentRole, MessageType, MessagePriority
)

# Set up logging
logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Possible states for an agent."""
    INITIALIZING = "initializing"
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING_FOR_RESPONSE = "waiting_for_response"
    COLLABORATING = "collaborating"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class AgentCapability(Enum):
    """Capabilities that agents can have."""
    REQUIREMENTS_ANALYSIS = "requirements_analysis"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    PROJECT_MANAGEMENT = "project_management"
    ARCHITECTURE_DESIGN = "architecture_design"
    DEBUGGING = "debugging"


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    role: AgentRole
    capabilities: Set[AgentCapability]
    max_memory_size: int = 1000
    response_timeout: float = 30.0
    retry_count: int = 3
    enable_learning: bool = True
    tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMetrics:
    """Performance metrics for an agent."""
    messages_sent: int = 0
    messages_received: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    average_response_time: float = 0.0
    uptime: float = 0.0
    last_activity: Optional[float] = None
    
    def update_response_time(self, response_time: float):
        """Update average response time with new measurement."""
        if self.messages_received == 0:
            self.average_response_time = response_time
        else:
            # Moving average
            self.average_response_time = (
                (self.average_response_time * (self.messages_received - 1) + response_time) 
                / self.messages_received
            )


class BaseAgent(ABC):
    """
    Abstract base class for all CodeCollab AI agents.
    
    Provides common functionality including:
    - Communication hub integration
    - Memory management
    - State tracking
    - Tool management
    - Error handling and recovery
    - Performance monitoring
    """
    
    def __init__(self, config: AgentConfig, communication_hub: CommunicationHub):
        """
        Initialize the base agent.
        
        Args:
            config: Agent configuration
            communication_hub: Communication system for inter-agent messaging
        """
        self.config = config
        self.communication_hub = communication_hub
        
        # Core state
        self.agent_id = str(uuid.uuid4())
        self.state = AgentState.INITIALIZING
        self.start_time = time.time()
        
        # Memory and history
        self.short_term_memory: List[Dict[str, Any]] = []
        self.conversation_history: List[Message] = []
        self.context_cache: Dict[str, Any] = {}
        
        # Performance tracking
        self.metrics = AgentMetrics()
        
        # Tool and capability management
        self.available_tools: Dict[str, Callable] = {}
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        
        # Event handlers
        self.message_handlers: Dict[MessageType, Callable] = {}
        self.state_change_callbacks: List[Callable] = []
        
        # Error handling
        self.last_error: Optional[Exception] = None
        self.error_count = 0
        
        logger.info(f"🤖 {self.config.name} ({self.config.role.value}) initialized with ID: {self.agent_id}")
    
    async def start(self):
        """Start the agent and subscribe to communication hub."""
        try:
            # Subscribe to communication hub
            self.communication_hub.subscribe(self.config.role, self._handle_message)
            
            # Initialize tools
            await self._initialize_tools()
            
            # Initialize memory system
            await self._initialize_memory()
            
            # Run agent-specific initialization
            await self.initialize()
            
            # Set state to idle
            await self._change_state(AgentState.IDLE)
            
            logger.info(f"✅ {self.config.name} started successfully")
            
        except Exception as e:
            await self._handle_error(e, "Failed to start agent")
            raise
    
    async def stop(self):
        """Stop the agent and cleanup resources."""
        try:
            await self._change_state(AgentState.SHUTDOWN)
            
            # Run agent-specific cleanup
            await self.cleanup()
            
            # Clear memory and cache
            self.short_term_memory.clear()
            self.context_cache.clear()
            
            # Update metrics
            self.metrics.uptime = time.time() - self.start_time
            
            logger.info(f"🛑 {self.config.name} stopped after {self.metrics.uptime:.2f} seconds")
            
        except Exception as e:
            logger.error(f"❌ Error stopping {self.config.name}: {e}")
    
    async def _handle_message(self, message: Message):
        """Handle incoming messages from the communication hub."""
        try:
            start_time = time.time()
            
            # Update metrics
            self.metrics.messages_received += 1
            self.metrics.last_activity = start_time
            
            # Add to conversation history
            self.conversation_history.append(message)
            
            # Trim conversation history if too long
            if len(self.conversation_history) > self.config.max_memory_size:
                self.conversation_history = self.conversation_history[-self.config.max_memory_size:]
            
            # Update state
            previous_state = self.state
            await self._change_state(AgentState.PROCESSING)
            
            try:
                # Route to specific handler based on message type
                if message.message_type in self.message_handlers:
                    response = await self.message_handlers[message.message_type](message)
                else:
                    # Default handling - delegate to agent implementation
                    response = await self.handle_message(message)
                
                # Send response if required
                if message.requires_response and response:
                    await self._send_response(message, response)
                
                # Update metrics
                response_time = time.time() - start_time
                self.metrics.update_response_time(response_time)
                self.metrics.tasks_completed += 1
                
            except Exception as e:
                self.metrics.tasks_failed += 1
                await self._handle_error(e, f"Error processing message: {message.id}")
                
                # Send error response if required
                if message.requires_response:
                    error_response = f"Error processing request: {str(e)}"
                    await self._send_response(message, error_response, MessageType.ERROR_REPORT)
            
            finally:
                # Return to previous state (or idle if was processing)
                target_state = AgentState.IDLE if previous_state == AgentState.PROCESSING else previous_state
                await self._change_state(target_state)
                
        except Exception as e:
            await self._handle_error(e, "Critical error in message handling")
    
    async def _send_response(self, original_message: Message, response_content: str, 
                           message_type: MessageType = MessageType.TASK_RESPONSE):
        """Send a response to a message."""
        response = Message(
            id=str(uuid.uuid4()),
            sender=self.config.role,
            recipient=original_message.sender,
            message_type=message_type,
            content=response_content,
            metadata={
                'response_to': original_message.id,
                'agent_id': self.agent_id,
                'processing_time': time.time()
            }
        )
        
        await self.communication_hub.send_message(response)
        self.metrics.messages_sent += 1
    
    async def _change_state(self, new_state: AgentState):
        """Change agent state and notify callbacks."""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            
            logger.debug(f"🔄 {self.config.name} state: {old_state.value} → {new_state.value}")
            
            # Notify state change callbacks
            for callback in self.state_change_callbacks:
                try:
                    await callback(old_state, new_state)
                except Exception as e:
                    logger.warning(f"⚠️ State change callback error: {e}")
    
    async def _handle_error(self, error: Exception, context: str):
        """Handle errors with logging and recovery."""
        self.last_error = error
        self.error_count += 1
        
        logger.error(f"❌ {self.config.name} error in {context}: {error}")
        
        # Update state to error if not already
        if self.state != AgentState.ERROR:
            await self._change_state(AgentState.ERROR)
        
        # Attempt recovery for non-critical errors
        if self.error_count <= self.config.retry_count:
            logger.info(f"🔄 Attempting recovery for {self.config.name} (attempt {self.error_count})")
            await asyncio.sleep(1.0 * self.error_count)  # Exponential backoff
            await self._change_state(AgentState.IDLE)
    
    async def _initialize_tools(self):
        """Initialize tools specified in configuration."""
        # This will be implemented in Block 3
        logger.debug(f"🔧 Initializing tools for {self.config.name}: {self.config.tools}")
    
    async def _initialize_memory(self):
        """Initialize memory system."""
        # This will be implemented in Block 2
        logger.debug(f"🧠 Initializing memory for {self.config.name}")
    
    def add_state_change_callback(self, callback: Callable):
        """Add a callback for state changes."""
        self.state_change_callbacks.append(callback)
    
    def register_message_handler(self, message_type: MessageType, handler: Callable):
        """Register a custom handler for specific message types."""
        self.message_handlers[message_type] = handler
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status and metrics."""
        return {
            'agent_id': self.agent_id,
            'name': self.config.name,
            'role': self.config.role.value,
            'state': self.state.value,
            'capabilities': [cap.value for cap in self.config.capabilities],
            'uptime': time.time() - self.start_time,
            'metrics': {
                'messages_sent': self.metrics.messages_sent,
                'messages_received': self.metrics.messages_received,
                'tasks_completed': self.metrics.tasks_completed,
                'tasks_failed': self.metrics.tasks_failed,
                'average_response_time': self.metrics.average_response_time,
                'last_activity': self.metrics.last_activity
            },
            'memory_usage': {
                'conversation_history': len(self.conversation_history),
                'short_term_memory': len(self.short_term_memory),
                'context_cache': len(self.context_cache)
            },
            'error_info': {
                'error_count': self.error_count,
                'last_error': str(self.last_error) if self.last_error else None
            }
        }
    
    # Abstract methods that concrete agents must implement
    
    @abstractmethod
    async def initialize(self):
        """Initialize agent-specific components. Called during startup."""
        pass
    
    @abstractmethod
    async def cleanup(self):
        """Cleanup agent-specific resources. Called during shutdown."""
        pass
    
    @abstractmethod
    async def handle_message(self, message: Message) -> Optional[str]:
        """
        Handle incoming messages. Concrete agents must implement this.
        
        Args:
            message: Incoming message to process
            
        Returns:
            Optional response content (None if no response needed)
        """
        pass
    
    @abstractmethod
    async def get_capabilities_description(self) -> str:
        """Return a description of what this agent can do."""
        pass 