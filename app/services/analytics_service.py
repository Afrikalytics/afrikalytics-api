"""Service d'analyse statistique des données importées."""
import logging
import statistics
from typing import Any
from collections import Counter
from datetime import datetime

logger = logging.getLogger(__name__)


class AnalysisResult:
    """Résultat d'une analyse statistique."""
    def __init__(self):
        self.summary: dict[str, Any] = {}
        self.trends: list[dict] = []
        self.correlations: list[dict] = []
        self.insights: list[str] = []  # Insights textuels en français
        self.kpis: list[dict] = []


def analyze_dataset(data: list[dict], columns: list[str]) -> AnalysisResult:
    """Analyse un dataset et génère des statistiques descriptives + insights."""
    result = AnalysisResult()

    if not data or not columns:
        result.insights.append("Aucune donnée à analyser.")
        return result

    result.summary = {
        "total_rows": len(data),
        "total_columns": len(columns),
        "columns": columns,
    }

    # Pour chaque colonne numérique, calculer les stats
    numeric_columns = _detect_numeric_columns(data, columns)
    text_columns = [c for c in columns if c not in numeric_columns]

    column_stats = {}
    for col in numeric_columns:
        values = _extract_numeric_values(data, col)
        if values:
            stats = _compute_stats(values)
            column_stats[col] = stats

            # Générer des insights textuels en français
            result.insights.append(
                f"📊 {col} : moyenne de {stats['mean']:.2f}, "
                f"médiane de {stats['median']:.2f}, "
                f"écart-type de {stats['std_dev']:.2f}"
            )

            # Détecter les tendances si données séquentielles
            if len(values) >= 5:
                trend = _detect_trend(values)
                if trend:
                    result.trends.append({
                        "column": col,
                        "direction": trend["direction"],
                        "strength": trend["strength"],
                        "description": trend["description_fr"]
                    })

    # Analyser les colonnes textuelles (top valeurs)
    for col in text_columns[:5]:  # Max 5 colonnes texte
        counter = Counter(row.get(col) for row in data if row.get(col))
        if counter:
            top = counter.most_common(5)
            result.insights.append(
                f"📋 {col} : valeur la plus fréquente \"{top[0][0]}\" ({top[0][1]} occurrences)"
            )

    # Générer les KPIs
    for col, stats in column_stats.items():
        result.kpis.append({
            "name": col,
            "value": stats["mean"],
            "min": stats["min"],
            "max": stats["max"],
            "trend": stats.get("trend_direction", "stable"),
            "unit": _guess_unit(col),
        })

    # Corrélations entre colonnes numériques
    if len(numeric_columns) >= 2:
        for i, col1 in enumerate(numeric_columns[:5]):
            for col2 in numeric_columns[i+1:5]:
                corr = _compute_correlation(data, col1, col2)
                if corr is not None and abs(corr) > 0.5:
                    strength = "forte" if abs(corr) > 0.8 else "modérée"
                    direction = "positive" if corr > 0 else "négative"
                    result.correlations.append({
                        "column1": col1,
                        "column2": col2,
                        "coefficient": round(corr, 3),
                        "strength": strength,
                        "direction": direction,
                    })
                    result.insights.append(
                        f"🔗 Corrélation {strength} {direction} entre {col1} et {col2} (r={corr:.3f})"
                    )

    # Résumé global
    result.insights.insert(0,
        f"📈 Analyse de {len(data)} lignes et {len(columns)} colonnes. "
        f"{len(numeric_columns)} colonnes numériques détectées."
    )

    result.summary["column_stats"] = column_stats
    result.summary["numeric_columns"] = numeric_columns
    result.summary["text_columns"] = text_columns

    return result


def _detect_numeric_columns(data: list[dict], columns: list[str]) -> list[str]:
    """Détecte les colonnes numériques en testant les premières lignes."""
    numeric = []
    sample = data[:min(20, len(data))]
    for col in columns:
        numeric_count = 0
        total = 0
        for row in sample:
            val = row.get(col)
            if val is not None:
                total += 1
                try:
                    float(str(val).replace(",", ".").replace(" ", ""))
                    numeric_count += 1
                except (ValueError, TypeError):
                    pass
        if total > 0 and numeric_count / total > 0.7:
            numeric.append(col)
    return numeric


def _extract_numeric_values(data: list[dict], col: str) -> list[float]:
    """Extrait les valeurs numériques d'une colonne."""
    values = []
    for row in data:
        val = row.get(col)
        if val is not None:
            try:
                values.append(float(str(val).replace(",", ".").replace(" ", "")))
            except (ValueError, TypeError):
                pass
    return values


def _compute_stats(values: list[float]) -> dict:
    """Calcule les statistiques descriptives."""
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
        "q1": _percentile(values, 25),
        "q3": _percentile(values, 75),
        "sum": sum(values),
    }


def _percentile(values: list[float], p: int) -> float:
    """Calcule le percentile p."""
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def _detect_trend(values: list[float]) -> dict | None:
    """Détecte la tendance linéaire d'une série."""
    n = len(values)
    if n < 3:
        return None
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(values) / n

    num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, values))
    den = sum((xi - x_mean) ** 2 for xi in x)

    if den == 0:
        return None

    slope = num / den

    # Normaliser par l'amplitude
    amplitude = max(values) - min(values)
    if amplitude == 0:
        return None

    relative_slope = slope / amplitude * n

    if abs(relative_slope) < 0.1:
        return None

    direction = "hausse" if slope > 0 else "baisse"
    strength = "forte" if abs(relative_slope) > 0.5 else "modérée"

    return {
        "direction": direction,
        "strength": strength,
        "slope": round(slope, 4),
        "description_fr": f"Tendance à la {direction} {strength} détectée (pente: {slope:.4f})"
    }


def _compute_correlation(data: list[dict], col1: str, col2: str) -> float | None:
    """Calcule la corrélation de Pearson entre deux colonnes."""
    pairs = []
    for row in data:
        v1, v2 = row.get(col1), row.get(col2)
        if v1 is not None and v2 is not None:
            try:
                pairs.append((
                    float(str(v1).replace(",", ".").replace(" ", "")),
                    float(str(v2).replace(",", ".").replace(" ", ""))
                ))
            except (ValueError, TypeError):
                pass

    if len(pairs) < 5:
        return None

    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]

    x_mean = sum(x_vals) / len(x_vals)
    y_mean = sum(y_vals) / len(y_vals)

    num = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    den_x = sum((x - x_mean) ** 2 for x in x_vals) ** 0.5
    den_y = sum((y - y_mean) ** 2 for y in y_vals) ** 0.5

    if den_x == 0 or den_y == 0:
        return None

    return num / (den_x * den_y)


def _guess_unit(column_name: str) -> str:
    """Devine l'unité probable d'une colonne par son nom."""
    name_lower = column_name.lower()
    if any(w in name_lower for w in ["prix", "cout", "montant", "revenu", "chiffre", "salaire", "budget"]):
        return "FCFA"
    if any(w in name_lower for w in ["poids", "masse", "kg"]):
        return "kg"
    if any(w in name_lower for w in ["distance", "km"]):
        return "km"
    if any(w in name_lower for w in ["taux", "pourcentage", "ratio", "%"]):
        return "%"
    if any(w in name_lower for w in ["age", "duree", "temps"]):
        return "ans"
    return ""
