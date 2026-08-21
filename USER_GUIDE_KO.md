# Interconnect 아키텍처 및 비용 분석 가이드: AWS Seoul ↔ GCP Seoul

본 가이드는 **AWS Seoul (`ap-northeast-2`)**과 **GCP Seoul (`asia-northeast3`)** 간의 프라이빗 및 하이브리드 클라우드 네트워크 연결 옵션에 대한 종합적인 비교 및 실무 설계 지침을 제공합니다.

---

## 1. 개요 및 연결 토폴로지 (Overview & Architecture)

AWS 서울 리전과 GCP 서울 리전 간 엔터프라이즈 하이브리드/멀티클라우드 네트워크를 설계할 때 일반적으로 검토하는 **3가지 핵심 연결 패턴**은 다음과 같습니다:

```
+-----------------------------------------------------------------------------------+
|                                 연결 옵션 비교 구조도                              |
+-----------------------------------------------------------------------------------+
|  Option A: Dedicated Interconnect + Direct Connect (Colocation Hub)               |
|  AWS ap-northeast-2 <---> [Colo: KINX / LGU+ / Sejong IX] <---> GCP asia-northeast3 |
|                                                                                   |
|  Option B: Cross-Cloud Interconnect (CCI)                                         |
|  AWS ap-northeast-2 <================[Google 관리형 전용선]==============> GCP      |
|                                                                                   |
|  Option C: HA VPN with AWS Transit Gateway (TGW) ECMP                             |
|  AWS VPC / TGW <--------------[Public Internet / IPsec]-------------> GCP Cloud Router |
+-----------------------------------------------------------------------------------+
```

---

## 2. 옵션별 상세 아키텍처 및 비용 구조

### Option A: AWS Direct Connect + GCP Dedicated Interconnect

* **아키텍처 개요:** 기업이 서울 내 공인 중립 코로케이션 센터(예: KINX 가산, LG U+ 평촌, Sejong IX 등)에 랙(Rack)과 전용 라우터(Cisco, Juniper, Arista 등)를 직접 배치합니다. 라우터에서 AWS Direct Connect (DX) Meet-Me-Room (MMR)으로 광케이블 2회선을 연결하고, GCP Dedicated Interconnect (DI) MMR로 광케이블 2회선을 교차 연결(Cross-Connect)합니다.
* **대역폭 (Bandwidth):** 회선당 10 Gbps 또는 100 Gbps (Link Aggregation Group 구성 가능).
* **지연시간 (Latency):** 1.5 ms 미만의 초저지연 (Sub-millisecond RTT).
* **가용성 SLA:** 이중화 센터 / 이중 회선 구성 시 99.99% SLA 보장.
* **비용 구성 요소:**
  * AWS Direct Connect Dedicated Port: 회선당 $2.25/시간 (10G) 또는 $22.50/시간 (100G).
  * GCP Dedicated Interconnect Port: 회선당 $2.328/시간 (10G) 또는 $23.28/시간 (100G).
  * GCP VLAN Attachment: 회선당 $0.10/시간 (≤10G) 또는 $1.00/시간 (100G).
  * Colocation Facility Cross-Connect 요금: 물리적 광케이블 인입당 약 $200 ~ $600/월.
  * AWS DTO (Seoul Direct Connect egress): $0.041 per decimal GB.
  * GCP Interconnect Egress (Asia to Asia): $0.042 per binary GiB.
* **장점:** 자체 라우터를 통한 커스텀 BGP 정책, 하드웨어 암호화(MACsec), 최대 대역폭 제어 가능.
* **단점:** 초기 하드웨어 투자비(CapEx) 및 상주 운영비(OpEx) 발생, 회선 개통에 4~12주의 긴 리드타임 소요.

---

### Option B: Cross-Cloud Interconnect (CCI)

* **아키텍처 개요:** Google이 서울 내 AWS Direct Connect 시설로 직접 인입되는 고용량 관리형 물리 회선을 사전 구축하여 제공합니다. 고객이 별도의 코로케이션 랙이나 물리 라우터를 보유할 필요가 전혀 없습니다.
* **대역폭 (Bandwidth):** 회선당 10 Gbps 또는 100 Gbps.
* **지연시간 (Latency):** 직접 물리 연결 기반 초저지연 (~1.5–2.0 ms RTT).
* **가용성 SLA:** 2개 엣지 위치 분산 4개 회선 구성 시 99.99% SLA, 단일 위치 2개 회선 시 99.9% SLA.
* **비용 구성 요소:**
  * AWS Direct Connect Dedicated Port: 회선당 $2.25/시간 (10G) 또는 $22.50/시간 (100G).
  * GCP Cross-Cloud Interconnect Port: 회선당 $5.60/시간 (10G) 또는 $30.00/시간 (100G).
  * GCP VLAN Attachment: 회선당 $0.10/시간 (≤10G) 또는 $1.00/시간 (100G).
  * Egress 요금: AWS DTO $0.041/GB, GCP Interconnect Egress $0.042/GiB.
  * 코로케이션 / 라우터 비용: **$0 (완전 불필요)**.
* **장점:** 제로 하드웨어/코로케이션, 수일 내 빠른 개통, Google 관리형 전송망 SLA, Cloud Router와의 완벽한 소프트웨어 정의 통합.
* **단점:** Dedicated Interconnect 대비 GCP 시간당 포트 단가가 높음 ($5.60/hr vs $2.328/hr at 10G).

---

### Option C: High Availability (HA) VPN with AWS Transit Gateway ECMP

* **아키텍처 개요:** GCP HA VPN 게이트웨이와 AWS Site-to-Site VPN (또는 AWS Transit Gateway) 간에 공용 인터넷을 통해 이중 IPsec 터널을 생성합니다. 2개 터널을 초과하는 대규모 트래픽(4, 8, 16개 터널) 구성 시 AWS Transit Gateway에서 Equal-Cost Multi-Path (ECMP) 라우팅을 활성화하여 터널 대역폭을 결합합니다.
* **대역폭 (Bandwidth):** 터널당 약 1.25 Gbps (단일 플로우 기준). 16개 터널 병렬 플로우 시 최대 ~20 Gbps 결합 대역폭 지원.
* **지연시간 (Latency):** 공용 인터넷 라우팅 경로에 따라 변동 (~3–8 ms RTT).
* **가용성 SLA:** GCP HA VPN 및 AWS Site-to-Site VPN 각각 99.99% 서비스 가용성 제공.
* **비용 구성 요소:**
  * GCP HA VPN Tunnel: 터널당 $0.075/시간.
  * AWS Site-to-Site VPN Connection: 연결당 $0.05/시간 (연결당 2개 터널 포함).
  * AWS Transit Gateway Attachment (>2 터널 시): 연결당 $0.05/시간.
  * AWS Transit Gateway Data Processing (>2 터널 시): $0.02 per decimal GB.
  * 인터넷 Egress 종량 요금 (Tiered):
    * AWS Internet Egress (Seoul): $0.126/GB (초기 10 TB), $0.122/GB (다음 40 TB), $0.117/GB (다음 100 TB), $0.108/GB (150 TB 초과).
    * GCP Internet Egress (Seoul to Korea): $0.19/GiB (초기 1 TiB), $0.18/GiB (다음 9 TiB), $0.15/GiB (10 TiB 초과).
* **장점:** Terraform 등 IaC를 통한 즉각적인 프로비저닝(수 분 내), 최소 고정 인프라 비용, 개발/스테이징 환경이나 백업 회선으로 최적.
* **단점:** 대규모 트래픽 시 공용 인터넷 Egress 요금 부담 증가, 인터넷 경로 품질에 따른 지연 변동성(Jitter) 발생 가능.

---

## 3. 핵심 아키텍처 비교표

| 비교 항목 | Option A: Dedicated Interconnect | Option B: Cross-Cloud Interconnect | Option C: HA VPN (TGW ECMP) |
|---|---|---|---|
| **물리 하드웨어** | 고객 엔터프라이즈 라우터 필수 | Google & AWS 완전 관리형 | 클라우드 가상 게이트웨이 |
| **코로케이션 시설** | 필수 (KINX, LG U+, Sejong) | 불필요 | 불필요 |
| **포트 대역폭** | 10 Gbps / 100 Gbps | 10 Gbps / 100 Gbps | 터널당 1.25 Gbps (최대 ~20 Gbps) |
| **일반적 RTT 지연** | < 1.5 ms RTT | < 2.0 ms RTT | 3.0 – 8.0 ms RTT |
| **월 고정 인프라비 (2×10G / 2-tun)** | ~$3,415/월 + Colo ($400-$1,200) | ~$5,803/월 | ~$182.50/월 |
| **AWS Egress 요율** | $0.041 / GB | $0.041 / GB | $0.108 – $0.126 / GB (+ $0.02 TGW) |
| **GCP Egress 요율** | $0.042 / GiB | $0.042 / GiB | $0.150 – $0.190 / GiB |
| **구축 소요 기간** | 4 – 12주 | 1 – 5영업일 | 수 분 (즉시 개통) |
| **손익분기점 추천** | 대규모 트래픽 + 기존 코로케이션 보유 시 | 대규모 트래픽 + 코로케이션 미보유 시 | 월 트래픽 소용량 또는 백업용 |

---

## 4. 과금 단위 계산법: 10진수 GB vs 2진수 GiB

AWS와 GCP는 데이터 전송량 과금 단위의 정의가 다릅니다:

* **AWS (10진수 Decimal 기준):** $1\text{ TB} = 10^{12}\text{ Bytes} = 1,000\text{ GB}$.
* **GCP (2진수 Binary 기준):** $1\text{ TiB} = 2^{40}\text{ Bytes} = 1,024\text{ GiB} = 1,099,511,627,776\text{ Bytes}$.

본 계산기는 AWS Egress에는 10진수 $10^9$ 바이트(GB) 기준 요율을 적용하고, GCP Egress에는 2진수 $2^{30}$ 바이트(GiB) 기준 요율을 정밀하게 적용하여 실제 청구서와 오차 없는 시뮬레이션을 제공합니다.

---

## 5. 고가용성(HA) 및 단일 장애점(SPOF) 방지 가이드

프로덕션 환경에서는 단일 장애점(SPOF)을 제거하기 위해 다음 원칙을 반드시 준수해야 합니다:

1. **최소 2회선 이중화 (Active/Active):** 1개 링크만 구성할 경우 정기 유지보수, 광케이블 손상, 포트 장애 시 크로스클라우드 트래픽이 100% 중단됩니다.
2. **SLA 요건:**
   * **99.9% 가용성:** 단일 코로케이션/엣지 내 최소 2개 독립 포트/회선 구성.
   * **99.99% 가용성:** 서울 내 2개 이상의 독립된 엣지 위치(예: KINX 가산 + LG U+ 평촌)에 걸쳐 총 4개 이상의 링크 분산 구성.
3. **BGP 동적 라우팅 및 MED/AS-Path 설정:** 두 클라우드 간 최적 경로 학습 및 장애 시 무중단 자동 페일오버(Failover) 보장.
