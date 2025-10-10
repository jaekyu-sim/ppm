from langgraph.graph import StateGraph, START, END

from .ast_parser_node import parse_methods_from_file, regroup_methods
from .node import summarize_method_function, match_summary_to_requirement, code_interpreter, compare_to_rfp
from .state import AgentState


def create_code_compare_to_rfp_graph():
    graph_builder = StateGraph(AgentState)
    graph_builder.add_node('parse_methods_from_file', parse_methods_from_file)
    graph_builder.add_node('summarize_method_function', summarize_method_function)
    graph_builder.add_node('match_summary_to_requirement', match_summary_to_requirement)
    graph_builder.add_node('regroup_methods', regroup_methods)
    graph_builder.add_node('code_interpreter', code_interpreter)
    graph_builder.add_node('compare_to_rfp', compare_to_rfp)

    graph_builder.add_edge(START, 'parse_methods_from_file')
    graph_builder.add_edge('parse_methods_from_file', 'summarize_method_function')
    graph_builder.add_edge('summarize_method_function', 'match_summary_to_requirement')
    graph_builder.add_edge('match_summary_to_requirement', 'regroup_methods')
    graph_builder.add_edge('regroup_methods', 'code_interpreter')
    graph_builder.add_edge('code_interpreter', 'compare_to_rfp')
    graph_builder.add_edge('compare_to_rfp', END)

    graph = graph_builder.compile()

    return graph