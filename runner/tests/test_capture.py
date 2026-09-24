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


def test_parse_top_keeps_only_the_cell_nodes_and_the_loader():
    """kubectl top node is called without names (it accepts only one), so the
    parser has to drop the tools node and other cells itself."""
    node_text = (
        "ip-tools        49m   2%   775Mi  10%\n"
        "ip-loader      3200m  20%  700Mi   2%\n"
        "ip-sut         9000m  57%  30000Mi 48%\n"
        "ip-other-cell   12m   0%   690Mi   1%\n"
    )
    s = capture.parse_top(node_text, "", "ip-sut", "ip-loader", keep={"ip-sut", "ip-loader"})
    assert s["loader_cpu_percent"] == 20 and s["loader_cpu_millicores"] == 3200
    assert s["node_cpu_percent"] == 57
    assert set(s["nodes"]) == {"ip-sut"}


def test_a_metrics_interval_lands_in_every_step_it_overlaps():
    t0 = 1_800_000_000
    windows = capture.ladder_windows(t0, 60, [10000, 20000])
    slack = capture.K6_START_SLACK_SECONDS
    assert windows == {10000: (t0, t0 + 60 + slack), 20000: (t0 + 60, t0 + 120 + slack)}
    samples = [{"ts": "x", "loader_cpu_percent": p, "loader_window": [t0 + b, t0 + e]}
               for b, e, p in ((0, 20, 10), (50, 70, 50), (130, 150, 99))]
    split = capture.by_overlap(samples, windows, "loader")
    assert [s["loader_cpu_percent"] for s in split[10000]] == [10, 50]
    assert [s["loader_cpu_percent"] for s in split[20000]] == [50]  # 130 s is past the ladder
    assert capture.loader_peak(split[20000]) == 50


def test_the_tail_of_a_step_is_still_that_steps_load():
    """k6 starts its scenario seconds after the container, so a step's load runs
    past its nominal end; a metrics window starting just after it still counts."""
    t0 = 1_800_000_000
    windows = capture.ladder_windows(t0, 60, [10000, 20000])
    late = [{"ts": "x", "loader_cpu_percent": 95, "loader_window": [t0 + 62, t0 + 80]}]
    assert capture.by_overlap(late, windows, "loader")[10000] == late


def test_an_unobserved_loader_has_no_peak_rather_than_zero():
    assert capture.loader_peak([{"ts": "x", "loader_cpu_percent": None}]) is None
    assert capture.loader_peak([]) is None


NODE_METRICS = json.dumps({"kind": "NodeMetricsList", "apiVersion": "metrics.k8s.io/v1beta1",
    "items": [
        {"metadata": {"name": "ip-loader"}, "timestamp": "2026-10-01T15:00:20Z",
         "window": "20.035s", "usage": {"cpu": "22400000000n", "memory": "1Gi"}},
        {"metadata": {"name": "ip-sut"}, "timestamp": "2026-10-01T15:00:18Z",
         "window": "1m0.5s", "usage": {"cpu": "9000m", "memory": "30Gi"}},
        {"metadata": {"name": "ip-tools"}, "timestamp": "2026-10-01T15:00:18Z",
         "window": "20s", "usage": {"cpu": "49m", "memory": "775Mi"}},
    ]})


def test_node_metrics_carry_their_own_interval_on_the_cluster_clock():
    from datetime import datetime
    s = capture.parse_node_metrics(NODE_METRICS, {"ip-loader": 32000, "ip-sut": 15750},
                                   "ip-sut", "ip-loader", keep={"ip-sut", "ip-loader"})
    end = datetime.fromisoformat("2026-10-01T15:00:20Z").timestamp()
    assert s["loader_window"] == [end - 20.035, end]
    assert (s["loader_cpu_millicores"], s["loader_cpu_percent"]) == (22400, 70)
    assert s["node_window"][1] - s["node_window"][0] == 60.5
    assert (s["node_cpu_millicores"], s["node_cpu_percent"]) == (9000, 57)
    assert set(s["nodes"]) == {"ip-sut"}


def test_an_unserved_metrics_api_is_none_so_the_sampler_falls_back():
    assert capture.parse_node_metrics("", {}, "a", "b") is None
    assert capture.parse_node_metrics('{"kind":"Status","code":503}', {}, "a", "b") is None


def test_a_node_without_allocatable_has_no_percent_rather_than_a_guess():
    s = capture.parse_node_metrics(NODE_METRICS, {}, "ip-sut", "ip-loader")
    assert s["loader_cpu_percent"] is None
    assert capture.loader_observed([s]) == []


def test_the_cpu_sample_is_recorded_before_the_actuator_is_asked(monkeypatch):
    """A stalled actuator must never cost the guard its CPU sample."""
    sampler = capture.TopSampler(["ip-sut"], "ip-loader",
                                 actuator={"proxy": "p", "path": "/x", "metrics": ["m"]})
    sampler._allocatable = {"ip-loader": 32000}
    monkeypatch.setattr(capture, "_top", lambda *a: {"ts": "t", "loader_cpu_percent": 10})

    def stalled(spec):
        assert sampler.samples and sampler.samples[0]["loader_cpu_percent"] == 10
        raise TimeoutError("actuator stalled")

    monkeypatch.setattr(capture, "_actuator", stalled)
    try:
        sampler._sample()
    except TimeoutError:
        pass
    assert sampler.samples == [{"ts": "t", "loader_cpu_percent": 10}]


def test_actuator_requests_carry_a_two_second_deadline(monkeypatch):
    seen = []
    monkeypatch.setattr(capture.config, "sh", lambda cmd, **k: seen.append(cmd) or "")
    assert capture._actuator({"proxy": "java:9966", "path": "/p", "metrics": ["m"]}) == {"m": None}
    assert "--request-timeout=2s" in seen[0]


def test_the_sampler_reads_the_metrics_api_and_falls_back_to_kubectl_top(monkeypatch):
    calls = []

    def fake_sh(cmd, **k):
        calls.append(" ".join(cmd))
        if "/apis/metrics.k8s.io/v1beta1/nodes" in cmd:
            return ""  # not served
        if cmd[:3] == ["kubectl", "top", "node"]:
            return NODES
        return PODS

    monkeypatch.setattr(capture.config, "sh", fake_sh)
    s = capture._top([SUT, OTHER], SUT, LOADER, {})
    assert s["source"] == "kubectl-top" and s["loader_cpu_percent"] == 32
    assert s["pod_cpu_millicores"] == 8493
    assert "--request-timeout=5s" in calls[0]


# --- Java's pool gauges -------------------------------------------------------

ACTUATOR = json.dumps({"name": "hikaricp.connections.pending", "baseUnit": "connections",
                       "measurements": [{"statistic": "VALUE", "value": 3.0}],
                       "availableTags": [{"tag": "pool", "values": ["HikariPool-1"]}]})


def test_an_actuator_gauge_is_its_value_statistic():
    assert capture.parse_actuator(ACTUATOR) == 3.0


def test_a_missing_actuator_meter_is_none_not_zero():
    # 404 through the service proxy, or an empty answer: not a pool at 0.
    assert capture.parse_actuator("") is None
    assert capture.parse_actuator('{"timestamp":"...","status":404,"error":"Not Found"}') is None


def test_actuator_stats_over_a_run():
    samples = [{"actuator": {"tomcat.threads.busy": v, "hikaricp.connections.pending": None}}
               for v in (10.0, 30.0, 20.0)]
    assert capture.actuator_stats(samples) == {
        "tomcat.threads.busy": {"max": 30.0, "median": 20.0, "samples": 3},
        "hikaricp.connections.pending": "missing",
    }
