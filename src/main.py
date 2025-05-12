from graph import build_graph

if __name__ == "__main__":
    graph = build_graph()
    graph.invoke({})          # initial state is an empty dict
    print("news.md generated.")