from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_get_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Interconnect Cost Calculator" in response.text
    assert "Architecture Guide" in response.text
    assert "Data volume unit" in response.text


def test_get_index_korean():
    response = client.get("/?lang=ko")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Interconnect 비용 계산기" in response.text
    assert "Architecture 가이드" in response.text
    assert "데이터 전송량 단위" in response.text


def test_get_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_get_guide():
    response = client.get("/guide")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Architecture &amp; User Guide" in response.text or "Architecture & User Guide" in response.text
    assert "Option A" in response.text
    assert "Option B" in response.text
    assert "Option C" in response.text
    assert "Back to Calculator" in response.text


def test_get_guide_korean():
    response = client.get("/guide?lang=ko")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "계산기로 돌아가기" in response.text


def test_get_guide_md():
    response = client.get("/guide.md")
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "# Interconnect Architecture & Cost Guide" in response.text
    assert "Cross-Cloud Interconnect" in response.text


def test_post_calculate_usd():
    payload = {
        "amount_a2g": "50",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "2",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "en",
    }
    response = client.post("/calculate", data=payload)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Option A" in response.text
    assert "Option B" in response.text
    assert "Option C" in response.text
    assert "CHEAPEST" in response.text or "Cheapest option" in response.text
    assert "Visual Cost Composition Breakdown" in response.text
    assert "Link Capacity Utilization" in response.text
    assert "$" in response.text


def test_post_calculate_korean():
    payload = {
        "amount_a2g": "50",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "2",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "ko",
    }
    response = client.post("/calculate", data=payload)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "최저가" in response.text
    assert "비용 구성 시각화" in response.text
    assert "고정 인프라" in response.text
    assert "Link 대역폭 사용률" in response.text
    # Technical terms preserved
    assert "AWS DX" in response.text
    assert "Cross-Cloud Interconnect" in response.text
    assert "HA VPN" in response.text
    assert "$" in response.text


def test_post_calculate_spof_warning():
    payload = {
        "amount_a2g": "10",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "1",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "en",
    }
    response = client.post("/calculate", data=payload)
    assert response.status_code == 200
    assert "Single point of failure (SPOF)" in response.text


def test_post_calculate_spof_warning_korean():
    payload = {
        "amount_a2g": "10",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "1",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "ko",
    }
    response = client.post("/calculate", data=payload)
    assert response.status_code == 200
    assert "단일 장애점 (SPOF) 경고" in response.text


def test_post_export_csv():
    payload = {
        "amount_a2g": "50",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "2",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "en",
    }
    response = client.post("/export/csv", data=payload)
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    csv_text = response.text
    assert "Interconnect Cost Calculator" in csv_text
    assert "Option A" in csv_text
    assert "Transfer time: AWS → GCP" in csv_text or "Transfer time AWS -> GCP" in csv_text


def test_post_export_csv_korean():
    payload = {
        "amount_a2g": "50",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "2",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "ko",
    }
    response = client.post("/export/csv", data=payload)
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    csv_text = response.text
    assert "Interconnect 비용 계산기" in csv_text
    assert "전송 소요 시간: AWS → GCP" in csv_text


def test_post_export_md():
    payload = {
        "amount_a2g": "50",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "2",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "en",
    }
    response = client.post("/export/md", data=payload)
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    md_text = response.text
    assert "# Interconnect Cost Calculator — Result" in md_text
    assert "Cost breakdown" in md_text
    assert "Transfer time: AWS → GCP" in md_text or "Transfer time (AWS → GCP)" in md_text


def test_post_export_md_korean():
    payload = {
        "amount_a2g": "50",
        "amount_g2a": "10",
        "unit": "TB",
        "port_gbps": "10",
        "link_count": "2",
        "colo_per_link_monthly": "0",
        "vpn_tunnels": "2",
        "lang": "ko",
    }
    response = client.post("/export/md", data=payload)
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    md_text = response.text
    assert "# Interconnect 비용 계산기 — Result" in md_text
    assert "전송 소요 시간: AWS → GCP" in md_text
