# Interconnect Cost Calculator (AWS ↔ GCP Seoul)

A modern monthly cost calculator and architecture analytics tool comparing connectivity options between **AWS Seoul (`ap-northeast-2`)** and **GCP Seoul (`asia-northeast3`)**, based on official public list prices.

## Options Compared

| Option | Description | Typical Use Case |
|---|---|---|
| **Option A** | AWS Direct Connect + GCP Dedicated Interconnect | Enterprise colo hub with customer-owned router |
| **Option B** | Cross-Cloud Interconnect (CCI) | Google-managed direct link, zero colo footprint |
| **Option C** | HA VPN over public internet (IPsec + AWS TGW ECMP) | Fast setup, dev/staging, backup link, or < 15 TB/mo |

## Features

- **Line-item Breakdown:** Detailed fixed infrastructure, AWS→GCP egress, and GCP→AWS egress accounting.
- **Bidirectional Analytics:** Real-time transfer time estimation for both directions (AWS → GCP and GCP → AWS) formatted in sec/min/hr/days.
- **Visual Composition Charts:** Visual stacked bar chart illustrating fixed infra vs directional egress breakdowns.
- **Capacity & Utilization Gauge:** Link capacity meter with traffic health alerts (<70% green, 70-100% warning, >100% danger).
- **Multi-language Support (EN / KO):** Seamless English and 한국어 language toggle (preserving industry-standard technical terminology).
- **Unit Precision:** Full decimal-GB ($10^9$ B) vs binary-GiB ($2^{30}$ B) billing math.
- **Export Formats:** Full CSV and GitHub-flavored Markdown export support in the selected language.
- **Architecture Documentation:** Integrated interactive `/guide` and raw `/guide.md` documentation endpoints.
- **HTMX Reactive UI:** Real-time recalculation without heavy JavaScript client frameworks.

## HA VPN Scaling Model (Option C)

- Per IPsec tunnel effective throughput ~1.25 Gbps (single flow)
- 2 tunnels: basic HA (Active/Active on 1 AWS S2S VPN connection)
- >2 tunnels: AWS Transit Gateway ECMP required — adds TGW attachment ($0.05/hr) + data processing ($0.02/GB)
- Presets: 2 / 4 / 8 / 16 tunnels (→ ~2.5 / 5 / 10 / 20 Gbps aggregate)

## Pricing Sources (as of 2026-08)

- [AWS Direct Connect pricing](https://aws.amazon.com/directconnect/pricing/)
- [AWS Site-to-Site VPN pricing](https://aws.amazon.com/vpn/pricing/)
- [AWS Transit Gateway pricing](https://aws.amazon.com/transit-gateway/pricing/)
- [AWS EC2 Data Transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [GCP Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/docs/interconnect/pricing)
- [GCP Cross-Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview)
- [GCP VPC network pricing](https://cloud.google.com/vpc/network-pricing)

Prices are cross-checked against the AWS Pricing API and GCP Cloud Billing Catalog API. See [`pricing.json`](./pricing.json).

## Local Development & Testing

```bash
# Setup virtual environment and dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest httpx

# Run automated test suite
pytest -v

# Start development server
uvicorn main:app --reload --port 8080
```

Visit [http://localhost:8080/](http://localhost:8080/) or [http://localhost:8080/guide](http://localhost:8080/guide)

## License

MIT
