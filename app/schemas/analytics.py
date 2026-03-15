"""Schemas Pydantic pour les endpoints d'analyse et détection d'anomalies."""
from pydantic import BaseModel, Field


# --- Analyse statistique ---

class ColumnStats(BaseModel):
    """Statistiques descriptives d'une colonne numérique."""
    count: int = Field(..., description="Nombre de valeurs")
    mean: float = Field(..., description="Moyenne")
    median: float = Field(..., description="Médiane")
    std_dev: float = Field(..., description="Écart-type")
    min: float = Field(..., description="Valeur minimale")
    max: float = Field(..., description="Valeur maximale")
    q1: float = Field(..., description="Premier quartile (25e percentile)")
    q3: float = Field(..., description="Troisième quartile (75e percentile)")
    sum: float = Field(0, description="Somme totale")


class TrendResult(BaseModel):
    """Résultat de détection de tendance sur une colonne."""
    column: str = Field(..., description="Nom de la colonne")
    direction: str = Field(..., description="Direction de la tendance (hausse/baisse)")
    strength: str = Field(..., description="Force de la tendance (forte/modérée)")
    description: str = Field(..., description="Description en français")


class CorrelationResult(BaseModel):
    """Corrélation entre deux colonnes numériques."""
    column1: str = Field(..., description="Première colonne")
    column2: str = Field(..., description="Deuxième colonne")
    coefficient: float = Field(..., description="Coefficient de corrélation de Pearson")
    strength: str = Field(..., description="Force (forte/modérée)")
    direction: str = Field(..., description="Direction (positive/négative)")


class KPIResult(BaseModel):
    """KPI calculé pour une colonne."""
    name: str = Field(..., description="Nom du KPI (colonne)")
    value: float = Field(..., description="Valeur moyenne")
    min: float = Field(..., description="Valeur minimale")
    max: float = Field(..., description="Valeur maximale")
    trend: str = Field("stable", description="Tendance (hausse/baisse/stable)")
    unit: str = Field("", description="Unité devinée (FCFA, kg, %, etc.)")


class AnalysisResponse(BaseModel):
    """Réponse complète d'une analyse statistique."""
    summary: dict = Field(default_factory=dict, description="Résumé global du dataset")
    trends: list[TrendResult] = Field(default_factory=list, description="Tendances détectées")
    correlations: list[CorrelationResult] = Field(default_factory=list, description="Corrélations significatives")
    insights: list[str] = Field(default_factory=list, description="Insights textuels en français")
    kpis: list[KPIResult] = Field(default_factory=list, description="KPIs calculés")


# --- Détection d'anomalies ---

class AnomalyResult(BaseModel):
    """Une anomalie détectée dans les données."""
    row_index: int = Field(..., description="Index de la ligne (0-based)")
    column: str = Field(..., description="Colonne concernée")
    value: float = Field(..., description="Valeur anormale")
    expected_range: str = Field(..., description="Plage de valeurs attendue")
    anomaly_type: str = Field(..., description="Méthode de détection (z-score ou iqr)")
    severity: str = Field(..., description="Sévérité (warning ou critical)")
    explanation: str = Field(..., description="Explication en français")


class AnomalySummary(BaseModel):
    """Résumé de la détection d'anomalies."""
    total_anomalies: int = Field(0, description="Nombre total d'anomalies")
    total_warnings: int = Field(0, description="Nombre d'avertissements")
    total_critical: int = Field(0, description="Nombre d'anomalies critiques")
    columns_analyzed: int = Field(0, description="Nombre de colonnes analysées")
    columns_with_anomalies: list[str] = Field(default_factory=list, description="Colonnes contenant des anomalies")
    methods_used: list[str] = Field(default_factory=list, description="Méthodes utilisées")
    thresholds: dict = Field(default_factory=dict, description="Seuils de détection appliqués")
    truncated: bool = Field(False, description="Résultats tronqués (trop d'anomalies)")
    message: str = Field("", description="Message de résumé en français")


class AnomaliesResponse(BaseModel):
    """Réponse complète de la détection d'anomalies."""
    anomalies: list[AnomalyResult] = Field(default_factory=list, description="Liste des anomalies détectées")
    summary: AnomalySummary = Field(default_factory=AnomalySummary, description="Résumé global")
