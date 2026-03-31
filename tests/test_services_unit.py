"""
Pure unit tests for Afrikalytics API service layer and security module.

Coverage targets:
- app/security.py          — API key + newsletter token helpers, masking utilities
- app/services/payment_service.py  — Pure helper functions (no I/O, no DB)
- app/services/analytics_service.py — Statistical analysis helpers
- app/services/anomaly_detection.py — Outlier detection (Z-score + IQR)
- app/pagination.py        — PaginationParams skip/limit properties

No database, no HTTP clients, no external services required.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

import hashlib
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.security import (
    MASK_FIELDS,
    API_KEY_PREFIX_LEN,
    constant_time_compare,
    generate_api_key,
    generate_newsletter_token,
    hash_api_key,
    hash_newsletter_token,
    mask_secret,
    sanitize_log_dict,
    verify_api_key,
    verify_newsletter_token,
)
from app.services.analytics_service import (
    AnalysisResult,
    _compute_correlation,
    _compute_stats,
    _detect_numeric_columns,
    _detect_trend,
    _extract_numeric_values,
    _guess_unit,
    analyze_dataset,
)
from app.services.anomaly_detection import (
    AnomalyDetectionResult,
    detect_anomalies,
)
from app.services.payment_service import (
    PLAN_DURATIONS,
    PLAN_FEATURES,
    PLAN_PRICES,
    VALID_PLANS,
    get_paydunya_base_url,
    get_paydunya_headers,
    get_plan_duration,
    get_plan_price,
)
from app.pagination import PaginationParams


# ---------------------------------------------------------------------------
# Shared sample datasets
# ---------------------------------------------------------------------------

SAMPLE_DATA: list[dict] = [
    {"region": "Dakar", "revenu": 850000, "clients": 120},
    {"region": "Thies", "revenu": 420000, "clients": 65},
    {"region": "Saint-Louis", "revenu": 310000, "clients": 42},
    {"region": "Ziguinchor", "revenu": 275000, "clients": 38},
    {"region": "Tambacounda", "revenu": 190000, "clients": 27},
    {"region": "Kaolack", "revenu": 360000, "clients": 55},
    {"region": "Louga", "revenu": 215000, "clients": 31},
    {"region": "Matam", "revenu": 145000, "clients": 19},
    {"region": "Kedougou", "revenu": 120000, "clients": 14},
    {"region": "Sedhiou", "revenu": 165000, "clients": 22},
]
SAMPLE_COLUMNS: list[str] = ["region", "revenu", "clients"]

OUTLIER_DATA: list[dict] = [
    {"region": "Dakar", "revenu": 300000, "clients": 50},
    {"region": "Thies", "revenu": 310000, "clients": 52},
    {"region": "Saint-Louis", "revenu": 295000, "clients": 48},
    {"region": "Ziguinchor", "revenu": 305000, "clients": 51},
    {"region": "Tambacounda", "revenu": 290000, "clients": 47},
    {"region": "Kaolack", "revenu": 315000, "clients": 53},
    {"region": "Louga", "revenu": 308000, "clients": 50},
    {"region": "Matam", "revenu": 298000, "clients": 49},
    {"region": "Kedougou", "revenu": 302000, "clients": 51},
    {"region": "Sedhiou", "revenu": 9900000, "clients": 999},  # extreme outlier
]


# ===========================================================================
# TestSecurityModule
# ===========================================================================

@pytest.mark.unit
class TestSecurityModule:

    def test_generate_api_key_returns_three_tuple(self):
        result = generate_api_key()
        assert isinstance(result, tuple) and len(result) == 3

    def test_generate_api_key_starts_with_ak(self):
        full_key, _, _ = generate_api_key()
        assert full_key.startswith("ak_")

    def test_generate_api_key_hash_is_64_hex(self):
        _, key_hash, _ = generate_api_key()
        assert len(key_hash) == 64
        int(key_hash, 16)

    def test_generate_api_key_prefix_length(self):
        full_key, _, key_prefix = generate_api_key()
        assert len(key_prefix) == API_KEY_PREFIX_LEN
        assert full_key.startswith(key_prefix)

    def test_generate_api_key_unique(self):
        keys = {generate_api_key()[0] for _ in range(10)}
        assert len(keys) == 10

    def test_hash_api_key_matches_sha256(self):
        full_key, stored_hash, _ = generate_api_key()
        expected = hashlib.sha256(full_key.encode("utf-8")).hexdigest()
        assert hash_api_key(full_key) == expected == stored_hash

    def test_verify_api_key_correct(self):
        full_key, stored_hash, _ = generate_api_key()
        assert verify_api_key(full_key, stored_hash) is True

    def test_verify_api_key_wrong(self):
        _, stored_hash, _ = generate_api_key()
        assert verify_api_key("ak_wrongkey_totally_invalid", stored_hash) is False

    def test_generate_newsletter_token_format(self):
        raw, tok_hash, prefix = generate_newsletter_token()
        assert len(raw) >= 30
        assert len(tok_hash) == 64
        assert len(prefix) == 8

    def test_hash_newsletter_token_deterministic(self):
        raw, stored_hash, _ = generate_newsletter_token()
        assert hash_newsletter_token(raw) == stored_hash

    def test_verify_newsletter_token_correct(self):
        raw, stored_hash, _ = generate_newsletter_token()
        assert verify_newsletter_token(raw, stored_hash) is True

    def test_verify_newsletter_token_wrong(self):
        _, stored_hash, _ = generate_newsletter_token()
        assert verify_newsletter_token("tampered_value", stored_hash) is False

    def test_constant_time_compare_equal(self):
        assert constant_time_compare("hello", "hello") is True

    def test_constant_time_compare_different(self):
        assert constant_time_compare("hello", "world") is False

    def test_constant_time_compare_empty(self):
        assert constant_time_compare("", "") is True

    def test_mask_secret_standard(self):
        assert mask_secret("ak_secrettoken123") == "ak_s...****"

    def test_mask_secret_empty(self):
        assert mask_secret("") == "****"

    def test_mask_secret_short(self):
        assert mask_secret("abc", visible_chars=4) == "****"
        assert mask_secret("abcd", visible_chars=4) == "****"

    def test_mask_secret_custom_visible(self):
        assert mask_secret("supersecret", visible_chars=6) == "supers...****"

    def test_sanitize_log_dict_masks_password(self):
        data = {"email": "user@example.com", "password": "s3cr3t!"}
        result = sanitize_log_dict(data)
        assert result["email"] == "user@example.com"
        assert "****" in result["password"]
        assert "s3cr3t" not in result["password"]

    def test_sanitize_log_dict_no_mutation(self):
        data = {"password": "original"}
        sanitize_log_dict(data)
        assert data["password"] == "original"

    def test_sanitize_log_dict_non_sensitive_unchanged(self):
        data = {"email": "a@b.com", "name": "Fatou", "plan": "basic"}
        result = sanitize_log_dict(data)
        assert result == data

    def test_sanitize_log_dict_all_sensitive_fields(self):
        sensitive = {field: "secret_value_123" for field in MASK_FIELDS}
        result = sanitize_log_dict(sensitive)
        for field in MASK_FIELDS:
            assert "****" in result[field], f"Field '{field}' was not masked"

    def test_sanitize_log_dict_none_value(self):
        assert sanitize_log_dict({"password": None})["password"] == "****"


# ===========================================================================
# TestPaymentService
# ===========================================================================

def _mock_settings(paydunya_mode="test", master_key="mk", private_key="pk", token="tok"):
    mock = MagicMock()
    mock.paydunya_mode = paydunya_mode
    mock.paydunya_master_key = master_key
    mock.paydunya_private_key = private_key
    mock.paydunya_token = token
    return mock


@pytest.mark.unit
class TestPaymentService:

    def test_valid_plans(self):
        assert VALID_PLANS == {"basic", "professionnel", "entreprise"}

    def test_plan_prices(self):
        assert PLAN_PRICES["professionnel"] == 295000
        assert PLAN_PRICES["entreprise"] == 500000

    def test_plan_durations_30_days(self):
        for plan in ("professionnel", "entreprise"):
            assert PLAN_DURATIONS[plan] == timedelta(days=30)

    def test_plan_features_basic(self):
        assert PLAN_FEATURES["basic"]["api_access"] is False
        assert PLAN_FEATURES["basic"]["price_monthly"] == 0

    def test_plan_features_pro(self):
        assert PLAN_FEATURES["professionnel"]["api_access"] is True
        assert PLAN_FEATURES["professionnel"]["max_studies"] == 20

    def test_plan_features_enterprise(self):
        assert PLAN_FEATURES["entreprise"]["max_studies"] == -1
        assert PLAN_FEATURES["entreprise"]["custom_branding"] is True

    def test_get_plan_price_known(self):
        assert get_plan_price("professionnel") == 295000
        assert get_plan_price("entreprise") == 500000

    def test_get_plan_price_unknown_fallback(self):
        assert get_plan_price("unknown") == 295000

    def test_get_plan_duration_known(self):
        assert get_plan_duration("professionnel") == timedelta(days=30)

    def test_get_plan_duration_unknown_fallback(self):
        assert get_plan_duration("ghost") == timedelta(days=30)

    def test_paydunya_base_url_test(self):
        with patch("app.services.payment_service.get_settings", return_value=_mock_settings("test")):
            assert "sandbox" in get_paydunya_base_url()

    def test_paydunya_base_url_live(self):
        with patch("app.services.payment_service.get_settings", return_value=_mock_settings("live")):
            url = get_paydunya_base_url()
            assert "sandbox" not in url
            assert "paydunya.com" in url

    def test_paydunya_headers(self):
        with patch("app.services.payment_service.get_settings", return_value=_mock_settings(
            master_key="mk_test", private_key="pk_test", token="tok_test"
        )):
            headers = get_paydunya_headers()
            assert headers["PAYDUNYA-MASTER-KEY"] == "mk_test"
            assert headers["PAYDUNYA-PRIVATE-KEY"] == "pk_test"
            assert headers["PAYDUNYA-TOKEN"] == "tok_test"


# ===========================================================================
# TestAnalyticsService
# ===========================================================================

@pytest.mark.unit
class TestAnalyticsService:

    def test_detect_numeric_columns(self):
        result = _detect_numeric_columns(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert "revenu" in result and "clients" in result
        assert "region" not in result

    def test_detect_numeric_columns_empty(self):
        assert _detect_numeric_columns([], SAMPLE_COLUMNS) == []

    def test_detect_numeric_comma_decimal(self):
        data = [{"m": "1,500"}, {"m": "2,300"}, {"m": "3,100"}]
        assert "m" in _detect_numeric_columns(data, ["m"])

    def test_extract_numeric_values(self):
        values = _extract_numeric_values(SAMPLE_DATA, "revenu")
        assert len(values) == 10
        assert all(isinstance(v, float) for v in values)

    def test_extract_numeric_skips_none(self):
        data = [{"v": 100}, {"v": None}, {"v": 200}]
        assert len(_extract_numeric_values(data, "v")) == 2

    def test_extract_numeric_missing_col(self):
        assert _extract_numeric_values(SAMPLE_DATA, "nonexistent") == []

    def test_compute_stats_basic(self):
        stats = _compute_stats([10.0, 20.0, 30.0, 40.0, 50.0])
        assert stats["count"] == 5
        assert stats["mean"] == pytest.approx(30.0)
        assert stats["median"] == pytest.approx(30.0)
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["sum"] == pytest.approx(150.0)
        assert stats["std_dev"] > 0

    def test_compute_stats_single_value(self):
        assert _compute_stats([42.0])["std_dev"] == 0

    def test_compute_stats_all_keys(self):
        stats = _compute_stats([1.0, 2.0, 3.0])
        for key in ("count", "mean", "median", "std_dev", "min", "max", "q1", "q3", "sum"):
            assert key in stats

    def test_compute_stats_q1_q3_ordering(self):
        stats = _compute_stats([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        assert stats["q1"] < stats["median"] < stats["q3"]

    def test_detect_trend_upward(self):
        trend = _detect_trend([100, 200, 300, 400, 500, 600, 700, 800])
        assert trend is not None and trend["direction"] == "hausse"

    def test_detect_trend_downward(self):
        trend = _detect_trend([800, 700, 600, 500, 400, 300, 200, 100])
        assert trend is not None and trend["direction"] == "baisse"

    def test_detect_trend_flat(self):
        assert _detect_trend([100, 100, 100, 100, 100]) is None

    def test_detect_trend_too_short(self):
        assert _detect_trend([1.0, 2.0]) is None

    def test_detect_trend_required_keys(self):
        trend = _detect_trend([10, 20, 30, 40, 50, 60])
        assert trend is not None
        for key in ("direction", "strength", "slope", "description_fr"):
            assert key in trend

    def test_compute_correlation_positive(self):
        corr = _compute_correlation(SAMPLE_DATA, "revenu", "clients")
        assert corr is not None and corr > 0.9

    def test_compute_correlation_insufficient(self):
        assert _compute_correlation(SAMPLE_DATA[:4], "revenu", "clients") is None

    def test_compute_correlation_negative(self):
        data = [{"x": float(i), "y": float(10 - i)} for i in range(1, 11)]
        corr = _compute_correlation(data, "x", "y")
        assert corr is not None and corr < -0.99

    def test_guess_unit_fcfa(self):
        assert _guess_unit("revenu_total") == "FCFA"
        assert _guess_unit("montant_paye") == "FCFA"

    def test_guess_unit_kg(self):
        assert _guess_unit("poids_colis") == "kg"

    def test_guess_unit_percent(self):
        assert _guess_unit("taux_croissance") == "%"

    def test_guess_unit_unknown(self):
        assert _guess_unit("nom") == ""

    def test_analyze_dataset_full(self):
        result = analyze_dataset(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert isinstance(result, AnalysisResult)
        assert result.summary["total_rows"] == 10
        assert len(result.insights) > 0
        assert len(result.kpis) > 0

    def test_analyze_dataset_numeric_columns_detected(self):
        result = analyze_dataset(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert "revenu" in result.summary.get("numeric_columns", [])

    def test_analyze_dataset_first_insight_is_summary(self):
        result = analyze_dataset(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert "lignes" in result.insights[0] and "colonnes" in result.insights[0]

    def test_analyze_dataset_empty(self):
        result = analyze_dataset([], [])
        assert any("Aucune" in ins for ins in result.insights)

    def test_analyze_dataset_correlations(self):
        result = analyze_dataset(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert len(result.correlations) > 0
        assert result.correlations[0]["direction"] == "positive"


# ===========================================================================
# TestAnomalyDetection
# ===========================================================================

@pytest.mark.unit
class TestAnomalyDetection:

    def test_returns_correct_type(self):
        result = detect_anomalies(SAMPLE_DATA, SAMPLE_COLUMNS)
        assert isinstance(result, AnomalyDetectionResult)

    def test_finds_extreme_outlier(self):
        result = detect_anomalies(OUTLIER_DATA, SAMPLE_COLUMNS)
        critical = [a for a in result.anomalies if a.severity == "critical"]
        assert len(critical) > 0
        assert any(a.value == pytest.approx(9900000.0) for a in critical if a.column == "revenu")

    def test_summary_required_keys(self):
        result = detect_anomalies(OUTLIER_DATA, SAMPLE_COLUMNS)
        for key in ("total_anomalies", "total_warnings", "total_critical", "columns_analyzed", "methods_used"):
            assert key in result.summary

    def test_empty_data(self):
        result = detect_anomalies([], [])
        assert result.summary["total_anomalies"] == 0
        assert "Aucune" in result.summary.get("message", "")

    def test_no_numeric_columns(self):
        data = [{"name": "a"}, {"name": "b"}, {"name": "c"}, {"name": "d"}, {"name": "e"}]
        result = detect_anomalies(data, ["name"])
        assert result.summary["total_anomalies"] == 0

    def test_max_anomalies_cap(self):
        data = [{"val": float(i * 1000)} for i in range(200)]
        result = detect_anomalies(data, ["val"], max_anomalies=5)
        assert len(result.anomalies) <= 5
        assert result.summary.get("truncated") is True

    def test_critical_sorted_before_warnings(self):
        result = detect_anomalies(OUTLIER_DATA, SAMPLE_COLUMNS)
        if len(result.anomalies) >= 2:
            seen_warning = False
            for a in result.anomalies:
                if a.severity == "warning":
                    seen_warning = True
                if seen_warning and a.severity == "critical":
                    pytest.fail("critical after warning — not sorted correctly")

    def test_anomaly_has_required_fields(self):
        result = detect_anomalies(OUTLIER_DATA, SAMPLE_COLUMNS)
        assert len(result.anomalies) > 0
        a = result.anomalies[0]
        assert hasattr(a, "row_index")
        assert hasattr(a, "column")
        assert hasattr(a, "value")
        assert hasattr(a, "severity")
        assert a.severity in ("warning", "critical")
        assert a.anomaly_type in ("z-score", "iqr")


# ===========================================================================
# TestPagination
# ===========================================================================

@pytest.mark.unit
class TestPagination:

    def test_skip_page_1(self):
        params = PaginationParams.__new__(PaginationParams)
        params.page, params.per_page = 1, 20
        assert params.skip == 0

    def test_skip_page_2(self):
        params = PaginationParams.__new__(PaginationParams)
        params.page, params.per_page = 2, 20
        assert params.skip == 20

    def test_skip_custom_per_page(self):
        params = PaginationParams.__new__(PaginationParams)
        params.page, params.per_page = 3, 10
        assert params.skip == 20

    def test_limit_equals_per_page(self):
        params = PaginationParams.__new__(PaginationParams)
        params.page, params.per_page = 1, 50
        assert params.limit == 50

    def test_skip_large_page(self):
        params = PaginationParams.__new__(PaginationParams)
        params.page, params.per_page = 100, 25
        assert params.skip == 99 * 25

    def test_limit_unchanged_across_pages(self):
        for pp in (1, 10, 50, 100):
            params = PaginationParams.__new__(PaginationParams)
            params.page, params.per_page = 5, pp
            assert params.limit == pp
