"""
Memory System for CodeCollab AI Agents
Provides persistent memory, context management, and learning capabilities
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Union, TypeVar, Generic
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod
import hashlib
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class MemoryType(Enum):
    """Types of memory entries."""
    CONVERSATION = "conversation"
    TASK = "task"
    LEARNING = "learning"
    CONTEXT = "context"
    FACT = "fact"
    PATTERN = "pattern"
    ERROR = "error"


class MemoryPriority(Enum):
    """Priority levels for memory entries."""
    CRITICAL = 5
    HIGH = 4
    MEDIUM = 3
    LOW = 2
    TEMPORARY = 1


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""
    id: str
    content: Any
    memory_type: MemoryType
    priority: MemoryPriority
    created_at: float
    last_accessed: float
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[float] = None
    
    def __post_init__(self):
        """Initialize computed fields."""
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_accessed is None:
            self.last_accessed = self.created_at
    
    def access(self):
        """Mark this memory as accessed."""
        self.access_count += 1
        self.last_accessed = time.time()
    
    def is_expired(self) -> bool:
        """Check if this memory entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            **asdict(self),
            'memory_type': self.memory_type.value,
            'priority': self.priority.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryEntry':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            content=data['content'],
            memory_type=MemoryType(data['memory_type']),
            priority=MemoryPriority(data['priority']),
            created_at=data['created_at'],
            last_accessed=data['last_accessed'],
            access_count=data.get('access_count', 0),
            tags=data.get('tags', []),
            metadata=data.get('metadata', {}),
            expires_at=data.get('expires_at')
        )


class MemoryStore(ABC):
    """Abstract base class for memory storage backends."""
    
    @abstractmethod
    async def store(self, entry: MemoryEntry) -> bool:
        """Store a memory entry."""
        pass
    
    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID."""
        pass
    
    @abstractmethod
    async def search(self, query: str, memory_type: Optional[MemoryType] = None, 
                    tags: Optional[List[str]] = None, limit: int = 10) -> List[MemoryEntry]:
        """Search for memory entries."""
        pass
    
    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        pass
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count."""
        pass


class InMemoryStore(MemoryStore):
    """In-memory implementation of memory store."""
    
    def __init__(self):
        self.memories: Dict[str, MemoryEntry] = {}
        self.type_index: Dict[MemoryType, List[str]] = {t: [] for t in MemoryType}
        self.tag_index: Dict[str, List[str]] = {}
    
    async def store(self, entry: MemoryEntry) -> bool:
        """Store a memory entry in memory."""
        try:
            # Store the entry
            self.memories[entry.id] = entry
            
            # Update type index
            if entry.id not in self.type_index[entry.memory_type]:
                self.type_index[entry.memory_type].append(entry.id)
            
            # Update tag index
            for tag in entry.tags:
                if tag not in self.tag_index:
                    self.tag_index[tag] = []
                if entry.id not in self.tag_index[tag]:
                    self.tag_index[tag].append(entry.id)
            
            return True
        except Exception as e:
            logger.error(f"Error storing memory {entry.id}: {e}")
            return False
    
    async def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID."""
        entry = self.memories.get(memory_id)
        if entry and not entry.is_expired():
            entry.access()
            return entry
        elif entry and entry.is_expired():
            await self.delete(memory_id)
        return None
    
    async def search(self, query: str, memory_type: Optional[MemoryType] = None, 
                    tags: Optional[List[str]] = None, limit: int = 10) -> List[MemoryEntry]:
        """Search for memory entries."""
        results = []
        
        # Get candidate IDs based on filters
        candidate_ids = set(self.memories.keys())
        
        if memory_type:
            candidate_ids &= set(self.type_index[memory_type])
        
        if tags:
            tag_ids = set()
            for tag in tags:
                if tag in self.tag_index:
                    tag_ids.update(self.tag_index[tag])
            candidate_ids &= tag_ids
        
        # Search through candidates
        for memory_id in candidate_ids:
            entry = self.memories[memory_id]
            if entry.is_expired():
                continue
            
            # Simple text search in content
            content_str = str(entry.content).lower()
            if query.lower() in content_str:
                entry.access()
                results.append(entry)
        
        # Sort by relevance (access count + recency)
        results.sort(key=lambda e: (e.access_count, e.last_accessed), reverse=True)
        
        return results[:limit]
    
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        if memory_id not in self.memories:
            return False
        
        entry = self.memories[memory_id]
        
        # Remove from main storage
        del self.memories[memory_id]
        
        # Remove from type index
        if memory_id in self.type_index[entry.memory_type]:
            self.type_index[entry.memory_type].remove(memory_id)
        
        # Remove from tag index
        for tag in entry.tags:
            if tag in self.tag_index and memory_id in self.tag_index[tag]:
                self.tag_index[tag].remove(memory_id)
                if not self.tag_index[tag]:  # Remove empty tag lists
                    del self.tag_index[tag]
        
        return True
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count."""
        expired_ids = []
        
        for memory_id, entry in self.memories.items():
            if entry.is_expired():
                expired_ids.append(memory_id)
        
        for memory_id in expired_ids:
            await self.delete(memory_id)
        
        return len(expired_ids)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory store statistics."""
        return {
            'total_memories': len(self.memories),
            'by_type': {t.value: len(ids) for t, ids in self.type_index.items()},
            'total_tags': len(self.tag_index),
            'memory_usage_mb': sum(
                len(str(entry.content)) for entry in self.memories.values()
            ) / (1024 * 1024)
        }


class AgentMemory:
    """
    Memory management system for agents.
    Provides context-aware storage, retrieval, and learning capabilities.
    """
    
    def __init__(self, agent_id: str, store: Optional[MemoryStore] = None, 
                 max_size: int = 1000):
        self.agent_id = agent_id
        self.store = store or InMemoryStore()
        self.max_size = max_size
        
        # Working memory (faster access)
        self.working_memory: Dict[str, Any] = {}
        
        # Context tracking
        self.current_context: Dict[str, Any] = {}
        self.context_stack: List[Dict[str, Any]] = []
        
        # Learning patterns
        self.success_patterns: List[Dict[str, Any]] = []
        self.failure_patterns: List[Dict[str, Any]] = []
        
        logger.info(f"🧠 Memory system initialized for agent {agent_id}")
    
    async def remember(self, content: Any, memory_type: MemoryType, 
                      priority: MemoryPriority = MemoryPriority.MEDIUM,
                      tags: Optional[List[str]] = None,
                      expires_in: Optional[float] = None) -> str:
        """
        Store something in memory.
        
        Args:
            content: What to remember
            memory_type: Type of memory
            priority: Priority level
            tags: Optional tags for categorization
            expires_in: Optional expiration time in seconds
            
        Returns:
            Memory ID
        """
        # Generate memory ID
        content_hash = hashlib.md5(str(content).encode()).hexdigest()
        memory_id = f"{self.agent_id}_{memory_type.value}_{content_hash}_{int(time.time())}"
        
        # Calculate expiration
        expires_at = None
        if expires_in:
            expires_at = time.time() + expires_in
        
        # Create memory entry
        entry = MemoryEntry(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            priority=priority,
            created_at=time.time(),
            last_accessed=time.time(),
            tags=tags or [],
            expires_at=expires_at
        )
        
        # Store in memory
        success = await self.store.store(entry)
        
        if success:
            logger.debug(f"💾 Stored memory {memory_id} ({memory_type.value})")
            await self._enforce_size_limit()
        
        return memory_id
    
    async def recall(self, memory_id: str) -> Optional[Any]:
        """Recall something from memory by ID."""
        entry = await self.store.retrieve(memory_id)
        if entry:
            logger.debug(f"🧠 Recalled memory {memory_id}")
            return entry.content
        return None
    
    async def search_memories(self, query: str, memory_type: Optional[MemoryType] = None,
                             tags: Optional[List[str]] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search memories by content, type, or tags.
        
        Returns:
            List of memory results with metadata
        """
        entries = await self.store.search(query, memory_type, tags, limit)
        
        results = []
        for entry in entries:
            results.append({
                'id': entry.id,
                'content': entry.content,
                'type': entry.memory_type.value,
                'priority': entry.priority.value,
                'created_at': entry.created_at,
                'tags': entry.tags,
                'relevance_score': entry.access_count / max(1, time.time() - entry.created_at)
            })
        
        return results
    
    async def remember_conversation(self, message_id: str, content: str, 
                                  role: str, context: Optional[Dict[str, Any]] = None):
        """Remember a conversation message with context."""
        conversation_data = {
            'message_id': message_id,
            'content': content,
            'role': role,
            'context': context or {},
            'timestamp': time.time()
        }
        
        await self.remember(
            conversation_data,
            MemoryType.CONVERSATION,
            MemoryPriority.MEDIUM,
            tags=['conversation', role]
        )
    
    async def remember_task_outcome(self, task_id: str, outcome: str, 
                                   success: bool, details: Optional[Dict[str, Any]] = None):
        """Remember the outcome of a task for learning."""
        task_data = {
            'task_id': task_id,
            'outcome': outcome,
            'success': success,
            'details': details or {},
            'timestamp': time.time()
        }
        
        priority = MemoryPriority.HIGH if success else MemoryPriority.CRITICAL
        tags = ['task', 'success' if success else 'failure']
        
        await self.remember(task_data, MemoryType.TASK, priority, tags)
        
        # Update learning patterns
        pattern = {
            'context': self.current_context.copy(),
            'outcome': outcome,
            'success': success,
            'timestamp': time.time()
        }
        
        if success:
            self.success_patterns.append(pattern)
            if len(self.success_patterns) > 100:  # Keep last 100
                self.success_patterns.pop(0)
        else:
            self.failure_patterns.append(pattern)
            if len(self.failure_patterns) > 100:
                self.failure_patterns.pop(0)
    
    async def learn_from_feedback(self, feedback: str, context: Dict[str, Any]):
        """Learn from feedback and adjust future behavior."""
        learning_data = {
            'feedback': feedback,
            'context': context,
            'timestamp': time.time(),
            'current_patterns': {
                'success_count': len(self.success_patterns),
                'failure_count': len(self.failure_patterns)
            }
        }
        
        await self.remember(
            learning_data,
            MemoryType.LEARNING,
            MemoryPriority.HIGH,
            tags=['feedback', 'learning']
        )
    
    def set_context(self, context: Dict[str, Any]):
        """Set current working context."""
        self.current_context = context.copy()
        logger.debug(f"🎯 Context set: {list(context.keys())}")
    
    def push_context(self, context: Dict[str, Any]):
        """Push current context to stack and set new context."""
        self.context_stack.append(self.current_context.copy())
        self.current_context = context.copy()
    
    def pop_context(self) -> Optional[Dict[str, Any]]:
        """Pop context from stack and restore previous context."""
        if self.context_stack:
            old_context = self.current_context.copy()
            self.current_context = self.context_stack.pop()
            return old_context
        return None
    
    async def get_relevant_context(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get relevant memories for current context."""
        # Search recent conversations
        conversations = await self.search_memories(
            query, MemoryType.CONVERSATION, limit=limit//2
        )
        
        # Search relevant tasks
        tasks = await self.search_memories(
            query, MemoryType.TASK, limit=limit//2
        )
        
        # Combine and sort by relevance
        all_results = conversations + tasks
        all_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return all_results[:limit]
    
    async def cleanup(self):
        """Clean up expired memories and optimize storage."""
        expired_count = await self.store.cleanup_expired()
        await self._enforce_size_limit()
        
        logger.info(f"🧹 Memory cleanup: {expired_count} expired entries removed")
    
    async def _enforce_size_limit(self):
        """Enforce maximum memory size by removing oldest, least accessed entries."""
        if isinstance(self.store, InMemoryStore):
            total_memories = len(self.store.memories)
            
            if total_memories > self.max_size:
                # Sort by priority and access patterns
                entries = list(self.store.memories.values())
                entries.sort(key=lambda e: (
                    e.priority.value,
                    e.access_count,
                    e.last_accessed
                ))
                
                # Remove oldest, least important entries
                to_remove = total_memories - self.max_size
                for i in range(to_remove):
                    await self.store.delete(entries[i].id)
                
                logger.debug(f"🗑️ Removed {to_remove} old memories to enforce size limit")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        base_stats = {
            'agent_id': self.agent_id,
            'working_memory_size': len(self.working_memory),
            'context_stack_depth': len(self.context_stack),
            'success_patterns': len(self.success_patterns),
            'failure_patterns': len(self.failure_patterns),
            'current_context_keys': list(self.current_context.keys())
        }
        
        if isinstance(self.store, InMemoryStore):
            base_stats.update(self.store.get_stats())
        
        return base_stats


# Demo function
async def demo_memory_system():
    """Demonstrate the memory system functionality."""
    print("🧠 CodeCollab AI Memory System Demo")
    print("=" * 40)
    
    # Create memory system
    memory = AgentMemory("demo-agent")
    
    print("\n1. Storing different types of memories...")
    
    # Store conversation
    conv_id = await memory.remember_conversation(
        "msg-1", "User asked about implementing authentication", "user",
        {"project": "webapp", "priority": "high"}
    )
    
    # Store task outcome
    await memory.remember_task_outcome(
        "task-1", "Successfully implemented login API", True,
        {"lines_of_code": 150, "tests_added": 12}
    )
    
    # Store learning
    await memory.learn_from_feedback(
        "The API design was clean but could use better error handling",
        {"component": "authentication", "feedback_type": "code_review"}
    )
    
    print("✅ Stored conversation, task outcome, and learning feedback")
    
    print("\n2. Searching memories...")
    
    # Search for authentication-related memories
    results = await memory.search_memories("authentication", limit=5)
    print(f"🔍 Found {len(results)} memories about authentication")
    for result in results:
        print(f"   - {result['type']}: {str(result['content'])[:60]}...")
    
    print("\n3. Context management...")
    
    # Set context
    memory.set_context({"current_task": "code_review", "file": "auth.py"})
    
    # Get relevant context
    context = await memory.get_relevant_context("authentication")
    print(f"🎯 Found {len(context)} relevant memories for current context")
    
    print("\n4. Memory statistics:")
    stats = memory.get_memory_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n✅ Memory system demo completed!")


if __name__ == "__main__":
    asyncio.run(demo_memory_system()) 