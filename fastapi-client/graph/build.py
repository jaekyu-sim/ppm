from langgraph.graph import MessagesState, StateGraph, START, END
from typing import Literal
from .node import code_interpreter, compare_to_rfp
from .state import AgentState



def create_code_compare_to_rfp_graph():
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node('code_interpreter', code_interpreter)
    graph_builder.add_node('compare_to_rfp', compare_to_rfp)

    graph_builder.add_edge(START, 'code_interpreter')
    graph_builder.add_edge('code_interpreter', 'compare_to_rfp')
    graph_builder.add_edge('compare_to_rfp', END)

    graph = graph_builder.compile()

    return graph