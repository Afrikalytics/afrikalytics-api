"""
Tests for the analytics router — /api/studies/{id}/analyze and /api/studies/{id}/anomalies.
Also unit tests for analytics_service and anomaly_detection services.
"""
import pytest

from app.models import Study, StudyDataset
from app.services.analytics_service import (
    AnalysisResult,
    analyze_dataset,
    _compute_correlation,
    _compute_stats,
    _detect_numeric_columns,
    _detect_trend,
    _extract_numeric_values,
    _guess_unit,
)
from app.services.anomaly_detection import detect_anomalies


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_DATA = [
    {"region": "Dakar", "revenue": 50000, "clients": 120},
    {"region": "Abidjan", "revenue": 45000, "clients": 95},
    {"region": "Bamako", "revenue": 38000, "clients": 80},
    {"region": "Conakry", "revenue": 42000, "clients": 110},
    {"region": "Lome", "revenue": 35000, "clients": 70},
    {"region": "Ouaga", "revenue": 40000, "clients": 90},
    {"region": "Niamey", "revenue": 37000, "clients": 75},
    {"region": "Cotonou", "revenue": 43000, "clients": 100},
    {"region": "Nouakchott", "revenue": 30000, "clients": 60},
    {"region": "Libreville", "revenue": 55000, "clients": 130},
]

SAMPLE_COLUMNS = ["region", "revenue", "clients"]

# Data with an extreme outlier for anomaly detection
ANOMALY_DATA = SAMPLE_DATA + [
    {"region": "Outlier", "revenue": 500000, "clients": 5},  # extreme outlier
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def study_with_data(db):
    """Create a study with an attached dataset."""
    study = Study(
        title="Etude Analyse Test",
        description="Test study for analytics.",
        category="Consommation",
        status="Ouvert",
        is_active=True,
    )
    db.add(study)
    db.flush()

    dataset = StudyDataset(
        study_id=study.id,
        data=SAMPLE_DATA,
        columns=SAMPLE_COLUMNS,
        row_count=len(SAMPLE_DATA),
    )
    db.add(dataset)
    db.commit()
    db.refresh(study)
    return study


@pytest.fixture()
def study_without_data(db):
    """Create a study with no dataset."""
    study = Study(
        title="Etude Sans Donnees",
        description="No data imported.",
        category="Finance",
        status="Ouvert",
        is_active=True,
    )
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


@pytest.fixture()
def study_with_anomaly_data(db):
    """Create a study with data containing outliers."""
    study = Study(
        title="Etude Anomalies Test",
        description="Contains outliers.",
        category="Finance",
        status="Ouvert",
        is_active=True,
    )
    db.add(study)
    db.flush()

    dataset = StudyDataset(
        study_id=study.id,
        data=ANOMALY_DATA,
        columns=SAMPLE_COLUMNS,
        row_count=len(ANOMALY_DATA),
    )
    db.add(dataset)
    db.commit()
    db.refresh(study)
    return study


# ---------------------------------------------------------------------------
# POST /api/studies/{id}/analyze — Endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeEndpoint:
    def test_analyze_success(self, client, auth_headers, study_with_data):
        resp = client.post(
            f"/api/studies/{study_with_data.id}/analyze",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "trends" in data
        assert "insights" in data
        assert "kpis" in data

    def test_analyze_no_data(self, client, auth_headers, study_without_data):
        resp = client.post(
            f"/api/studies/{study_without_data.id}/analyze",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "donnees" in resp.json()["detail"].lower() or "données" in resp.json()["detail"].lower()

    def test_analyze_study_not_found(self, client, auth_headers):
        resp = client.post("/api/studies/99999/analyze", headers=auth_headers)
        assert resp.status_code == 404

    def test_analyze_unauthorized(self, client, study_with_data):
        resp = client.post(f"/api/studies/{study_with_data.id}/analyze")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/studies/{id}/anomalies — Endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnomaliesEndpoint:
    def test_anomalies_success(self, client, auth_headers, study_with_anomaly_data):
        resp = client.get(
            f"/api/studies/{study_with_anomaly_data.id}/anomalies",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data
        assert "summary" in data
        assert data["summary"]["total_anomalies"] > 0

    def test_anomalies_no_data(self, client, auth_headers, study_without_data):
        resp = client.get(
            f"/api/studies/{study_without_data.id}/anomalies",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_anomalies_study_not_found(self, client, auth_headers):
        resp = client.get("/api/studies/99999/anomalies", headers=auth_headers)
        assert resp.status_code == 404

    def test_anomalies_unauthorized(self, client, study_with_anomaly_data):
        resp = client.get(f"/api/studies/{study_with_anomaly_data.id}/anomalies")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unit tests — analytics_service
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyticsService:
    def test_detect_numeric_columns(self):
        result = _detect_numeric_columns(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert "revenue" in result
        assert "clients" in result
        assert "region" not in result

    def test_extract_numeric_values(self):
        values = _extract_numeric_values(SAMPLE_DATA, "revenue")
        assert len(values) == 10
        assert 50000.0 in values

    def test_compute_stats(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = _compute_stats(values)
        assert stats["count"] == 5
        assert stats["mean"] == 30.0
        assert stats["median"] == 30.0
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["sum"] == 150.0

    def test_detect_trend_upward(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        trend = _detect_trend(values)
        assert trend is not None
        assert trend["direction"] == "hausse"

    def test_detect_trend_downward(self):
        values = [50.0, 40.0, 30.0, 20.0, 10.0]
        trend = _detect_trend(values)
        assert trend is not None
        assert trend["direction"] == "baisse"

    def test_detect_trend_flat(self):
        values = [10.0, 10.0, 10.0, 10.0, 10.0]
        trend = _detect_trend(values)
        assert trend is None  # No trend for flat data

    def test_compute_correlation_positive(self):
        data = [{"a": i, "b": i * 2} for i in range(10)]
        corr = _compute_correlation(data, "a", "b")
        assert corr is not None
        assert corr > 0.9  # Perfect positive correlation

    def test_compute_correlation_insufficient_data(self):
        data = [{"a": 1, "b": 2}]
        corr = _compute_correlation(data, "a", "b")
        assert corr is None

    def test_guess_unit(self):
        assert _guess_unit("prix_total") == "FCFA"
        assert _guess_unit("revenue") == "FCFA"
        assert _guess_unit("taux_croissance") == "%"
        assert _guess_unit("poids") == "kg"
        assert _guess_unit("nom") == ""

    def test_analyze_dataset_full(self):
        result = analyze_dataset(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert isinstance(result, AnalysisResult)
        assert result.summary["total_rows"] == 10
        assert result.summary["total_columns"] == 3
        assert len(result.insights) > 0
        assert len(result.kpis) > 0

    def test_analyze_dataset_empty(self):
        result = analyze_dataset([], [])
        assert "Aucune" in result.insights[0]


# ---------------------------------------------------------------------------
# Unit tests — anomaly_detection
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnomalyDetection:
    def test_detect_anomalies_with_outlier(self):
        result = detect_anomalies(ANOMALY_DATA, SAMPLE_COLUMNS)
        assert result.summary["total_anomalies"] > 0
        # The 500000 revenue should be flagged
        revenue_anomalies = [a for a in result.anomalies if a.column == "revenue"]
        assert len(revenue_anomalies) > 0
        assert any(a.value == 500000.0 for a in revenue_anomalies)

    def test_detect_anomalies_no_anomalies(self):
        # Uniform data — no outliers
        uniform = [{"val": 10.0} for _ in range(20)]
        result = detect_anomalies(uniform, ["val"])
        assert result.summary["total_anomalies"] == 0

    def test_detect_anomalies_empty_data(self):
        result = detect_anomalies([], [])
        assert result.summary["total_anomalies"] == 0
        assert "Aucune" in result.summary["message"]

    def test_detect_anomalies_no_numeric(self):
        data = [{"name": "alpha"}, {"name": "beta"}]
        result = detect_anomalies(data, ["name"])
        assert result.summary["total_anomalies"] == 0
