"""Service de détection d'anomalies dans les données importées.

Utilise deux méthodes complémentaires :
- Z-score : détecte les valeurs éloignées de la moyenne (> 2 ou 3 écarts-types)
- IQR (Interquartile Range) : détecte les valeurs en dehors de [Q1 - 1.5*IQR, Q3 + 1.5*IQR]
"""
import logging
import statistics
from dataclasses import dataclass, field

from app.services.analytics_service import (
    _detect_numeric_columns,
    _extract_numeric_values,
    _percentile,
)

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    """Représente une anomalie détectée dans les données."""
    row_index: int
    column: str
    value: float
    expected_range: str
    anomaly_type: str  # "z-score" ou "iqr"
    severity: str  # "warning" ou "critical"
    explanation: str  # Explication en français


@dataclass
class AnomalyDetectionResult:
    """Résultat global de la détection d'anomalies."""
    anomalies: list[Anomaly] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def detect_anomalies(
    data: list[dict],
    columns: list[str],
    z_threshold_warning: float = 2.0,
    z_threshold_critical: float = 3.0,
    iqr_multiplier: float = 1.5,
    max_anomalies: int = 100,
) -> AnomalyDetectionResult:
    """
    Détecte les anomalies dans un dataset en combinant Z-score et IQR.

    Args:
        data: Liste de dictionnaires (lignes du dataset).
        columns: Liste des noms de colonnes.
        z_threshold_warning: Seuil Z-score pour severity "warning" (défaut: 2.0).
        z_threshold_critical: Seuil Z-score pour severity "critical" (défaut: 3.0).
        iqr_multiplier: Multiplicateur IQR pour les bornes (défaut: 1.5).
        max_anomalies: Nombre maximum d'anomalies à retourner (défaut: 100).

    Returns:
        AnomalyDetectionResult avec la liste des anomalies et un résumé.
    """
    result = AnomalyDetectionResult()

    if not data or not columns:
        result.summary = {
            "total_anomalies": 0,
            "message": "Aucune donnée à analyser.",
        }
        return result

    numeric_columns = _detect_numeric_columns(data, columns)

    if not numeric_columns:
        result.summary = {
            "total_anomalies": 0,
            "columns_analyzed": 0,
            "message": "Aucune colonne numérique détectée pour l'analyse d'anomalies.",
        }
        return result

    total_warnings = 0
    total_critical = 0
    columns_with_anomalies = []

    for col in numeric_columns:
        values = _extract_numeric_values(data, col)
        if len(values) < 5:
            # Pas assez de données pour une détection fiable
            continue

        mean = statistics.mean(values)
        std_dev = statistics.stdev(values) if len(values) > 1 else 0
        q1 = _percentile(values, 25)
        q3 = _percentile(values, 75)
        iqr = q3 - q1

        iqr_lower = q1 - iqr_multiplier * iqr
        iqr_upper = q3 + iqr_multiplier * iqr

        col_anomaly_count = 0

        for row_idx, row in enumerate(data):
            if len(result.anomalies) >= max_anomalies:
                break

            raw_val = row.get(col)
            if raw_val is None:
                continue

            try:
                val = float(str(raw_val).replace(",", ".").replace(" ", ""))
            except (ValueError, TypeError):
                continue

            # --- Détection par Z-score ---
            if std_dev > 0:
                z_score = abs(val - mean) / std_dev

                if z_score > z_threshold_critical:
                    direction = "supérieure" if val > mean else "inférieure"
                    result.anomalies.append(Anomaly(
                        row_index=row_idx,
                        column=col,
                        value=val,
                        expected_range=f"{mean - z_threshold_critical * std_dev:.2f} — {mean + z_threshold_critical * std_dev:.2f}",
                        anomaly_type="z-score",
                        severity="critical",
                        explanation=(
                            f"Valeur critique : {val:.2f} est {direction} à la moyenne ({mean:.2f}) "
                            f"de {z_score:.1f} écarts-types. "
                            f"Cette valeur est très inhabituelle pour la colonne « {col} »."
                        ),
                    ))
                    total_critical += 1
                    col_anomaly_count += 1
                    continue  # Pas besoin de vérifier IQR si déjà critique

                elif z_score > z_threshold_warning:
                    direction = "supérieure" if val > mean else "inférieure"
                    result.anomalies.append(Anomaly(
                        row_index=row_idx,
                        column=col,
                        value=val,
                        expected_range=f"{mean - z_threshold_warning * std_dev:.2f} — {mean + z_threshold_warning * std_dev:.2f}",
                        anomaly_type="z-score",
                        severity="warning",
                        explanation=(
                            f"Valeur suspecte : {val:.2f} est {direction} à la moyenne ({mean:.2f}) "
                            f"de {z_score:.1f} écarts-types. "
                            f"Cette valeur mérite une vérification pour la colonne « {col} »."
                        ),
                    ))
                    total_warnings += 1
                    col_anomaly_count += 1
                    continue

            # --- Détection par IQR (complémentaire) ---
            if iqr > 0 and (val < iqr_lower or val > iqr_upper):
                # Vérifier que ce n'est pas déjà détecté par Z-score
                severity = "critical" if (val < q1 - 3 * iqr or val > q3 + 3 * iqr) else "warning"
                direction = "au-dessus" if val > iqr_upper else "en-dessous"
                bound = iqr_upper if val > iqr_upper else iqr_lower

                result.anomalies.append(Anomaly(
                    row_index=row_idx,
                    column=col,
                    value=val,
                    expected_range=f"{iqr_lower:.2f} — {iqr_upper:.2f}",
                    anomaly_type="iqr",
                    severity=severity,
                    explanation=(
                        f"Valeur aberrante (IQR) : {val:.2f} est {direction} de la borne "
                        f"{'supérieure' if val > iqr_upper else 'inférieure'} ({bound:.2f}). "
                        f"Plage attendue pour « {col} » : [{iqr_lower:.2f}, {iqr_upper:.2f}]."
                    ),
                ))
                if severity == "critical":
                    total_critical += 1
                else:
                    total_warnings += 1
                col_anomaly_count += 1

        if col_anomaly_count > 0:
            columns_with_anomalies.append(col)

        if len(result.anomalies) >= max_anomalies:
            break

    # Trier par sévérité (critical d'abord) puis par index de ligne
    severity_order = {"critical": 0, "warning": 1}
    result.anomalies.sort(key=lambda a: (severity_order.get(a.severity, 2), a.row_index))

    result.summary = {
        "total_anomalies": len(result.anomalies),
        "total_warnings": total_warnings,
        "total_critical": total_critical,
        "columns_analyzed": len(numeric_columns),
        "columns_with_anomalies": columns_with_anomalies,
        "methods_used": ["z-score", "iqr"],
        "thresholds": {
            "z_score_warning": z_threshold_warning,
            "z_score_critical": z_threshold_critical,
            "iqr_multiplier": iqr_multiplier,
        },
        "truncated": len(result.anomalies) >= max_anomalies,
        "message": _generate_summary_message(
            len(result.anomalies), total_critical, total_warnings, columns_with_anomalies
        ),
    }

    return result


def _generate_summary_message(
    total: int, critical: int, warnings: int, columns: list[str]
) -> str:
    """Génère un message de résumé en français."""
    if total == 0:
        return "Aucune anomalie détectée dans les données. La qualité des données semble bonne."

    parts = [f"{total} anomalie(s) détectée(s)"]

    if critical > 0:
        parts.append(f"dont {critical} critique(s)")
    if warnings > 0:
        parts.append(f"et {warnings} avertissement(s)")

    if columns:
        cols_str = ", ".join(columns[:5])
        parts.append(f"dans les colonnes : {cols_str}")

    return ". ".join(parts) + "."
