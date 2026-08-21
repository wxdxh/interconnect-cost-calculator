from __future__ import annotations

import pytest
from main import (
    GB_BYTES,
    GIB_BYTES,
    PRICING,
    UNIT_TO_BYTES,
    _fmt,
    _fmt_hours,
    _tiered_cost_gb,
    _tiered_cost_gib,
    _transfer_time_hours,
    calculate,
)


def test_unit_constants():
    assert UNIT_TO_BYTES["TB"] == 10**12
    assert UNIT_TO_BYTES["TiB"] == 2**40
    assert UNIT_TO_BYTES["PB"] == 10**15
    assert UNIT_TO_BYTES["PiB"] == 2**50
    assert GB_BYTES == 10**9
    assert GIB_BYTES == 2**30


def test_tiered_cost_gb_aws():
    tiers = PRICING["ha_vpn"]["aws_internet_egress_seoul_tiers_per_gb"]
    # 0 GB and negative
    assert _tiered_cost_gb(0, tiers) == 0.0
    assert _tiered_cost_gb(-10, tiers) == 0.0

    # 5,000 GB (Tier 1: $0.126)
    assert _tiered_cost_gb(5000, tiers) == pytest.approx(5000 * 0.126)

    # 30,000 GB (Tier 1: 10,000 * 0.126 = 1260; Tier 2: 20,000 * 0.122 = 2440) -> 3700.0
    assert _tiered_cost_gb(30000, tiers) == pytest.approx(1260.0 + 2440.0)

    # 100,000 GB (Tier 1: 10k*0.126=1260, Tier 2: 40k*0.122=4880, Tier 3: 50k*0.117=5850) -> 11,990.0
    assert _tiered_cost_gb(100000, tiers) == pytest.approx(1260.0 + 4880.0 + 5850.0)

    # 200,000 GB (Tier 1: 1260, Tier 2: 4880, Tier 3: 100k*0.117=11700, Tier 4: 50k*0.108=5400) -> 23,240.0
    assert _tiered_cost_gb(200000, tiers) == pytest.approx(1260.0 + 4880.0 + 11700.0 + 5400.0)


def test_tiered_cost_gib_gcp():
    tiers = PRICING["ha_vpn"]["gcp_internet_egress_seoul_to_korea_tiers_per_gib"]
    assert _tiered_cost_gib(0, tiers) == 0.0
    assert _tiered_cost_gib(-50, tiers) == 0.0

    # 500 GiB (Tier 1: 500 * 0.19 = 95.0)
    assert _tiered_cost_gib(500, tiers) == pytest.approx(95.0)

    # 5,000 GiB (Tier 1: 1024 * 0.19 = 194.56, Tier 2: 3976 * 0.18 = 715.68) -> 910.24
    assert _tiered_cost_gib(5000, tiers) == pytest.approx(194.56 + 715.68)

    # 20,000 GiB (Tier 1: 194.56, Tier 2: 9216 * 0.18 = 1658.88, Tier 3: 9760 * 0.15 = 1464.0) -> 3317.44
    assert _tiered_cost_gib(20000, tiers) == pytest.approx(194.56 + 1658.88 + 1464.0)


def test_transfer_time_calculation():
    # 10 TB transferred at 10 Gbps effective (10e9 bps)
    # bytes = 10 * 10^12 = 10^13 B. bits = 8 * 10^13
    # time = (8 * 10^13) / (10 * 10^9) / 3600 = 80000 / 3600 = 22.222 hrs
    h = _transfer_time_hours(10 * (10**12), 10.0)
    assert h == pytest.approx((8 * 10**13) / (10 * 1e9) / 3600.0)
    assert _transfer_time_hours(0, 10.0) == 0.0
    assert _transfer_time_hours(100, 0.0) == 0.0


def test_formatting_helpers():
    assert _fmt(1234.56) == "$1,234.56"
    assert _fmt(0.0) == "$0.00"
    assert _fmt_hours(0, "en") == "0 min"
    assert _fmt_hours(0.005, "en") == "18 sec"
    assert _fmt_hours(0.5, "en") == "30 min"
    assert _fmt_hours(5.2, "en") == "5.2 h"
    assert _fmt_hours(48.0, "en") == "48.0 h (2.0 d)"
    # Korean formatting
    assert _fmt_hours(0, "ko") == "0분"
    assert _fmt_hours(0.005, "ko") == "18초"
    assert _fmt_hours(0.5, "ko") == "30분"
    assert _fmt_hours(5.2, "ko") == "5.2시간"
    assert _fmt_hours(48.0, "ko") == "48.0시간 (2.0일)"


def test_calculate_with_language_ko():
    res = calculate(amount_a2g=50.0, amount_g2a=10.0, lang="ko")
    assert res["inputs"]["lang"] == "ko"
    assert res["t"]["title"] == "Interconnect 비용 계산기"
    assert "최저가" in res["t"]["cheapest_badge"]


def test_calculate_baseline_50tb_10tb():
    res = calculate(
        amount_a2g=50.0,
        amount_g2a=10.0,
        unit="TB",
        port_gbps=10,
        link_count=2,
        colo_per_link_monthly=200.0,
        vpn_tunnels=2,
    )

    hours = 730
    # Option A Infra:
    # AWS port: 2.25 * 730 * 2 = 3285.0
    # GCP port: 2.328 * 730 * 2 = 3398.88
    # GCP vlan: 0.10 * 730 * 2 = 146.0
    # Colo: 200 * 2 = 400.0
    # Infra subtotal = 7229.88
    a_infra = 3285.0 + 3398.88 + 146.0 + 400.0
    assert res["option_a"]["infra"]["subtotal"] == pytest.approx(a_infra)

    # AWS DTO: 50 TB = 50,000 GB * 0.041 = 2050.0
    assert res["option_a"]["egress_a2g"]["subtotal"] == pytest.approx(2050.0)

    # GCP Interconnect Egress: 10 TB = 10^13 B / 2^30 GiB * 0.042 = 391.1554
    expected_gcp_egress = (10 * 10**12 / 2**30) * 0.042
    assert res["option_a"]["egress_g2a"]["subtotal"] == pytest.approx(expected_gcp_egress)

    # Option B Infra (No colo):
    # AWS port: 3285.0, GCP CCI port: 5.60 * 730 * 2 = 8176.0, GCP vlan: 146.0 -> 11607.0
    assert res["option_b"]["infra"]["subtotal"] == pytest.approx(3285.0 + 8176.0 + 146.0)

    # Option C (2 tunnels, no TGW):
    # GCP tunnel: 0.075 * 2 * 730 = 109.5
    # AWS VPN: 0.05 * 1 * 730 = 36.5
    # TGW: 0
    assert res["option_c"]["infra"]["subtotal"] == pytest.approx(109.5 + 36.5)
    assert not res["option_c"]["uses_tgw"]

    # Bidirectional transfer times exist and are positive
    assert res["option_a"]["time_a2g_h"] > 0
    assert res["option_a"]["time_g2a_h"] > 0
    assert res["option_b"]["time_a2g_h"] > 0
    assert res["option_b"]["time_g2a_h"] > 0
    assert res["option_c"]["time_a2g_h"] > 0
    assert res["option_c"]["time_g2a_h"] > 0

    # Chart composition percentages sum to 100%
    assert res["option_a"]["infra_pct"] + res["option_a"]["egress_a2g_pct"] + res["option_a"]["egress_g2a_pct"] == pytest.approx(100.0)
    assert res["option_b"]["infra_pct"] + res["option_b"]["egress_a2g_pct"] + res["option_b"]["egress_g2a_pct"] == pytest.approx(100.0)
    assert res["option_c"]["infra_pct"] + res["option_c"]["egress_a2g_pct"] + res["option_c"]["egress_g2a_pct"] == pytest.approx(100.0)


def test_calculate_tgw_ecmp_scaling():
    # 4 tunnels triggers TGW
    res = calculate(
        amount_a2g=20.0,
        amount_g2a=5.0,
        unit="TB",
        port_gbps=10,
        link_count=2,
        vpn_tunnels=4,
    )
    c = res["option_c"]
    assert c["uses_tgw"] is True
    assert res["inputs"]["aws_vpn_connections"] == 2
    # GCP tunnel: 0.075 * 4 * 730 = 219.0
    # AWS VPN: 0.05 * 2 * 730 = 73.0
    # AWS TGW attach: 0.05 * 2 * 730 = 73.0
    assert c["infra"]["gcp_tunnel"] == pytest.approx(219.0)
    assert c["infra"]["aws_vpn"] == pytest.approx(73.0)
    assert c["infra"]["aws_tgw_attach"] == pytest.approx(73.0)
    # AWS TGW data processing: 20 TB = 20,000 GB * 0.02 = 400.0
    assert c["egress_a2g"]["aws_tgw_data"] == pytest.approx(400.0)


def test_calculate_extreme_tunnels():
    # 16 tunnels
    res = calculate(
        amount_a2g=50.0,
        amount_g2a=10.0,
        vpn_tunnels=16,
    )
    c = res["option_c"]
    assert c["uses_tgw"] is True
    assert res["inputs"]["aws_vpn_connections"] == 8
    # Effective bandwidth = 16 * 1.25 = 20 Gbps
    assert c["bw_gbps"] == pytest.approx(20.0)


def test_calculate_100g_ports():
    res = calculate(
        amount_a2g=100.0,
        amount_g2a=50.0,
        unit="TB",
        port_gbps=100,
        link_count=4,
    )
    # AWS 100G port: 22.50 * 730 * 4 = 65,700.0
    # GCP DI 100G port: 23.28 * 730 * 4 = 67,977.6
    # GCP DI 100G vlan: 1.00 * 730 * 4 = 2,920.0
    assert res["option_a"]["infra"]["aws_port"] == pytest.approx(65700.0)
    assert res["option_a"]["infra"]["gcp_port"] == pytest.approx(67977.6)
    assert res["option_a"]["infra"]["gcp_vlan"] == pytest.approx(2920.0)
    assert res["option_a"]["bw_gbps"] == pytest.approx(100 * 4 * 0.85)


def test_edge_case_zero_traffic():
    res = calculate(
        amount_a2g=0.0,
        amount_g2a=0.0,
        unit="TB",
        port_gbps=10,
        link_count=2,
    )
    assert res["option_a"]["per_gb"] == 0.0
    assert res["option_b"]["per_gb"] == 0.0
    assert res["option_c"]["per_gb"] == 0.0
    assert res["option_a"]["time_a2g_h"] == 0.0
    assert res["option_a"]["time_g2a_h"] == 0.0
    assert res["comparison"]["cheaper"] == "C"  # Lowest fixed infra is C
    assert res["capacity"]["utilization_pct"] == 0.0


def test_edge_case_asymmetric_traffic_g2a_only():
    res = calculate(
        amount_a2g=0.0,
        amount_g2a=100.0,
        unit="TB",
        port_gbps=10,
        link_count=2,
    )
    # total transferred is 100 TB = 100,000 GB
    total_gb = 100.0 * 10**12 / 10**9
    assert res["option_a"]["per_gb"] == pytest.approx(res["option_a"]["total"] / total_gb)
    assert res["option_a"]["time_a2g_h"] == 0.0
    assert res["option_a"]["time_g2a_h"] > 0.0


def test_edge_case_asymmetric_traffic_a2g_only():
    res = calculate(
        amount_a2g=100.0,
        amount_g2a=0.0,
        unit="TB",
        port_gbps=10,
        link_count=2,
    )
    total_gb = 100.0 * 10**12 / 10**9
    assert res["option_a"]["per_gb"] == pytest.approx(res["option_a"]["total"] / total_gb)
    assert res["option_a"]["time_a2g_h"] > 0.0
    assert res["option_a"]["time_g2a_h"] == 0.0


def test_edge_case_high_volume_pb_pib():
    res_pb = calculate(amount_a2g=5.0, amount_g2a=2.0, unit="PB", port_gbps=100, link_count=8)
    assert res_pb["inputs"]["bytes_total"] == 7 * 10**15
    assert res_pb["option_a"]["total"] > 0
    assert res_pb["capacity"]["over_capacity"] is True or res_pb["capacity"]["utilization_pct"] > 0

    res_pib = calculate(amount_a2g=5.0, amount_g2a=2.0, unit="PiB", port_gbps=100, link_count=8)
    assert res_pib["inputs"]["bytes_total"] == 7 * 2**50
    assert res_pib["option_a"]["total"] > 0


def test_edge_case_single_link_and_invalid_inputs():
    # Negative traffic, 0 link count, invalid unit should be safely clamped
    res = calculate(
        amount_a2g=-10.0,
        amount_g2a=-5.0,
        unit="INVALID",
        link_count=0,
        vpn_tunnels=1,
        colo_per_link_monthly=-50.0,
    )
    assert res["inputs"]["amount_a2g"] == 0.0
    assert res["inputs"]["amount_g2a"] == 0.0
    assert res["inputs"]["unit"] == "TB"
    assert res["inputs"]["link_count"] == 1
    assert res["inputs"]["vpn_tunnels"] == 2
    assert res["inputs"]["colo_per_link_monthly"] == 0.0


def test_breakeven_crossover_calculation():
    res = calculate(amount_a2g=50.0, amount_g2a=10.0, port_gbps=10, link_count=2, vpn_tunnels=2)
    bk = res["breakeven"]
    assert bk["has_crossover"] is True
    # For 10G 2-links ($11,607/mo fixed infra), crossover vs 2-tunnel VPN occurs around ~135 TB
    assert 50.0 < bk["crossover_tb"] < 200.0
    assert len(bk["curve_points"]) >= 4
    # At 0 TB, C should be cheaper than B
    assert bk["curve_points"][0]["cost_c"] < bk["curve_points"][0]["cost_b"]
    # At high volume (e.g. max curve), B should be cheaper than C
    assert bk["curve_points"][-1]["cost_b"] < bk["curve_points"][-1]["cost_c"]
