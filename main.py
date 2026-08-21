from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import markdown as md_lib
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from i18n import get_t

BASE_DIR = Path(__file__).parent
PRICING = json.loads((BASE_DIR / "pricing.json").read_text(encoding="utf-8"))

# Unit factor to bytes.
# TB / PB are decimal (SI): 1 TB = 10^12 B, 1 PB = 10^15 B.
# TiB / PiB are binary (IEC): 1 TiB = 2^40 B, 1 PiB = 2^50 B.
UNIT_TO_BYTES = {
    "TB":  10 ** 12,
    "TiB": 2  ** 40,
    "PB":  10 ** 15,
    "PiB": 2  ** 50,
}
GB_BYTES  = 10 ** 9   # AWS bills DTO per decimal GB
GIB_BYTES = 2  ** 30  # GCP bills Interconnect egress per binary GiB

app = FastAPI(title="Interconnect Cost Calculator")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _fmt(n: float) -> str:
    return f"${n:,.2f}"


def _fmt_hours(h: float, lang: str = "en") -> str:
    if h <= 0:
        return "0분" if lang == "ko" else "0 min"
    if h < 1 / 60:
        sec = h * 3600
        return f"{sec:.0f}초" if lang == "ko" else f"{sec:.0f} sec"
    if h < 1:
        minutes = h * 60
        return f"{minutes:.0f}분" if lang == "ko" else f"{minutes:.0f} min"
    if h < 24:
        return f"{h:.1f}시간" if lang == "ko" else f"{h:.1f} h"
    days = h / 24
    return f"{h:.1f}시간 ({days:.1f}일)" if lang == "ko" else f"{h:.1f} h ({days:.1f} d)"


templates.env.filters["money"] = _fmt
templates.env.filters["hours"] = _fmt_hours


def _tiered_cost_gb(amount_gb: float, tiers: list[dict]) -> float:
    """Apply tiered pricing where each tier starts at start_gb."""
    if amount_gb <= 0:
        return 0.0
    cost = 0.0
    for i, tier in enumerate(tiers):
        start = tier["start_gb"]
        price = tier["price"]
        next_start = tiers[i + 1]["start_gb"] if i + 1 < len(tiers) else float("inf")
        tier_size = next_start - start
        if amount_gb > start:
            in_tier = min(amount_gb - start, tier_size)
            cost += in_tier * price
    return cost


def _tiered_cost_gib(amount_gib: float, tiers: list[dict]) -> float:
    """Apply tiered pricing where each tier starts at start_gib."""
    if amount_gib <= 0:
        return 0.0
    cost = 0.0
    for i, tier in enumerate(tiers):
        start = tier["start_gib"]
        price = tier["price"]
        next_start = tiers[i + 1]["start_gib"] if i + 1 < len(tiers) else float("inf")
        tier_size = next_start - start
        if amount_gib > start:
            in_tier = min(amount_gib - start, tier_size)
            cost += in_tier * price
    return cost


def _transfer_time_hours(bytes_total: float, effective_gbps: float) -> float:
    if effective_gbps <= 0 or bytes_total <= 0:
        return 0.0
    bits = bytes_total * 8.0
    return bits / (effective_gbps * 1e9) / 3600.0


def calculate(
    amount_a2g: float,
    amount_g2a: float,
    unit: str = "TB",
    port_gbps: Literal[10, 100] | int = 10,
    link_count: int = 2,
    colo_per_link_monthly: float = 0.0,
    vpn_tunnels: int = 2,
    lang: str = "en",
) -> dict:
    hours = PRICING["hours_per_month"]
    aws_dx = PRICING["aws_dx"]
    gcp_di = PRICING["gcp_di"]
    gcp_cci = PRICING["gcp_cci"]
    vpn = PRICING["ha_vpn"]
    eff_ratio = PRICING["transfer_time"]["interconnect_efficiency"]

    lang_code = "ko" if str(lang).lower() in ("ko", "kr", "korean") else "en"
    t = get_t(lang_code)

    # Sanitize inputs
    amount_a2g = max(0.0, float(amount_a2g))
    amount_g2a = max(0.0, float(amount_g2a))
    link_count = max(1, int(link_count))
    vpn_tunnels = max(2, int(vpn_tunnels))
    colo_per_link_monthly = max(0.0, float(colo_per_link_monthly))

    port_gbps_val = 100 if int(port_gbps) == 100 else 10
    key = str(port_gbps_val)

    if unit not in UNIT_TO_BYTES:
        unit = "TB"
    factor = UNIT_TO_BYTES[unit]

    bytes_a2g = amount_a2g * factor
    bytes_g2a = amount_g2a * factor
    bytes_total = bytes_a2g + bytes_g2a

    # AWS bills Data Transfer Out in decimal GB; GCP bills Interconnect egress in binary GiB.
    gb_a2g = bytes_a2g / GB_BYTES
    gib_g2a = bytes_g2a / GIB_BYTES
    total_gb = bytes_total / GB_BYTES

    aws_dto_a2g = gb_a2g * aws_dx["dto_seoul_local_per_gb"]
    gcp_egress_g2a_ic = gib_g2a * gcp_di["egress_asia_to_asia_per_gib"]

    # --- Option A: AWS DX + GCP DI ---
    a_aws_port = aws_dx["port_hourly"][key] * hours * link_count
    a_gcp_port = gcp_di["port_hourly"][key] * hours * link_count
    a_gcp_vlan = gcp_di["vlan_attachment_hourly"][key] * hours * link_count
    a_colo = colo_per_link_monthly * link_count
    a_infra = a_aws_port + a_gcp_port + a_gcp_vlan + a_colo
    a_total = a_infra + aws_dto_a2g + gcp_egress_g2a_ic
    a_bw_gbps = port_gbps_val * link_count * eff_ratio
    a_time_a2g_h = _transfer_time_hours(bytes_a2g, a_bw_gbps)
    a_time_g2a_h = _transfer_time_hours(bytes_g2a, a_bw_gbps)
    a_time_total_h = _transfer_time_hours(bytes_total, a_bw_gbps)

    # --- Option B: Cross-Cloud Interconnect ---
    b_aws_port = aws_dx["port_hourly"][key] * hours * link_count
    b_gcp_port = gcp_cci["port_hourly"][key] * hours * link_count
    b_gcp_vlan = gcp_cci["vlan_attachment_hourly"][key] * hours * link_count
    b_infra = b_aws_port + b_gcp_port + b_gcp_vlan
    b_total = b_infra + aws_dto_a2g + gcp_egress_g2a_ic
    b_bw_gbps = port_gbps_val * link_count * eff_ratio
    b_time_a2g_h = _transfer_time_hours(bytes_a2g, b_bw_gbps)
    b_time_g2a_h = _transfer_time_hours(bytes_g2a, b_bw_gbps)
    b_time_total_h = _transfer_time_hours(bytes_total, b_bw_gbps)

    # --- Option C: HA VPN (scales via TGW ECMP) ---
    tunnels = vpn_tunnels
    # Each AWS Site-to-Site VPN connection has 2 tunnels
    aws_vpn_connections = max(1, tunnels // 2)
    uses_tgw = tunnels > 2

    c_gcp_tunnel = vpn["gcp_vpn_tunnel_hourly_seoul"] * tunnels * hours
    c_aws_vpn = vpn["aws_vpn_connection_hourly"] * aws_vpn_connections * hours
    if uses_tgw:
        c_aws_tgw_attach = vpn["aws_tgw_attachment_hourly"] * aws_vpn_connections * hours
        c_aws_tgw_data = vpn["aws_tgw_data_processing_per_gb"] * gb_a2g
    else:
        c_aws_tgw_attach = 0.0
        c_aws_tgw_data = 0.0

    c_infra = c_gcp_tunnel + c_aws_vpn + c_aws_tgw_attach
    # AWS Internet egress (tiered) for A→G direction
    c_aws_internet_egress = _tiered_cost_gb(gb_a2g, vpn["aws_internet_egress_seoul_tiers_per_gb"])
    # GCP Internet egress (tiered) for G→A direction (Seoul → South Korea)
    c_gcp_internet_egress = _tiered_cost_gib(gib_g2a, vpn["gcp_internet_egress_seoul_to_korea_tiers_per_gib"])
    c_total = c_infra + c_aws_internet_egress + c_aws_tgw_data + c_gcp_internet_egress
    c_bw_gbps = tunnels * vpn["per_tunnel_effective_gbps"]
    c_time_a2g_h = _transfer_time_hours(bytes_a2g, c_bw_gbps)
    c_time_g2a_h = _transfer_time_hours(bytes_g2a, c_bw_gbps)
    c_time_total_h = _transfer_time_hours(bytes_total, c_bw_gbps)

    # capacity utilization (Gbps average vs aggregate link capacity)
    total_bits = bytes_total * 8.0
    avg_gbps = total_bits / (hours * 3600.0) / 1e9
    aggregate_gbps = port_gbps_val * link_count
    utilization = (avg_gbps / aggregate_gbps) * 100.0 if aggregate_gbps else 0.0

    # Cost per GB metrics (based on total transferred decimal GB)
    per_gb_a = a_total / total_gb if total_gb > 0 else 0.0
    per_gb_b = b_total / total_gb if total_gb > 0 else 0.0
    per_gb_c = c_total / total_gb if total_gb > 0 else 0.0

    pct_a2g = (bytes_a2g / bytes_total * 100.0) if bytes_total else 0.0
    pct_g2a = (bytes_g2a / bytes_total * 100.0) if bytes_total else 0.0

    # Determine cheapest option
    totals = {"A": a_total, "B": b_total, "C": c_total}
    cheaper = min(totals, key=totals.get)

    # Percentages for visual breakdown charts
    def _pcts(infra: float, eg_a2g: float, eg_g2a: float, tot: float) -> tuple[float, float, float]:
        if tot <= 0:
            return 100.0, 0.0, 0.0
        return (infra / tot * 100.0), (eg_a2g / tot * 100.0), (eg_g2a / tot * 100.0)

    a_infra_pct, a_eg_a2g_pct, a_eg_g2a_pct = _pcts(a_infra, aws_dto_a2g, gcp_egress_g2a_ic, a_total)
    b_infra_pct, b_eg_a2g_pct, b_eg_g2a_pct = _pcts(b_infra, aws_dto_a2g, gcp_egress_g2a_ic, b_total)
    c_infra_pct, c_eg_a2g_pct, c_eg_g2a_pct = _pcts(c_infra, c_aws_internet_egress + c_aws_tgw_data, c_gcp_internet_egress, c_total)

    # ---------------- Break-even & Curve Points ----------------
    ratio_a2g = (amount_a2g / (amount_a2g + amount_g2a)) if (amount_a2g + amount_g2a) > 0 else 0.5
    ratio_g2a = 1.0 - ratio_a2g

    def _calc_totals_at_tb(v_tb: float) -> tuple[float, float, float]:
        v_bytes_a2g = v_tb * (10**12) * ratio_a2g
        v_bytes_g2a = v_tb * (10**12) * ratio_g2a
        v_gb_a2g = v_bytes_a2g / GB_BYTES
        v_gib_g2a = v_bytes_g2a / GIB_BYTES

        v_aws_dto = v_gb_a2g * aws_dx["dto_seoul_local_per_gb"]
        v_gcp_egress = v_gib_g2a * gcp_di["egress_asia_to_asia_per_gib"]

        tot_a = a_infra + v_aws_dto + v_gcp_egress
        tot_b = b_infra + v_aws_dto + v_gcp_egress

        v_c_aws_eg = _tiered_cost_gb(v_gb_a2g, vpn["aws_internet_egress_seoul_tiers_per_gb"])
        v_c_tgw_data = (vpn["aws_tgw_data_processing_per_gb"] * v_gb_a2g) if uses_tgw else 0.0
        v_c_gcp_eg = _tiered_cost_gib(v_gib_g2a, vpn["gcp_internet_egress_seoul_to_korea_tiers_per_gib"])
        tot_c = c_infra + v_c_aws_eg + v_c_tgw_data + v_c_gcp_eg
        return tot_a, tot_b, tot_c

    # Find crossover where B becomes cheaper than C
    low, high = 0.0, 500.0
    crossover_tb = None
    if _calc_totals_at_tb(0.0)[1] > _calc_totals_at_tb(0.0)[2]:
        for _ in range(30):
            mid = (low + high) / 2.0
            _, mid_b, mid_c = _calc_totals_at_tb(mid)
            if mid_b < mid_c:
                high = mid
                crossover_tb = mid
            else:
                low = mid

    current_tb = bytes_total / (10**12)
    base_max = max(100.0, round(current_tb * 1.5, -1))
    if crossover_tb:
        max_curve_tb = max(base_max, round(crossover_tb * 1.5, -1))
    else:
        max_curve_tb = base_max

    sample_vols = sorted(list(set([
        0.0,
        round(max_curve_tb * 0.1, 1),
        round(max_curve_tb * 0.25, 1),
        round(max_curve_tb * 0.5, 1),
        round(max_curve_tb * 0.75, 1),
        round(max_curve_tb, 1),
        round(current_tb, 1) if current_tb > 0 else 0.0,
        round(crossover_tb, 1) if (crossover_tb and 0 < crossover_tb <= max_curve_tb) else 0.0
    ])))

    curve_points = []
    max_cost_in_curve = 1.0
    for sv in sample_vols:
        if sv <= 0 and curve_points:
            continue
        ta, tb, tc = _calc_totals_at_tb(sv)
        max_cost_in_curve = max(max_cost_in_curve, ta, tb, tc)
        curve_points.append({
            "vol_tb": sv,
            "cost_a": ta,
            "cost_b": tb,
            "cost_c": tc,
        })

    return {
        "inputs": {
            "unit": unit,
            "amount_a2g": amount_a2g,
            "amount_g2a": amount_g2a,
            "amount_total": amount_a2g + amount_g2a,
            "bytes_total": bytes_total,
            "bytes_a2g": bytes_a2g,
            "bytes_g2a": bytes_g2a,
            "port_gbps": port_gbps_val,
            "link_count": link_count,
            "colo_per_link_monthly": colo_per_link_monthly,
            "vpn_tunnels": tunnels,
            "aws_vpn_connections": aws_vpn_connections,
            "uses_tgw": uses_tgw,
            "pct_a2g": pct_a2g,
            "pct_g2a": pct_g2a,
            "total_tb": bytes_total / (10 ** 12),
            "total_tib": bytes_total / (2 ** 40),
            "lang": lang_code,
        },
        "option_a": {
            "label": "AWS DX + GCP Dedicated Interconnect",
            "infra": {
                "subtotal": a_infra,
                "aws_port": a_aws_port,
                "gcp_port": a_gcp_port,
                "gcp_vlan": a_gcp_vlan,
                "colo": a_colo,
            },
            "egress_a2g": {"subtotal": aws_dto_a2g, "aws_dto": aws_dto_a2g},
            "egress_g2a": {"subtotal": gcp_egress_g2a_ic, "gcp_egress": gcp_egress_g2a_ic},
            "total": a_total,
            "per_gb": per_gb_a,
            "bw_gbps": a_bw_gbps,
            "time_h": a_time_a2g_h,
            "time_a2g_h": a_time_a2g_h,
            "time_g2a_h": a_time_g2a_h,
            "time_total_h": a_time_total_h,
            "infra_pct": a_infra_pct,
            "egress_a2g_pct": a_eg_a2g_pct,
            "egress_g2a_pct": a_eg_g2a_pct,
        },
        "option_b": {
            "label": "Cross-Cloud Interconnect",
            "infra": {
                "subtotal": b_infra,
                "aws_port": b_aws_port,
                "gcp_port": b_gcp_port,
                "gcp_vlan": b_gcp_vlan,
            },
            "egress_a2g": {"subtotal": aws_dto_a2g, "aws_dto": aws_dto_a2g},
            "egress_g2a": {"subtotal": gcp_egress_g2a_ic, "gcp_egress": gcp_egress_g2a_ic},
            "total": b_total,
            "per_gb": per_gb_b,
            "bw_gbps": b_bw_gbps,
            "time_h": b_time_a2g_h,
            "time_a2g_h": b_time_a2g_h,
            "time_g2a_h": b_time_g2a_h,
            "time_total_h": b_time_total_h,
            "infra_pct": b_infra_pct,
            "egress_a2g_pct": b_eg_a2g_pct,
            "egress_g2a_pct": b_eg_g2a_pct,
        },
        "option_c": {
            "label": f"HA VPN ({tunnels} tunnels{' + TGW ECMP' if uses_tgw else ''})",
            "infra": {
                "subtotal": c_infra,
                "gcp_tunnel": c_gcp_tunnel,
                "aws_vpn": c_aws_vpn,
                "aws_tgw_attach": c_aws_tgw_attach,
            },
            "egress_a2g": {
                "subtotal": c_aws_internet_egress + c_aws_tgw_data,
                "aws_internet_egress": c_aws_internet_egress,
                "aws_tgw_data": c_aws_tgw_data,
            },
            "egress_g2a": {
                "subtotal": c_gcp_internet_egress,
                "gcp_internet_egress": c_gcp_internet_egress,
            },
            "total": c_total,
            "per_gb": per_gb_c,
            "bw_gbps": c_bw_gbps,
            "time_h": c_time_a2g_h,
            "time_a2g_h": c_time_a2g_h,
            "time_g2a_h": c_time_g2a_h,
            "time_total_h": c_time_total_h,
            "uses_tgw": uses_tgw,
            "infra_pct": c_infra_pct,
            "egress_a2g_pct": c_eg_a2g_pct,
            "egress_g2a_pct": c_eg_g2a_pct,
        },
        "comparison": {
            "cheaper": cheaper,
            "totals": totals,
        },
        "capacity": {
            "avg_gbps": avg_gbps,
            "aggregate_gbps": aggregate_gbps,
            "utilization_pct": utilization,
            "over_capacity": utilization > 100.0,
        },
        "breakeven": {
            "crossover_tb": crossover_tb,
            "has_crossover": crossover_tb is not None,
            "curve_points": curve_points,
            "max_curve_tb": max_curve_tb,
            "max_cost_in_curve": max_cost_in_curve,
        },
        "pricing_as_of": PRICING["as_of"],
        "t": t,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, lang: str = "en"):
    lang_code = "ko" if str(lang).lower() in ("ko", "kr", "korean") else "en"
    t = get_t(lang_code)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "pricing_as_of": PRICING["as_of"],
            "sources": PRICING["sources"],
            "lang": lang_code,
            "t": t,
        },
    )


@app.post("/calculate", response_class=HTMLResponse)
async def calc(
    request: Request,
    amount_a2g: float = Form(...),
    amount_g2a: float = Form(...),
    unit: str = Form("TB"),
    port_gbps: int = Form(10),
    link_count: int = Form(2),
    colo_per_link_monthly: float = Form(0.0),
    vpn_tunnels: int = Form(2),
    lang: str = Form("en"),
):
    ctx = calculate(
        amount_a2g=amount_a2g,
        amount_g2a=amount_g2a,
        unit=unit,
        port_gbps=port_gbps,
        link_count=link_count,
        colo_per_link_monthly=colo_per_link_monthly,
        vpn_tunnels=vpn_tunnels,
        lang=lang,
    )
    return templates.TemplateResponse(request, "_result.html", ctx)


# ---------------- Export ----------------

def _scenario_slug(ctx: dict) -> str:
    i = ctx["inputs"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    return (
        f"interconnect-calc_"
        f"{int(round(i['amount_a2g']))}+{int(round(i['amount_g2a']))}{i['unit']}_"
        f"{i['port_gbps']}G-x{i['link_count']}_vpn{i['vpn_tunnels']}t_{stamp}"
    )


def _render_csv(ctx: dict, lang: str = "en") -> str:
    i = ctx["inputs"]
    a, b, c = ctx["option_a"], ctx["option_b"], ctx["option_c"]
    cmp_ = ctx["comparison"]
    t = get_t(lang)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"{t['title']} — AWS Seoul (ap-northeast-2) <-> GCP Seoul (asia-northeast3)"])
    w.writerow([t["prices_as_of"], ctx["pricing_as_of"]])
    w.writerow(["Currency", "USD (monthly, list price only)"])
    w.writerow(["Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")])
    w.writerow([])
    w.writerow(["INPUTS"])
    w.writerow([t["unit_label"], i["unit"]])
    w.writerow([f"{t['a2g_label']} ({i['unit']})", f"{i['amount_a2g']:.4f}"])
    w.writerow([f"{t['g2a_label']} ({i['unit']})", f"{i['amount_g2a']:.4f}"])
    w.writerow([f"Total transfer ({i['unit']})", f"{i['amount_total']:.4f}"])
    w.writerow(["Total transfer (TB, decimal)", f"{i['total_tb']:.4f}"])
    w.writerow(["Total transfer (TiB, binary)", f"{i['total_tib']:.4f}"])
    w.writerow([t["port_speed_label"], i["port_gbps"]])
    w.writerow([t["link_count_label"], i["link_count"]])
    w.writerow([t["vpn_tunnels_label"], i["vpn_tunnels"]])
    w.writerow([f"{t['colo_label']} (USD)", f"{i['colo_per_link_monthly']:.2f}"])
    w.writerow([])
    w.writerow(["BREAKDOWN (USD/month)"])
    w.writerow(["Category", t["line_item"], "Option A", "Option B", "Option C"])
    w.writerow([f"1) Infrastructure ({t['fixed_cost']})",
                f"Port / Tunnel × {i['link_count']}/{i['link_count']}/{i['vpn_tunnels']}",
                f"{a['infra']['subtotal']:.2f}",
                f"{b['infra']['subtotal']:.2f}",
                f"{c['infra']['subtotal']:.2f}"])
    w.writerow([f"2) AWS -> GCP egress ({t['traffic_based']})",
                f"{i['amount_a2g']:.2f} {i['unit']}",
                f"{a['egress_a2g']['subtotal']:.2f}",
                f"{b['egress_a2g']['subtotal']:.2f}",
                f"{c['egress_a2g']['subtotal']:.2f}"])
    w.writerow([f"3) GCP -> AWS egress ({t['traffic_based']})",
                f"{i['amount_g2a']:.2f} {i['unit']}",
                f"{a['egress_g2a']['subtotal']:.2f}",
                f"{b['egress_g2a']['subtotal']:.2f}",
                f"{c['egress_g2a']['subtotal']:.2f}"])
    w.writerow([t["monthly_total"], "",
                f"{a['total']:.2f}", f"{b['total']:.2f}", f"{c['total']:.2f}"])
    w.writerow([t["effective_bw"], "",
                f"{a['bw_gbps']:.2f}", f"{b['bw_gbps']:.2f}", f"{c['bw_gbps']:.2f}"])
    w.writerow([f"{t['transfer_time_a2g']} ({i['amount_a2g']:.2f} {i['unit']})", "",
                _fmt_hours(a["time_a2g_h"], lang), _fmt_hours(b["time_a2g_h"], lang), _fmt_hours(c["time_a2g_h"], lang)])
    w.writerow([f"{t['transfer_time_g2a']} ({i['amount_g2a']:.2f} {i['unit']})", "",
                _fmt_hours(a["time_g2a_h"], lang), _fmt_hours(b["time_g2a_h"], lang), _fmt_hours(c["time_g2a_h"], lang)])
    w.writerow([])
    w.writerow([t["cheapest_verdict"], f"Option {cmp_['cheaper']}"])
    w.writerow([])
    w.writerow(["NOTES"])
    w.writerow(["List price only. No enterprise discounts (AWS EDP/PPA, GCP CUD), no free tiers, no promotional credits."])
    w.writerow([t["note_c"]])
    w.writerow([t["note_transfer"]])
    w.writerow([t["billing_granularity"]])
    return buf.getvalue()


def _render_markdown(ctx: dict, lang: str = "en") -> str:
    i = ctx["inputs"]
    a, b, c = ctx["option_a"], ctx["option_b"], ctx["option_c"]
    cmp_ = ctx["comparison"]
    t = get_t(lang)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    m = _fmt

    lines = []
    lines.append(f"# {t['title']} — Result")
    lines.append("")
    lines.append(f"**Route:** AWS Seoul (`ap-northeast-2`) ↔ GCP Seoul (`asia-northeast3`)  ")
    lines.append(f"**{t['prices_as_of']}:** {ctx['pricing_as_of']}  ")
    lines.append(f"**Generated:** {ts}  ")
    lines.append("**Currency:** USD (monthly, list price only)")
    lines.append("")
    lines.append(f"## {t['inputs_heading']}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| {t['unit_label']} | `{i['unit']}` |")
    lines.append(f"| {t['a2g_label']} | {i['amount_a2g']:.2f} {i['unit']} |")
    lines.append(f"| {t['g2a_label']} | {i['amount_g2a']:.2f} {i['unit']} |")
    lines.append(f"| Total transfer | {i['amount_total']:.2f} {i['unit']} = {i['total_tb']:.2f} TB = {i['total_tib']:.2f} TiB |")
    lines.append(f"| {t['port_speed_label']} | {i['port_gbps']} Gbps × {i['link_count']} |")
    lines.append(f"| {t['vpn_tunnels_label']} | {i['vpn_tunnels']}{' (via TGW ECMP)' if i['uses_tgw'] else ''} |")
    lines.append(f"| {t['colo_label']} | {m(i['colo_per_link_monthly'])} / month / link |")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **{t['opt_a_label']}:** {m(a['total'])} / month · {a['bw_gbps']:.1f} Gbps eff · Transfer times: A→G {_fmt_hours(a['time_a2g_h'], lang)}, G→A {_fmt_hours(a['time_g2a_h'], lang)}")
    lines.append(f"- **{t['opt_b_label']}:** {m(b['total'])} / month · {b['bw_gbps']:.1f} Gbps eff · Transfer times: A→G {_fmt_hours(b['time_a2g_h'], lang)}, G→A {_fmt_hours(b['time_g2a_h'], lang)}")
    lines.append(f"- **{t['opt_c_label']} ({i['vpn_tunnels']} tunnels):** {m(c['total'])} / month · {c['bw_gbps']:.1f} Gbps eff · Transfer times: A→G {_fmt_hours(c['time_a2g_h'], lang)}, G→A {_fmt_hours(c['time_g2a_h'], lang)}")
    lines.append("")
    lines.append(f"**{t['cheapest_verdict']}** Option **{cmp_['cheaper']}**")
    lines.append("")
    lines.append("## Cost breakdown (USD / month)")
    lines.append("")
    lines.append("| Category | Option A | Option B | Option C |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| ① Infrastructure ({t['fixed_cost']}) | {m(a['infra']['subtotal'])} | {m(b['infra']['subtotal'])} | {m(c['infra']['subtotal'])} |")
    lines.append(f"| ② AWS → GCP egress ({t['traffic_based']}) | {m(a['egress_a2g']['subtotal'])} | {m(b['egress_a2g']['subtotal'])} | {m(c['egress_a2g']['subtotal'])} |")
    lines.append(f"| ③ GCP → AWS egress ({t['traffic_based']}) | {m(a['egress_g2a']['subtotal'])} | {m(b['egress_g2a']['subtotal'])} | {m(c['egress_g2a']['subtotal'])} |")
    lines.append(f"| **{t['monthly_total']}** | **{m(a['total'])}** | **{m(b['total'])}** | **{m(c['total'])}** |")
    lines.append(f"| {t['effective_bw']} | {a['bw_gbps']:.1f} Gbps | {b['bw_gbps']:.1f} Gbps | {c['bw_gbps']:.1f} Gbps |")
    lines.append(f"| {t['transfer_time_a2g']} | {_fmt_hours(a['time_a2g_h'], lang)} | {_fmt_hours(b['time_a2g_h'], lang)} | {_fmt_hours(c['time_a2g_h'], lang)} |")
    lines.append(f"| {t['transfer_time_g2a']} | {_fmt_hours(a['time_g2a_h'], lang)} | {_fmt_hours(b['time_g2a_h'], lang)} | {_fmt_hours(c['time_g2a_h'], lang)} |")
    lines.append("")
    lines.append("## Notes")
    lines.append("- List price only. No enterprise discounts, no free tiers, no promotional credits.")
    lines.append(f"- {t['note_c']}")
    lines.append(f"- {t['note_transfer']}")
    lines.append(f"- {t['billing_granularity']}")
    lines.append("")
    return "\n".join(lines)


def _parse_export_inputs(
    amount_a2g: float,
    amount_g2a: float,
    unit: str,
    port_gbps: int,
    link_count: int,
    colo_per_link_monthly: float,
    vpn_tunnels: int,
    lang: str = "en",
) -> dict:
    return calculate(
        amount_a2g=amount_a2g,
        amount_g2a=amount_g2a,
        unit=unit,
        port_gbps=port_gbps,
        link_count=link_count,
        colo_per_link_monthly=colo_per_link_monthly,
        vpn_tunnels=vpn_tunnels,
        lang=lang,
    )


@app.post("/export/csv")
async def export_csv(
    amount_a2g: float = Form(...),
    amount_g2a: float = Form(...),
    unit: str = Form("TB"),
    port_gbps: int = Form(10),
    link_count: int = Form(2),
    colo_per_link_monthly: float = Form(0.0),
    vpn_tunnels: int = Form(2),
    lang: str = Form("en"),
):
    ctx = _parse_export_inputs(
        amount_a2g, amount_g2a, unit, port_gbps, link_count, colo_per_link_monthly, vpn_tunnels, lang
    )
    body = _render_csv(ctx, lang=lang)
    filename = f"{_scenario_slug(ctx)}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/export/md")
async def export_md(
    amount_a2g: float = Form(...),
    amount_g2a: float = Form(...),
    unit: str = Form("TB"),
    port_gbps: int = Form(10),
    link_count: int = Form(2),
    colo_per_link_monthly: float = Form(0.0),
    vpn_tunnels: int = Form(2),
    lang: str = Form("en"),
):
    ctx = _parse_export_inputs(
        amount_a2g, amount_g2a, unit, port_gbps, link_count, colo_per_link_monthly, vpn_tunnels, lang
    )
    body = _render_markdown(ctx, lang=lang)
    filename = f"{_scenario_slug(ctx)}.md"
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


GUIDE_PATH = BASE_DIR / "USER_GUIDE.md"
_GUIDE_CACHE: dict = {"mtime": 0.0, "html": ""}


def _render_guide_html() -> str:
    mtime = GUIDE_PATH.stat().st_mtime
    if _GUIDE_CACHE["mtime"] != mtime or not _GUIDE_CACHE["html"]:
        text = GUIDE_PATH.read_text(encoding="utf-8")
        _GUIDE_CACHE["html"] = md_lib.markdown(
            text,
            extensions=["extra", "tables", "toc", "sane_lists", "fenced_code"],
        )
        _GUIDE_CACHE["mtime"] = mtime
    return _GUIDE_CACHE["html"]


@app.get("/guide", response_class=HTMLResponse)
async def guide(request: Request, lang: str = "en"):
    lang_code = "ko" if str(lang).lower() in ("ko", "kr", "korean") else "en"
    t = get_t(lang_code)
    return templates.TemplateResponse(
        request,
        "guide.html",
        {
            "body_html": _render_guide_html(),
            "pricing_as_of": PRICING["as_of"],
            "lang": lang_code,
            "t": t,
        },
    )


@app.get("/guide.md", response_class=PlainTextResponse)
async def guide_md():
    return PlainTextResponse(GUIDE_PATH.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@app.get("/healthz")
async def healthz():
    return {"ok": True}
