"""Communication Hub - Main implementation for CodeCollab AI (Phase 1)

This file will contain the CommunicationHub, Message, AgentRole, and MessageType classes.
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Callable, Any, cast
from dataclasses import dataclass, asdict, field
from enum import Enum
from datetime import datetime
import logging
import typing

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Defines the roles agents can take in the system."""
    PRODUCT_MANAGER = "pm"
    DEVELOPER = "dev" 
    REVIEWER = "reviewer"
    TESTER = "tester"
    ORCHESTRATOR = "orchestrator"


class MessageType(Enum):
    """Types of messages that can be sent between agents."""
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    COLLABORATION_REQUEST = "collaboration_request"
    STATUS_UPDATE = "status_update"
    ERROR_REPORT = "error_report"
    NEGOTIATION = "negotiation"
    CONSENSUS = "consensus"


class MessagePriority(Enum):
    """Message priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Message:
    """Core message structure for agent communication."""
    sender: AgentRole
    recipient: AgentRole
    message_type: MessageType
    content: str
    id: Optional[str] = None
    priority: MessagePriority = MessagePriority.MEDIUM
    timestamp: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)  # Always dict, never None
    requires_response: bool = False
    conversation_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.conversation_id is None:
            self.conversation_id = str(uuid.uuid4())
        # No metadata check needed - it's always a dict
    
    def to_dict(self) -> Dict:
        """Convert message to dictionary for serialization."""
        return {
            **asdict(self),
            'sender': self.sender.value,
            'recipient': self.recipient.value, 
            'message_type': self.message_type.value,
            'priority': self.priority.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Message':
        """Create message from dictionary."""
        # Bulletproof metadata handling with assert + cast
        raw_metadata = data.get('metadata')
        meta = raw_metadata if isinstance(raw_metadata, dict) else {}
        assert meta is not None and isinstance(meta, dict), "metadata must be a dict"
        meta = cast(Dict[str, Any], meta)  # Tell type checker: this is definitely Dict[str, Any]
        if meta is None:
            meta = {}
        return cls(
            id=data['id'],
            sender=AgentRole(data['sender']),
            recipient=AgentRole(data['recipient']),
            message_type=MessageType(data['message_type']),
            content=data['content'],
            priority=MessagePriority(data['priority']),
            timestamp=data['timestamp'],
            metadata=meta,  # Type checker now 100% convinced this is Dict[str, Any]
            requires_response=data.get('requires_response', False),
            conversation_id=data.get('conversation_id')
        )

@dataclass
class ConversationThread:
    """Tracks a conversation between agents."""
    id: str
    participants: List[AgentRole]
    messages: List[Message]
    created_at: float
    status: str = "active"  # active, completed, archived
    
    def add_message(self, message: Message):
        """Add a message to the conversation."""
        message.conversation_id = self.id
        self.messages.append(message)
    
    def get_context(self, limit: int = 10) -> List[Message]:
        """Get recent messages for context."""
        return self.messages[-limit:]


class CommunicationHub:
    """
    Central communication system for CodeCollab AI agents.
    
    Features:
    - Asynchronous message routing
    - Message queuing and prioritization  
    - Conversation tracking
    - Event-driven architecture
    - Message persistence
    - Performance monitoring
    """
    
    def __init__(self):
        # Message routing
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.subscribers: Dict[AgentRole, Callable] = {}
        self.broadcast_subscribers: List[Callable] = []
        
        # Conversation management
        self.conversations: Dict[str, ConversationThread] = {}
        self.active_negotiations: Dict[str, Dict] = {}
        
        # Message history and analytics
        self.message_history: List[Message] = []
        self.delivery_stats: Dict[str, int] = {
            'total_sent': 0,
            'total_delivered': 0,
            'total_failed': 0
        }
        
        # System state
        self.is_running = False
        self.processing_task = None
        
        logger.info("🚀 Communication Hub initialized")

    async def start(self):
        """Start the communication hub message processing."""
        if self.is_running:
            return
            
        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_messages())
        logger.info("📡 Communication Hub started")
    
    async def stop(self):
        """Stop the communication hub."""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        logger.info("📡 Communication Hub stopped")
    
    def subscribe(self, role: AgentRole, callback: Callable):
        """Subscribe an agent to receive messages."""
        self.subscribers[role] = callback
        logger.info(f"📝 Agent {role.value} subscribed to communication hub")
    
    def subscribe_to_all(self, callback: Callable):
        """Subscribe to all messages (for monitoring/logging)."""
        self.broadcast_subscribers.append(callback)
        logger.info("📝 Broadcast subscriber added")

    async def _process_messages(self):
        """Main message processing loop."""
        logger.info("🔄 Message processing started")
        
        while self.is_running:
            try:
                # Get message with priority (higher number = higher priority)
                priority, message = await asyncio.wait_for(
                    self.message_queue.get(), timeout=1.0
                )
                
                # Deliver to specific recipient
                if message.recipient in self.subscribers:
                    try:
                        await self.subscribers[message.recipient](message)
                        self.delivery_stats['total_delivered'] += 1
                        logger.debug(f"✅ Message delivered: {message.id}")
                    except Exception as e:
                        logger.error(f"❌ Delivery failed: {e}")
                        self.delivery_stats['total_failed'] += 1
                
                # Send to broadcast subscribers
                for subscriber in self.broadcast_subscribers:
                    try:
                        await subscriber(message)
                    except Exception as e:
                        logger.warning(f"⚠️ Broadcast subscriber error: {e}")
                
                # Mark task as done
                self.message_queue.task_done()
                
            except asyncio.TimeoutError:
                # Normal timeout, continue loop
                continue
            except Exception as e:
                logger.error(f"❌ Message processing error: {e}")

    def get_conversation_history(self, agent1: AgentRole, agent2: AgentRole, 
                                limit: int = 50) -> List[Message]:
        """Get conversation history between two agents."""
        history = []
        for message in self.message_history:
            if ((message.sender == agent1 and message.recipient == agent2) or
                (message.sender == agent2 and message.recipient == agent1)):
                history.append(message)
        
        return history[-limit:]
    
    def get_stats(self) -> Dict:
        """Get communication hub statistics."""
        if self.message_history and self.message_history[0].timestamp is not None:
            uptime = time.time() - self.message_history[0].timestamp
        else:
            uptime = 0.0
        return {
            'total_messages': len(self.message_history),
            'active_conversations': len([c for c in self.conversations.values() 
                                       if c.status == 'active']),
            'active_negotiations': len(self.active_negotiations),
            'delivery_stats': self.delivery_stats.copy(),
            'queue_size': self.message_queue.qsize(),
            'subscriber_count': len(self.subscribers),
            'uptime': uptime
        }

    async def send_message(self, message: Message) -> bool:
        """
        Send a message through the communication hub.
        
        Args:
            message: Message to send
            
        Returns:
            bool: True if message was queued successfully
        """
        try:
            # Add to queue with priority handling
            await self.message_queue.put((message.priority.value, message))
            
            # Track in history
            self.message_history.append(message)
            self.delivery_stats['total_sent'] += 1
            
            # Add to conversation if needed
            self._track_conversation(message)
            
            logger.info(f"📤 Message queued: {message.sender.value} → {message.recipient.value}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send message: {e}")
            self.delivery_stats['total_failed'] += 1
            return False
    
    def _track_conversation(self, message: Message):
        """Track message in conversation threads."""
        conversation_id = message.conversation_id or str(uuid.uuid4())
        created_at = message.timestamp if message.timestamp is not None else time.time()
        
        if conversation_id not in self.conversations:
            # Create new conversation
            self.conversations[conversation_id] = ConversationThread(
                id=conversation_id,
                participants=[message.sender, message.recipient],
                messages=[],
                created_at=created_at
            )
        
        # Add message to conversation
        self.conversations[conversation_id].add_message(message)

    async def send_request(self, sender: AgentRole, recipient: AgentRole, 
                          content: str, message_type: MessageType = MessageType.TASK_REQUEST,
                          timeout: float = 30.0) -> Optional[Message]:
        """
        Send a request and wait for response.
        
        Args:
            sender: Sending agent role
            recipient: Receiving agent role  
            content: Message content
            message_type: Type of message
            timeout: Timeout in seconds
            
        Returns:
            Response message or None if timeout
        """
        # Create request message
        request_msg = Message(
            id=str(uuid.uuid4()),
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            content=content,
            requires_response=True
        )
        
        # Set up response waiting
        response_future = asyncio.Future()
        
        def response_handler(message: Message):
            # Ensure message.metadata is not None
            metadata = message.metadata or {}
            if (message.sender == recipient and 
                metadata.get('response_to') == request_msg.id):
                if not response_future.done():
                    response_future.set_result(message)
        
        # Temporarily subscribe to responses
        self.subscribe_to_all(response_handler)
        
        try:
            # Send request
            await self.send_message(request_msg)
            
            # Wait for response
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Request timeout: {sender.value} → {recipient.value}")
            return None
        except Exception as e:
            logger.error(f"❌ Request failed: {e}")
            return None

    async def broadcast_message(self, sender: AgentRole, content: str, 
                               message_type: MessageType = MessageType.STATUS_UPDATE):
        """Broadcast a message to all subscribed agents."""
        for recipient_role in self.subscribers.keys():
            if recipient_role != sender:  # Don't send to self
                message = Message(
                    id=str(uuid.uuid4()),
                    sender=sender,
                    recipient=recipient_role,
                    message_type=message_type,
                    content=content,
                    metadata={'broadcast': True}
                )
                await self.send_message(message)
        
        logger.info(f"📢 Broadcast sent from {sender.value}")

    async def start_negotiation(self, participants: List[AgentRole], 
                               topic: str, initial_data: Dict = None) -> str:
        """
        Start a negotiation session between multiple agents.
        
        Args:
            participants: List of agent roles to include
            topic: Negotiation topic
            initial_data: Initial negotiation data
            
        Returns:
            Negotiation ID
        """
        negotiation_id = str(uuid.uuid4())
        data = initial_data if initial_data is not None else {}
        self.active_negotiations[negotiation_id] = {
            'id': negotiation_id,
            'participants': participants,
            'topic': topic,
            'data': data,
            'proposals': [],
            'status': 'active',
            'created_at': time.time()
        }
        
        # Notify participants
        for participant in participants or []:
            message = Message(
                id=str(uuid.uuid4()),
                sender=AgentRole.ORCHESTRATOR,
                recipient=participant,
                message_type=MessageType.NEGOTIATION,
                content=f"Negotiation started: {topic}",
                metadata={
                    'negotiation_id': negotiation_id,
                    'action': 'start',
                    'participants': [p.value for p in (participants or [])]
                }
            )
            await self.send_message(message)
        
        logger.info(f"🤝 Negotiation started: {negotiation_id}")
        return negotiation_id

# Example usage and test
async def demo_communication_hub():
    """Demonstrate the communication hub functionality."""
    print("🚀 CodeCollab AI Communication Hub Demo")
    print("=" * 50)
    
    # Create communication hub
    hub = CommunicationHub()
    await hub.start()
    
    # Mock agent handlers
    async def pm_handler(message: Message):
        print(f"📋 PM received: {message.content}")
        if message.requires_response:
            response = Message(
                id=str(uuid.uuid4()),
                sender=AgentRole.PRODUCT_MANAGER,
                recipient=message.sender,
                message_type=MessageType.TASK_RESPONSE,
                content=f"PM processed: {message.content}",
                metadata={'response_to': message.id}
            )
            await hub.send_message(response)
    
    async def dev_handler(message: Message):
        print(f"💻 Developer received: {message.content}")
        if message.requires_response:
            response = Message(
                id=str(uuid.uuid4()),
                sender=AgentRole.DEVELOPER,
                recipient=message.sender,
                message_type=MessageType.TASK_RESPONSE,
                content=f"Developer will implement: {message.content}",
                metadata={'response_to': message.id}
            )
            await hub.send_message(response)
    
    async def monitor_handler(message: Message):
        print(f"📊 Monitor: {message.sender.value} → {message.recipient.value}: {message.content[:50]}...")
        return  # Ensure this is a coroutine and avoid NoneType await warning
    
    # Subscribe agents
    hub.subscribe(AgentRole.PRODUCT_MANAGER, pm_handler)
    hub.subscribe(AgentRole.DEVELOPER, dev_handler)
    hub.subscribe_to_all(monitor_handler)
    
    print("\n1. Testing basic messaging...")
    # Test basic messaging
    message1 = Message(
        id=str(uuid.uuid4()),
        sender=AgentRole.ORCHESTRATOR,
        recipient=AgentRole.PRODUCT_MANAGER,
        message_type=MessageType.TASK_REQUEST,
        content="Analyze requirements for user authentication system"
    )
    await hub.send_message(message1)
    
    print("\n2. Testing request-response pattern...")
    # Test request-response
    response = await hub.send_request(
        sender=AgentRole.PRODUCT_MANAGER,
        recipient=AgentRole.DEVELOPER,
        content="Implement login API endpoint",
        timeout=5.0
    )
    if response:
        print(f"✅ Got response: {response.content}")
    
    print("\n3. Testing broadcast...")
    # Test broadcast
    await hub.broadcast_message(
        sender=AgentRole.ORCHESTRATOR,
        content="Project kickoff - building authentication system"
    )
    
    print("\n4. Testing negotiation...")
    # Test negotiation
    negotiation_id = await hub.start_negotiation(
        participants=[AgentRole.PRODUCT_MANAGER, AgentRole.DEVELOPER],
        topic="API design approach",
        initial_data={'deadline': '2 weeks', 'priority': 'high'}
    )
    
    # Allow processing time
    await asyncio.sleep(2)
    
    print("\n5. System Statistics:")
    stats = hub.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Clean up
    await hub.stop()
    print("\n✅ Demo completed!")


if __name__ == "__main__":
    asyncio.run(demo_communication_hub()) 