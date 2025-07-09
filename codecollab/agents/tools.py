# codecollab/agents/tools.py
"""
Tool System for CodeCollab AI Agents
Provides extensible plugin architecture for agent capabilities
"""

import asyncio
import inspect
import json
import time
from typing import Dict, List, Optional, Any, Callable, Union, get_type_hints
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Categories of tools available to agents."""
    CODE_ANALYSIS = "code_analysis"
    CODE_GENERATION = "code_generation"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    COMMUNICATION = "communication"
    FILE_MANAGEMENT = "file_management"
    PROJECT_MANAGEMENT = "project_management"
    RESEARCH = "research"
    VALIDATION = "validation"


class ToolExecutionStatus(Enum):
    """Status of tool execution."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    param_type: type
    description: str
    required: bool = True
    default: Any = None
    validation_rules: List[str] = field(default_factory=list)
    
    def validate(self, value: Any) -> bool:
        """Validate a parameter value."""
        # Type check
        if not isinstance(value, self.param_type):
            try:
                # Try to convert
                value = self.param_type(value)
            except (ValueError, TypeError):
                return False
        
        # Apply validation rules
        for rule in self.validation_rules:
            if rule == "non_empty" and not value:
                return False
            elif rule == "positive" and isinstance(value, (int, float)) and value <= 0:
                return False
            elif rule.startswith("max_length:"):
                # Only check length for types that are not int/float and have __len__
                if not isinstance(value, (int, float)) and hasattr(value, '__len__'):
                    max_len = int(rule.split(":")[1])
                    if len(value) > max_len:
                        return False
        
        return True


@dataclass
class ToolResult:
    """Result of tool execution."""
    tool_name: str
    status: ToolExecutionStatus
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def is_success(self) -> bool:
        """Check if tool execution was successful."""
        return self.status == ToolExecutionStatus.SUCCESS
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'tool_name': self.tool_name,
            'status': self.status.value,
            'result': self.result,
            'error': self.error,
            'execution_time': self.execution_time,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }


class BaseTool(ABC):
    """Abstract base class for all agent tools."""
    
    def __init__(self, name: str, description: str, category: ToolCategory):
        self.name = name
        self.description = description
        self.category = category
        self.parameters: List[ToolParameter] = []
        self.usage_count = 0
        self.total_execution_time = 0.0
        self.success_count = 0
        self.failure_count = 0
        
        # Auto-detect parameters from execute method signature
        self._detect_parameters()
    
    def _detect_parameters(self):
        """Auto-detect parameters from the execute method signature."""
        try:
            sig = inspect.signature(self.execute)
            type_hints = get_type_hints(self.execute)
            
            for param_name, param in sig.parameters.items():
                if param_name in ['self', 'context']:
                    continue
                
                param_type = type_hints.get(param_name, str)
                required = param.default == inspect.Parameter.empty
                default = None if required else param.default
                
                tool_param = ToolParameter(
                    name=param_name,
                    param_type=param_type,
                    description=f"Parameter {param_name}",
                    required=required,
                    default=default
                )
                self.parameters.append(tool_param)
                
        except Exception as e:
            logger.warning(f"Could not auto-detect parameters for {self.name}: {e}")
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        pass
    
    async def run(self, context: Optional[Dict[str, Any]] = None, **kwargs) -> ToolResult:
        """Run the tool with validation and error handling."""
        start_time = time.time()
        self.usage_count += 1
        
        try:
            # Validate parameters
            validation_errors = self._validate_parameters(kwargs)
            if validation_errors:
                self.failure_count += 1
                return ToolResult(
                    tool_name=self.name,
                    status=ToolExecutionStatus.FAILURE,
                    error=f"Parameter validation failed: {', '.join(validation_errors)}",
                    execution_time=time.time() - start_time
                )
            
            # Execute the tool
            result = await self.execute(**kwargs)
            
            execution_time = time.time() - start_time
            self.total_execution_time += execution_time
            self.success_count += 1
            
            return ToolResult(
                tool_name=self.name,
                status=ToolExecutionStatus.SUCCESS,
                result=result,
                execution_time=execution_time,
                metadata={'context': context or {}}
            )
            
        except asyncio.TimeoutError:
            self.failure_count += 1
            return ToolResult(
                tool_name=self.name,
                status=ToolExecutionStatus.TIMEOUT,
                error="Tool execution timed out",
                execution_time=time.time() - start_time
            )
        except Exception as e:
            self.failure_count += 1
            logger.error(f"Tool {self.name} execution failed: {e}")
            return ToolResult(
                tool_name=self.name,
                status=ToolExecutionStatus.FAILURE,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    def _validate_parameters(self, kwargs: Dict[str, Any]) -> List[str]:
        """Validate tool parameters."""
        errors = []
        
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                errors.append(f"Required parameter '{param.name}' is missing")
            elif param.name in kwargs:
                if not param.validate(kwargs[param.name]):
                    errors.append(f"Parameter '{param.name}' validation failed")
        
        return errors
    
    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema for documentation or UI generation."""
        return {
            'name': self.name,
            'description': self.description,
            'category': self.category.value,
            'parameters': [
                {
                    'name': p.name,
                    'type': p.param_type.__name__,
                    'description': p.description,
                    'required': p.required,
                    'default': p.default,
                    'validation_rules': p.validation_rules
                }
                for p in self.parameters
            ],
            'usage_stats': {
                'usage_count': self.usage_count,
                'success_rate': self.success_count / max(1, self.usage_count),
                'average_execution_time': self.total_execution_time / max(1, self.usage_count)
            }
        }


class ToolRegistry:
    """Registry for managing available tools."""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.categories: Dict[ToolCategory, List[str]] = {cat: [] for cat in ToolCategory}
        
    def register_tool(self, tool: BaseTool):
        """Register a new tool."""
        self.tools[tool.name] = tool
        if tool.name not in self.categories[tool.category]:
            self.categories[tool.category].append(tool.name)
        logger.info(f"🔧 Registered tool: {tool.name} ({tool.category.value})")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def get_tools_by_category(self, category: ToolCategory) -> List[BaseTool]:
        """Get all tools in a category."""
        return [self.tools[name] for name in self.categories[category]]
    
    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return list(self.tools.keys())
    
    def search_tools(self, query: str) -> List[BaseTool]:
        """Search tools by name or description."""
        results = []
        query_lower = query.lower()
        
        for tool in self.tools.values():
            if (query_lower in tool.name.lower() or 
                query_lower in tool.description.lower()):
                results.append(tool)
        
        return results
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            'total_tools': len(self.tools),
            'by_category': {cat.value: len(tools) for cat, tools in self.categories.items()},
            'most_used_tools': sorted(
                [(name, tool.usage_count) for name, tool in self.tools.items()],
                key=lambda x: x[1], reverse=True
            )[:5]
        }


# Built-in tools
class CodeAnalysisTool(BaseTool):
    """Tool for analyzing code quality and structure."""
    
    def __init__(self):
        super().__init__(
            name="code_analyzer",
            description="Analyzes code for quality, complexity, and potential issues",
            category=ToolCategory.CODE_ANALYSIS
        )
    
    async def execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Analyze code and return metrics."""
        # Simulate code analysis
        await asyncio.sleep(0.1)  # Simulate processing time
        
        lines = code.split('\n')
        
        analysis = {
            'lines_of_code': len([line for line in lines if line.strip()]),
            'blank_lines': len([line for line in lines if not line.strip()]),
            'comment_lines': len([line for line in lines if line.strip().startswith('#')]),
            'language': language,
            'estimated_complexity': min(10, len(lines) // 10),
            'suggestions': [
                "Consider adding more comments",
                "Break down large functions",
                "Add type hints for better code clarity"
            ]
        }
        
        return analysis


class DocumentationTool(BaseTool):
    """Tool for generating documentation."""
    
    def __init__(self):
        super().__init__(
            name="doc_generator",
            description="Generates documentation for code, APIs, or projects",
            category=ToolCategory.DOCUMENTATION
        )
    
    async def execute(self, content: str, doc_type: str = "readme") -> str:
        """Generate documentation."""
        await asyncio.sleep(0.2)  # Simulate processing
        
        if doc_type.lower() == "readme":
            return f"""# Project Documentation

## Overview
{content}

## Installation
```bash
pip install -r requirements.txt
```

## Usage
Detailed usage instructions for the project.

## Contributing
Guidelines for contributing to this project.
"""
        elif doc_type.lower() == "api":
            return f"""# API Documentation

## Endpoints

### {content}
- **Method**: GET/POST
- **Description**: Auto-generated API documentation
- **Parameters**: To be documented
- **Response**: JSON response format
"""
        else:
            return f"# {doc_type.title()} Documentation\n\n{content}"


class TestGeneratorTool(BaseTool):
    """Tool for generating test cases."""
    
    def __init__(self):
        super().__init__(
            name="test_generator",
            description="Generates unit tests for given code",
            category=ToolCategory.TESTING
        )
    
    async def execute(self, code: str, test_framework: str = "pytest") -> str:
        """Generate test cases for code."""
        await asyncio.sleep(0.15)  # Simulate processing
        
        function_names = []
        for line in code.split('\n'):
            if line.strip().startswith('def ') and '__init__' not in line:
                func_name = line.strip().split('(')[0].replace('def ', '')
                function_names.append(func_name)
        
        if test_framework.lower() == "pytest":
            tests = f"""import pytest
from your_module import *

class TestGeneratedTests:
"""
            for func in function_names:
                tests += f"""
    def test_{func}_basic(self):
        '''Test basic functionality of {func}.'''
        # TODO: Implement test
        assert True
    
    def test_{func}_edge_cases(self):
        '''Test edge cases for {func}.'''
        # TODO: Implement edge case tests
        assert True
"""
            return tests
        
        return f"# Generated tests for {test_framework}\n# TODO: Implement tests"


class ToolManager:
    """Manages tools for an agent."""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.registry = ToolRegistry()
        self.execution_history: List[ToolResult] = []
        
        # Register built-in tools
        self._register_builtin_tools()
        
        logger.info(f"🔧 Tool manager initialized for agent {agent_id}")
    
    def _register_builtin_tools(self):
        """Register built-in tools."""
        self.registry.register_tool(CodeAnalysisTool())
        self.registry.register_tool(DocumentationTool())
        self.registry.register_tool(TestGeneratorTool())
    
    async def execute_tool(self, tool_name: str, context: Optional[Dict[str, Any]] = None, 
                          **kwargs) -> ToolResult:
        """Execute a tool by name."""
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILURE,
                error=f"Tool '{tool_name}' not found"
            )
        
        # Execute tool
        result = await tool.run(context=context, **kwargs)
        
        # Store in history
        self.execution_history.append(result)
        
        # Keep history size manageable
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-1000:]
        
        logger.info(f"🔧 Executed tool {tool_name}: {result.status.value}")
        return result
    
    def get_available_tools(self, category: Optional[ToolCategory] = None) -> List[Dict[str, Any]]:
        """Get list of available tools with their schemas."""
        if category:
            tools = self.registry.get_tools_by_category(category)
        else:
            tools = list(self.registry.tools.values())
        
        return [tool.get_schema() for tool in tools]
    
    def get_tool_recommendations(self, context: Dict[str, Any]) -> List[str]:
        """Get tool recommendations based on context."""
        recommendations = []
        
        # Simple rule-based recommendations
        if 'code' in context:
            recommendations.extend(['code_analyzer', 'test_generator'])
        
        if 'documentation' in context or 'readme' in context:
            recommendations.append('doc_generator')
        
        if 'project' in context:
            recommendations.extend(['doc_generator', 'code_analyzer'])
        
        return recommendations[:5]  # Top 5 recommendations
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get tool usage statistics."""
        successful_executions = [r for r in self.execution_history if r.is_success()]
        failed_executions = [r for r in self.execution_history if not r.is_success()]
        
        return {
            'total_executions': len(self.execution_history),
            'successful_executions': len(successful_executions),
            'failed_executions': len(failed_executions),
            'success_rate': len(successful_executions) / max(1, len(self.execution_history)),
            'average_execution_time': sum(r.execution_time for r in self.execution_history) / max(1, len(self.execution_history)),
            'most_used_tools': {},  # Could implement frequency counting
            'registry_stats': self.registry.get_registry_stats()
        }


# Demo function
async def demo_tool_system():
    """Demonstrate the tool system functionality."""
    print("🔧 CodeCollab AI Tool System Demo")
    print("=" * 40)
    
    # Create tool manager
    tool_manager = ToolManager("demo-agent")
    
    print("\n1. Available tools:")
    tools = tool_manager.get_available_tools()
    for tool in tools:
        print(f"   🔧 {tool['name']}: {tool['description']}")
        print(f"      Category: {tool['category']}")
        print(f"      Usage: {tool['usage_stats']['usage_count']} times")
    
    print("\n2. Executing tools...")
    
    # Test code analysis
    sample_code = """
def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

def main():
    print(calculate_fibonacci(10))
"""
    
    result1 = await tool_manager.execute_tool(
        "code_analyzer",
        context={'task': 'code_review'},
        code=sample_code,
        language="python"
    )
    
    print(f"✅ Code Analysis: {result1.status.value}")
    if result1.is_success():
        analysis = result1.result
        print(f"   - Lines of code: {analysis['lines_of_code']}")
        print(f"   - Complexity: {analysis['estimated_complexity']}/10")
    
    # Test documentation generation
    result2 = await tool_manager.execute_tool(
        "doc_generator",
        context={'task': 'documentation'},
        content="A Python library for calculating Fibonacci numbers",
        doc_type="readme"
    )
    
    print(f"✅ Documentation Generation: {result2.status.value}")
    if result2.is_success():
        print("   - Generated README documentation")
    
    # Test test generation
    result3 = await tool_manager.execute_tool(
        "test_generator",
        context={'task': 'testing'},
        code=sample_code,
        test_framework="pytest"
    )
    
    print(f"✅ Test Generation: {result3.status.value}")
    if result3.is_success():
        print("   - Generated pytest test cases")
    
    print("\n3. Tool recommendations:")
    context = {'code': True, 'project': 'fibonacci-calculator'}
    recommendations = tool_manager.get_tool_recommendations(context)
    print(f"   Recommended tools: {', '.join(recommendations)}")
    
    print("\n4. Usage statistics:")
    stats = tool_manager.get_usage_stats()
    print(f"   Total executions: {stats['total_executions']}")
    print(f"   Success rate: {stats['success_rate']:.1%}")
    print(f"   Average execution time: {stats['average_execution_time']:.3f}s")
    
    print("\n✅ Tool system demo completed!")


if __name__ == "__main__":
    asyncio.run(demo_tool_system()) 