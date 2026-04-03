from graphify.models import Confidence, FileType, GraphNode, GraphEdge, ExtractionResult

def test_confidence_values():
    assert Confidence.EXTRACTED.value == "EXTRACTED"
    assert Confidence.INFERRED.value == "INFERRED"
    assert Confidence.AMBIGUOUS.value == "AMBIGUOUS"

def test_graph_node_defaults():
    node = GraphNode(id="n1", label="MyClass", file_type=FileType.CODE, source_file="foo.py")
    assert node.community is None
    assert node.source_location is None

def test_graph_edge_defaults():
    edge = GraphEdge(source="n1", target="n2", relation="imports",
                     confidence=Confidence.EXTRACTED, source_file="foo.py")
    assert edge.weight == 1.0

def test_extraction_result_accumulates():
    r = ExtractionResult()
    r.nodes.append(GraphNode(id="n1", label="X", file_type=FileType.CODE, source_file="a.py"))
    r.edges.append(GraphEdge(source="n1", target="n2", relation="calls",
                             confidence=Confidence.INFERRED, source_file="a.py"))
    assert len(r.nodes) == 1
    assert len(r.edges) == 1
    r.input_tokens += 100
    assert r.input_tokens == 100
