# Interconnect Architecture & Cost Guide: AWS Seoul ↔ GCP Seoul

This guide provides a comprehensive comparison of private and hybrid cloud network connectivity options between **AWS Seoul (`ap-northeast-2`)** and **GCP Seoul (`asia-northeast3`)**.

---

## 1. Overview & Architecture Options

When architecting hybrid or multi-cloud connectivity between AWS and GCP in Seoul, organizations typically evaluate three primary interconnect patterns:

```
+-----------------------------------------------------------------------------------+
|                                 Connectivity Options                              |
+-----------------------------------------------------------------------------------+
|  Option A: Dedicated Interconnect + Direct Connect (Colocation Hub)               |
|  AWS ap-northeast-2 <---> [Colo: KINX / LGU+ / Sejong IX] <---> GCP asia-northeast3 |
|                                                                                   |
|  Option B: Cross-Cloud Interconnect (CCI)                                         |
|  AWS ap-northeast-2 <================[Google-Managed Link]===============> GCP     |
|                                                                                   |
|  Option C: HA VPN with Transit Gateway (TGW) ECMP                                 |
|  AWS VPC / TGW <--------------[Public Internet / IPsec]-------------> GCP Cloud Router |
+-----------------------------------------------------------------------------------+
```

---

## 2. Detailed Option Comparison

### Option A: AWS Direct Connect + GCP Dedicated Interconnect

* **Architecture:** The enterprise leases colocation space in a certified Seoul carrier-neutral facility (e.g., KINX Gasan, LG U+ Pyeongchon, or Sejong IX). Physical enterprise edge routers (e.g., Cisco, Juniper, Arista) are installed in the rack. Two cross-connect fibers are patched to AWS Direct Connect (DX) Meet-Me-Rooms (MMR), and two cross-connects are patched to GCP Dedicated Interconnect (DI) MMRs.
* **Bandwidth:** 10 Gbps or 100 Gbps per link (up to 16 links in a Link Aggregation Group).
* **Latency:** Sub-millisecond (< 1.5 ms RTT between VPCs).
* **SLA:** 99.99% with dual-location / dual-link architecture.
* **Cost Components:**
  * AWS Direct Connect Dedicated Port: $2.25/hr (10G) or $22.50/hr (100G) per link.
  * GCP Dedicated Interconnect Port: $2.328/hr (10G) or $23.28/hr (100G) per link.
  * GCP VLAN Attachment: $0.10/hr (≤10G) or $1.00/hr (100G) per link.
  * Colocation Facility Cross-Connects: ~$200 – $600/month per physical fiber drop.
  * AWS DTO (Seoul Direct Connect egress): $0.041 per decimal GB.
  * GCP Interconnect Egress (Asia to Asia): $0.042 per binary GiB.
* **Pros:** Complete control over routing hardware, custom BGP policies, hardware encryption (MACsec), maximum sustained wire-speed throughput.
* **Cons:** High CapEx and OpEx (router hardware lifecycle, rack power/cooling, remote hands, long provisioning lead time of 4–12 weeks).

---

### Option B: Cross-Cloud Interconnect (CCI)

* **Architecture:** Google provisions and manages high-capacity direct physical links into AWS Direct Connect facility locations in Seoul. Google acts as the connectivity partner, eliminating the need for customer-owned physical colocation space or edge routing equipment.
* **Bandwidth:** 10 Gbps or 100 Gbps per link.
* **Latency:** Sub-millisecond direct interconnect latency (~1.5–2.0 ms RTT).
* **SLA:** 99.99% SLA with 4 links across 2 metros / edge locations; 99.9% with 2 links.
* **Cost Components:**
  * AWS Direct Connect Dedicated Port: $2.25/hr (10G) or $22.50/hr (100G) per link.
  * GCP Cross-Cloud Interconnect Port: $5.60/hr (10G) or $30.00/hr (100G) per link.
  * GCP VLAN Attachment: $0.10/hr (≤10G) or $1.00/hr (100G) per link.
  * Egress Fees: AWS DTO $0.041/GB, GCP Interconnect Egress $0.042/GiB.
  * Colocation Fee: **$0** (No customer colo or router hardware required).
* **Pros:** Zero hardware/colo footprint, fast provisioning (days instead of months), managed physical transport SLA, seamless integration with Cloud Router.
* **Cons:** Higher GCP hourly port charge compared to Dedicated Interconnect ($5.60/hr vs $2.328/hr at 10G).

---

### Option C: High Availability (HA) VPN with AWS Transit Gateway ECMP

* **Architecture:** Dual IPsec VPN tunnels established over the public internet between GCP HA VPN gateways and AWS Site-to-Site VPN or AWS Transit Gateway (TGW). When scaling beyond 2 tunnels (e.g., 4, 8, 16 tunnels), Equal-Cost Multi-Path (ECMP) routing is enabled on AWS Transit Gateway to aggregate tunnel bandwidth.
* **Bandwidth:** ~1.25 Gbps per tunnel (single TCP/UDP flow). Scalable up to ~20 Gbps aggregate throughput with 16 tunnels and multiple parallel flows.
* **Latency:** Dependent on public internet routing (~3–8 ms RTT in Seoul).
* **SLA:** 99.99% service availability for GCP HA VPN and AWS Site-to-Site VPN.
* **Cost Components:**
  * GCP HA VPN Tunnel: $0.075/hr per tunnel.
  * AWS Site-to-Site VPN Connection: $0.05/hr per connection (2 tunnels per connection).
  * AWS Transit Gateway Attachment (>2 tunnels): $0.05/hr per connection.
  * AWS Transit Gateway Data Processing (>2 tunnels): $0.02 per decimal GB.
  * Internet Egress Fees (Tiered):
    * AWS Internet Egress (Seoul): $0.126/GB (first 10 TB), $0.122/GB (next 40 TB), $0.117/GB (next 100 TB), $0.108/GB (>150 TB).
    * GCP Internet Egress (Seoul to Korea): $0.19/GiB (first 1 TiB), $0.18/GiB (next 9 TiB), $0.15/GiB (>10 TiB).
* **Pros:** Instant provisioning via Infrastructure as Code (Terraform), lowest fixed infrastructure monthly cost, ideal for lightweight replication, dev/staging environments, or backup circuits.
* **Cons:** High variable data transfer egress fees over public internet; performance subject to public internet jitter and single-flow throttling.

---

## 3. Comparison Matrix

| Metric / Dimension | Option A: Dedicated Interconnect | Option B: Cross-Cloud Interconnect | Option C: HA VPN (TGW ECMP) |
|---|---|---|---|
| **Physical Hardware** | Customer edge routers required | Fully managed by Google & AWS | Cloud-native virtual gateways |
| **Colocation Facility** | Required (KINX, LG U+, Sejong) | None required | None required |
| **Port Speeds** | 10 Gbps / 100 Gbps | 10 Gbps / 100 Gbps | 1.25 Gbps per tunnel (~20 Gbps max) |
| **Typical Latency** | < 1.5 ms RTT | < 2.0 ms RTT | 3.0 – 8.0 ms RTT |
| **Fixed Cost (2×10G / 2-tun)** | ~$3,415/mo + Colo ($400-$1,200) | ~$5,803/mo | ~$182.50/mo |
| **AWS Egress Rate** | $0.041 / GB | $0.041 / GB | $0.108 – $0.126 / GB (+ $0.02 TGW) |
| **GCP Egress Rate** | $0.042 / GiB | $0.042 / GiB | $0.150 – $0.190 / GiB |
| **Provisioning Lead Time** | 4 – 12 weeks | 1 – 5 days | Minutes |
| **Crossover Point** | Best for high volume + existing colo | Best for high volume without colo | Best for < 15–25 TB/month |

---

## 4. Billing Mechanics: Decimal GB vs Binary GiB

Cloud providers employ differing unit standards for network metering and billing:

1. **AWS Data Transfer Out (DTO):**
   * Measured in **decimal Gigabytes (GB)**: $1\text{ GB} = 10^9\text{ bytes} = 1,000,000,000\text{ bytes}$.
   * $1\text{ TB} = 1,000\text{ GB} = 10^{12}\text{ bytes}$.
2. **GCP Cloud Interconnect & Internet Egress:**
   * Measured in **binary Gibibytes (GiB)**: $1\text{ GiB} = 2^{30}\text{ bytes} = 1,073,741,824\text{ bytes}$.
   * $1\text{ TiB} = 1,024\text{ GiB} = 2^{40}\text{ bytes} = 1,099,511,627,776\text{ bytes}$.

### Impact on Cost Calculations
When migrating 100 TB ($10^{14}$ bytes) from GCP to AWS:
* In GCP billing: $10^{14} \div 2^{30} \approx 93,132.26\text{ GiB} \times \$0.042/\text{GiB} = \$3,911.55$.
* A naive calculation assuming 100,000 GiB would over-estimate cost by ~$288.
* Our calculator automatically converts all input volumes to raw bytes first, ensuring 100% precision.

---

## 5. Bidirectional Transfer Time Formula

Transfer duration estimates use effective bandwidth accounting for protocol overhead, framing, and TCP window scaling:

$$\text{Effective Bandwidth (Interconnect)} = \text{Nominal Port Speed} \times \text{Link Count} \times 0.85$$

$$\text{Effective Bandwidth (HA VPN)} = \text{Tunnel Count} \times 1.25\text{ Gbps}$$

$$\text{Transfer Duration (Hours)} = \frac{\text{Data Volume (Bytes)} \times 8}{\text{Effective Bandwidth (bps)} \times 3600}$$

---

## 6. Single Point of Failure (SPOF) & SLA Best Practices

* **Production SLA Requirement:** Both AWS Direct Connect and GCP Cloud Interconnect require a minimum of **2 distinct links** for a 99.9% SLA, and **4 links across 2 independent facilities** for a 99.99% enterprise SLA.
* **SPOF Risk:** A single link configuration leaves your cross-cloud architecture vulnerable to router maintenance, optic failure, or fiber cuts. The calculator flags any 1-link scenario with a high-priority warning.
