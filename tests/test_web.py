import pytest
from fastapi.testclient import TestClient

from pitchvalue.api.app import create_app
from pitchvalue.config import Settings


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    return TestClient(app)


def test_privacy_page_accessible(client: TestClient) -> None:
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text
    assert "PitchValue" in content
    assert "Privacy Policy" in content
    assert "4. HESAP SİLME" in content
    assert "push tokenlarını siler" in content
    assert "silinen hesaptan ayrıştırılabilir veya takma adlandırılabilir" in content
    assert "App Store veya Google Play aboneliğini iptal etmez" in content


def test_terms_page_accessible(client: TestClient) -> None:
    response = client.get("/terms")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text
    assert "PitchValue" in content
    assert "Terms of Service" in content
    assert "bilgi ve karar destek hizmetidir" in content
    assert "bir bahis operatörü, bahis sitesi, casino veya finansal aracı değildir" in content
    assert "kesin kazanç veya garantili sonuç vaat etmez" in content
    assert "ABONELİKLER VE ÖDEMELER" in content
