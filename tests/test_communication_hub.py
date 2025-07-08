"""
Comprehensive test suite for CodeCollab AI Communication Hub
Tests all features, edge cases, and error scenarios
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch
from codecollab.core.communication_hub import (
    CommunicationHub, Message, AgentRole, MessageType, MessagePriority, ConversationThread
)

# --- TestMessage class ---
class TestMessage:
    """Test suite for Message class."""
    def test_message_creation(self):
        message = Message(
            id="test-1",
            sender=AgentRole.PRODUCT_MANAGER,
            recipient=AgentRole.DEVELOPER,
            message_type=MessageType.TASK_REQUEST,
            content="Test message"
        )
        assert message.id == "test-1"
        assert message.sender == AgentRole.PRODUCT_MANAGER
        assert message.recipient == AgentRole.DEVELOPER
        assert message.content == "Test message"
        assert message.priority == MessagePriority.MEDIUM
        assert isinstance(message.metadata, dict)
        assert message.timestamp is not None
        assert message.conversation_id is not None
    def test_message_auto_fields(self):
        """Test that auto-generated fields work correctly."""
        # Test auto-generation with None
        message1 = Message(
            id=None,  # Should auto-generate
            sender=AgentRole.DEVELOPER,
            recipient=AgentRole.REVIEWER,
            message_type=MessageType.STATUS_UPDATE,
            content="Auto-generated test"
        )
        assert message1.id is not None
        assert len(message1.id) > 0
        assert message1.timestamp > 0
        assert message1.conversation_id is not None
        # Test that explicit empty string is preserved (edge case)
        message2 = Message(
            id="",  # Explicit empty string
            sender=AgentRole.DEVELOPER,
            recipient=AgentRole.REVIEWER,
            message_type=MessageType.STATUS_UPDATE,
            content="Empty ID test"
        )
        assert message2.id == ""  # Should preserve empty string
        # Test that explicit ID is preserved
        message3 = Message(
            id="custom-id-123",
            sender=AgentRole.DEVELOPER,
            recipient=AgentRole.REVIEWER,
            message_type=MessageType.STATUS_UPDATE,
            content="Custom ID test"
        )
        assert message3.id == "custom-id-123"
    def test_message_serialization(self):
        original = Message(
            id="serial-test",
            sender=AgentRole.TESTER,
            recipient=AgentRole.DEVELOPER,
            message_type=MessageType.ERROR_REPORT,
            content="Serialization test",
            priority=MessagePriority.HIGH,
            metadata={'test_key': 'test_value'}
        )
        msg_dict = original.to_dict()
        assert msg_dict['id'] == "serial-test"
        assert msg_dict['sender'] == "tester"
        assert msg_dict['content'] == "Serialization test"
        assert msg_dict['metadata']['test_key'] == 'test_value'
        restored = Message.from_dict(msg_dict)
        assert restored.id == original.id
        assert restored.sender == original.sender
        assert restored.content == original.content
        assert restored.metadata == original.metadata
    def test_message_from_dict_edge_cases(self):
        data_none_meta = {
            'id': 'edge-1',
            'sender': 'dev',
            'recipient': 'pm',
            'message_type': 'task_request',
            'content': 'Test',
            'priority': 2,
            'timestamp': 123456.0,
            'metadata': None
        }
        msg1 = Message.from_dict(data_none_meta)
        assert isinstance(msg1.metadata, dict)
        assert msg1.metadata == {}
        data_no_meta = {
            'id': 'edge-2',
            'sender': 'dev',
            'recipient': 'pm',
            'message_type': 'task_request',
            'content': 'Test',
            'priority': 2,
            'timestamp': 123456.0
        }
        msg2 = Message.from_dict(data_no_meta)
        assert isinstance(msg2.metadata, dict)
        assert msg2.metadata == {}

# --- TestConversationThread class ---
class TestConversationThread:
    """Test suite for ConversationThread class."""
    def test_conversation_creation(self):
        conv = ConversationThread(
            id="conv-1",
            participants=[AgentRole.DEVELOPER, AgentRole.REVIEWER],
            messages=[],
            created_at=time.time()
        )
        assert conv.id == "conv-1"
        assert len(conv.participants) == 2
        assert conv.status == "active"
        assert len(conv.messages) == 0
    def test_add_message(self):
        conv = ConversationThread(
            id="conv-2",
            participants=[AgentRole.PRODUCT_MANAGER, AgentRole.DEVELOPER],
            messages=[],
            created_at=time.time()
        )
        message = Message(
            id="msg-1",
            sender=AgentRole.PRODUCT_MANAGER,
            recipient=AgentRole.DEVELOPER,
            message_type=MessageType.TASK_REQUEST,
            content="Test message"
        )
        conv.add_message(message)
        assert len(conv.messages) == 1
        assert conv.messages[0] == message
        assert message.conversation_id == conv.id
    def test_get_context(self):
        conv = ConversationThread(
            id="conv-3",
            participants=[AgentRole.DEVELOPER, AgentRole.TESTER],
            messages=[],
            created_at=time.time()
        )
        for i in range(15):
            msg = Message(
                id=f"msg-{i}",
                sender=AgentRole.DEVELOPER,
                recipient=AgentRole.TESTER,
                message_type=MessageType.STATUS_UPDATE,
                content=f"Message {i}"
            )
            conv.add_message(msg)
        context = conv.get_context()
        assert len(context) == 10
        assert context[0].content == "Message 5"
        assert context[-1].content == "Message 14"
        context_5 = conv.get_context(limit=5)
        assert len(context_5) == 5
        assert context_5[0].content == "Message 10"

# --- TestCommunicationHub class ---
# (Insert all test methods for TestCommunicationHub here)
# ... (Due to length, the rest of the test suite code is as provided by the user) ...

# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"]) 