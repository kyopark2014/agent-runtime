"""This is an automatically generated file. Do not modify it.

This file was generated using `langgraph-gen` version 0.0.3.
To regenerate this file, run `langgraph-gen` with the source `yaml` file as an argument.

Usage:

1. Add the generated file to your project.
2. Create a new agent using the stub.

Below is a sample implementation of the generated stub:

```python
from typing_extensions import TypedDict

from stub import CostAgent

class CostState(TypedDict):
    # define your attributes here
    foo: str

# Define stand-alone functions
def service_cost(state: CostState) -> dict:
    print("In node: service_cost")
    return {
        # Add your state update logic here
    }


def region_cost(state: CostState) -> dict:
    print("In node: region_cost")
    return {
        # Add your state update logic here
    }


def daily_cost(state: CostState) -> dict:
    print("In node: daily_cost")
    return {
        # Add your state update logic here
    }


def generate_insight(state: CostState) -> dict:
    print("In node: generate_insight")
    return {
        # Add your state update logic here
    }


def reflect_context(state: CostState) -> dict:
    print("In node: reflect_context")
    return {
        # Add your state update logic here
    }


def should_end(state: CostState) -> str:
    print("In condition: should_end")
    raise NotImplementedError("Implement me.")


agent = CostAgent(
    state_schema=CostState,
    impl=[
        ("service_cost", service_cost),
        ("region_cost", region_cost),
        ("daily_cost", daily_cost),
        ("generate_insight", generate_insight),
        ("reflect_context", reflect_context),
        ("should_end", should_end),
    ]
)

compiled_agent = agent.compile()

print(compiled_agent.invoke({"foo": "bar"}))
"""

from typing import Callable, Any, Optional, Type

from langgraph.constants import START, END
from langgraph.graph import StateGraph

def CostAgent(
    *,
    state_schema: Optional[Type[Any]] = None,
    config_schema: Optional[Type[Any]] = None,
    input: Optional[Type[Any]] = None,
    output: Optional[Type[Any]] = None,
    impl: list[tuple[str, Callable]],
) -> StateGraph:
    """Create the state graph for CostAgent."""
    # Declare the state graph
    builder = StateGraph(
        state_schema, config_schema=config_schema, input=input, output=output
    )

    nodes_by_name = {name: imp for name, imp in impl}

    all_names = set(nodes_by_name)

    expected_implementations = {
        "service_cost",
        "region_cost",
        "daily_cost",
        "generate_insight",
        "reflect_context",
        "should_end",
        "mcp_tools",
    }

    missing_nodes = expected_implementations - all_names
    if missing_nodes:
        raise ValueError(f"Missing implementations for: {missing_nodes}")

    extra_nodes = all_names - expected_implementations

    if extra_nodes:
        raise ValueError(
            f"Extra implementations for: {extra_nodes}. Please regenerate the stub."
        )

    # Add nodes
    builder.add_node("service_cost", nodes_by_name["service_cost"])
    builder.add_node("region_cost", nodes_by_name["region_cost"])
    builder.add_node("daily_cost", nodes_by_name["daily_cost"])
    builder.add_node("generate_insight", nodes_by_name["generate_insight"])
    builder.add_node("reflect_context", nodes_by_name["reflect_context"])
    builder.add_node("mcp_tools", nodes_by_name["mcp_tools"])

    # Add edges
    builder.add_edge(START, "service_cost")
    builder.add_edge("service_cost", "region_cost")
    builder.add_edge("region_cost", "daily_cost")
    builder.add_edge("daily_cost", "generate_insight")
    builder.add_conditional_edges(
        "generate_insight",
        nodes_by_name["should_end"],
        [
            END,
            "reflect_context",
        ],
    )
    builder.add_edge("reflect_context", "mcp_tools")
    builder.add_edge("mcp_tools", "generate_insight")
    
    return builder
