"""Schemas Pydantic pour l'import CSV/Excel des etudes."""
from pydantic import BaseModel
from typing import Any


class ImportValidationResult(BaseModel):
    """Resultat de validation d'un fichier importe."""

    total_rows: int
    imported_rows: int
    skipped_rows: int
    columns: list[str]
    preview: list[dict[str, Any]]  # 5 premieres lignes
    errors: list[dict[str, Any]]


class ImportResponse(BaseModel):
    """Reponse apres import reussi."""

    study_id: int
    message: str
    result: ImportValidationResult


class ImportPreviewResponse(BaseModel):
    """Reponse de previsualisation (sans creation d'etude)."""

    filename: str
    file_size: int
    result: ImportValidationResult
