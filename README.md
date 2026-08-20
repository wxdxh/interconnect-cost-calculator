# Interconnect Cost Calculator (AWS ↔ GCP Seoul)

A monthly cost calculator that compares three connectivity options between **AWS Seoul (`ap-northeast-2`)** and **GCP Seoul (`asia-northeast3`)**, based on public list prices.

## Options compared

| Option | Description |
|---|---|
| **A** | AWS Direct Connect + GCP Dedicated Interconnect (customer-owned colo router hub) |
| **B** | Cross-Cloud Interconnect (Google-managed direct link, no customer colo) |
| **C** | HA VPN over public internet (IPsec, scales via AWS Transit Gateway ECMP) |

## Features

- Line-item breakdown (infrastructure + AWS→GCP egress + GCP→AWS egress)
- Effective bandwidth per option
- Transfer time estimation for the A→GCP direction (auto units: min / hr / day)
- Correct decimal-GB vs binary-GiB accounting (AWS bills decimal, GCP bills binary)
- CSV / Markdown export
- HTMX-based reactive UI (no JS framework)

## HA VPN scaling model (Option C)

- Per IPsec tunnel effective throughput ~1.25 Gbps (single flow)
- 2 tunnels: basic HA (Active/Active on 1 AWS S2S VPN connection)
- >2 tunnels: AWS Transit Gateway ECMP required — adds TGW attachment ($0.05/hr) + data processing ($0.02/GB)
- Presets: 2 / 4 / 8 / 16 tunnels (→ ~2.5 / 5 / 10 / 20 Gbps aggregate)

## Pricing sources (as of 2026-08)

- [AWS Direct Connect pricing](https://aws.amazon.com/directconnect/pricing/)
- [AWS Site-to-Site VPN pricing](https://aws.amazon.com/vpn/pricing/)
- [AWS Transit Gateway pricing](https://aws.amazon.com/transit-gateway/pricing/)
- [AWS EC2 Data Transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [GCP Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/docs/interconnect/pricing)
- [GCP Cross-Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview)
- [GCP VPC network pricing](https://cloud.google.com/vpc/network-pricing)

Prices are cross-checked against the AWS Pricing API and GCP Cloud Billing Catalog API. See [`pricing.json`](./pricing.json).

## Assumptions

- **List price only** — no EDP/PPA (AWS), no CUD (GCP), no promotional credits, no CCI fixed pricing.
- Both Option A and Option B use AWS DX **Dedicated** port ($2.25/hr at 10G, $22.50/hr at 100G).
- Option A does **not** include customer router hardware, colo rack/power/cooling, remote hands, or operational labor.
- Effective bandwidth: Interconnect = nominal × 85%; VPN = tunnels × 1.25 Gbps.
- AWS DTO applies for AWS→GCP direction regardless of port ownership (CCI or DI+DX).

## Stack

- Python 3.12 + FastAPI + Jinja2 + HTMX
- Deployed on Google Cloud Run (`asia-northeast3`)

## Local development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Visit http://localhost:8080/

## Deploy to Cloud Run

```bash
gcloud run deploy interconnect-calc-v2 \
  --source . \
  --region=asia-northeast3 \
  --allow-unauthenticated \
  --port=8080
```

## License

MIT
