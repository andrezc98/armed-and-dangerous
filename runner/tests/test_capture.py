"""`kubectl top` prints two different tables, and the parser has to know both.

Fixtures are the real formats, taken from the printer that produces them
(kubectl 1.33, staging/src/k8s.io/kubectl/pkg/metricsutil/metrics_printer.go):
NodeColumns = NAME CPU(cores) CPU(%) MEMORY(bytes) MEMORY(%), PodColumns = NAME
CPU(cores) MEMORY(bytes). The pod table has no percentage column at all.
"""

import json
from pathlib import Path

import capture

FIXTURES = Path(__file__).parent / "fixtures"
NODES = (FIXTURES / "top-node.txt").read_text()
PODS = (FIXTURES / "top-pod.txt").read_text()

SUT = "ip-10-0-1-11.ec2.internal"
OTHER = "ip-10-0-1-42.ec2.internal"
LOADER = "ip-10-0-1-90.ec2.internal"


def _sample():
    return capture.parse_top(NODES, PODS, SUT, LOADER)


def test_the_pod_table_has_no_percentage_column_and_is_still_parsed():
    # iperf3-server is 8493m in the fixture; a parser that demands a % column
    # reports 0 here and every cpu_per_gbps on the slide is a division by zero.
    assert _sample()["pod_cpu_millicores"] == 8493


def test_the_load_generator_pods_are_not_the_measured_pod():
    # The iperf3 client is on the loader side and is higher than pyroscope; the
    # measured pod is the server.
    assert _sample()["pod_cpu_millicores"] != 7802


def test_both_cell_nodes_are_sampled_not_only_the_sut():
    assert _sample()["nodes"] == {SUT: 14832, OTHER: 7104}


def test_the_sut_node_keeps_its_own_cpu_fields():
    s = _sample()
    assert (s["node_cpu_millicores"], s["node_cpu_percent"]) == (14832, 92)


def test_the_loader_is_read_from_the_same_table_for_the_guard():
    s = _sample()
    assert (s["loader_cpu_millicores"], s["loader_cpu_percent"]) == (5120, 32)
    assert LOADER not in s["nodes"]


def test_a_node_without_metrics_is_skipped_not_guessed():
    # kubectl prints '<unknown>' four times when metrics-server has no sample yet.
    text = f"{OTHER}   <unknown>   <unknown>   <unknown>   <unknown>\n"
    assert capture.parse_top(text, "", SUT, LOADER)["nodes"] == {}


def test_the_top_json_fixture_has_the_shape_the_parser_produces():
    """Guards the stats fixture against drifting away from the real parser."""
    fixture = json.loads((FIXTURES / "top-net.json").read_text())
    assert set(fixture[0]) == set(_sample())
