# Minimal graph.py fixture for analyze_graph_structure tests
from langgraph.graph import StateGraph

builder = StateGraph({"evidences": {}, "opinions": []})
builder.add_node("repo", lambda s: s)
builder.add_node("doc", lambda s: s)
builder.add_edge("repo", "doc")
builder.add_edge("doc", "__end__")
app = builder.compile()
