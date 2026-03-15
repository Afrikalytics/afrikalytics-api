"""Service d'import CSV/Excel pour les etudes Afrikalytics."""
import csv
import io
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Taille max : 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_ROWS = 100_000
MAX_COLUMNS = 200


class ImportError(Exception):
    """Erreur lors de l'import."""

    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


class ImportResult:
    """Resultat d'un import."""

    def __init__(self):
        self.total_rows: int = 0
        self.imported_rows: int = 0
        self.skipped_rows: int = 0
        self.errors: list[dict] = []
        self.columns: list[str] = []
        self.preview: list[dict] = []  # 5 premieres lignes
        self.data: list[dict] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "imported_rows": self.imported_rows,
            "skipped_rows": self.skipped_rows,
            "columns": self.columns,
            "preview": self.preview,
            "errors": self.errors,
        }


async def validate_file(filename: str, file_size: int) -> None:
    """Valide le fichier avant import."""
    # Verifier extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ImportError(
            f"Extension '{ext}' non supportee. Extensions acceptees : {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Verifier taille
    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        raise ImportError(
            f"Fichier trop volumineux ({file_size // (1024 * 1024)} MB). Taille maximale : {max_mb} MB"
        )


def _detect_delimiter(text: str) -> str:
    """Detecte le delimiteur CSV (virgule, point-virgule, tab)."""
    first_lines = text.split("\n", 5)[:5]
    sample = "\n".join(first_lines)

    delimiters = {";": 0, ",": 0, "\t": 0}
    for d in delimiters:
        delimiters[d] = sample.count(d)

    # Le point-virgule est courant dans les fichiers francophones
    best = max(delimiters, key=delimiters.get)
    return best if delimiters[best] > 0 else ","


async def parse_csv(content: bytes, encoding: str = "utf-8") -> ImportResult:
    """Parse un fichier CSV et retourne les donnees structurees."""
    result = ImportResult()

    # Decoder le contenu
    try:
        text = content.decode(encoding)
    except UnicodeDecodeError:
        # Essayer latin-1 (courant en Afrique francophone)
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            raise ImportError("Impossible de decoder le fichier. Encodages supportes : UTF-8, Latin-1")

    # Supprimer BOM si present
    if text.startswith("\ufeff"):
        text = text[1:]

    # Detecter le delimiteur
    delimiter = _detect_delimiter(text)

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    result.columns = reader.fieldnames or []

    if not result.columns:
        raise ImportError("Aucune colonne detectee dans le fichier CSV")

    if len(result.columns) > MAX_COLUMNS:
        raise ImportError(
            f"Trop de colonnes ({len(result.columns)}). Maximum autorise : {MAX_COLUMNS}"
        )

    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            result.errors.append(
                {"row": i + 1, "error": f"Limite de {MAX_ROWS:,} lignes depassee. Import arrete."}
            )
            break

        # Nettoyer les valeurs
        cleaned = {k: v.strip() if v else None for k, v in row.items()}
        result.data.append(cleaned)
        result.imported_rows += 1

        if i < 5:
            result.preview.append(cleaned)

    result.total_rows = result.imported_rows + result.skipped_rows
    return result


async def parse_excel(content: bytes) -> ImportResult:
    """Parse un fichier Excel (.xlsx/.xls)."""
    result = ImportResult()
    try:
        import openpyxl
    except ModuleNotFoundError:
        raise ImportError(
            "Le module openpyxl n'est pas installe. Import Excel indisponible."
        )

    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(content), read_only=True, data_only=True
        )
        ws = wb.active

        if ws is None:
            raise ImportError("Fichier Excel vide ou aucune feuille active trouvee")

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise ImportError("Fichier Excel vide")

        # Extraire les en-tetes depuis la premiere ligne
        headers = [
            str(cell).strip() if cell is not None else f"col_{i}"
            for i, cell in enumerate(rows[0])
        ]
        result.columns = headers

        if len(headers) > MAX_COLUMNS:
            raise ImportError(
                f"Trop de colonnes ({len(headers)}). Maximum autorise : {MAX_COLUMNS}"
            )

        for i, row in enumerate(rows[1:], start=2):
            if i - 1 >= MAX_ROWS:
                result.errors.append(
                    {"row": i, "error": f"Limite de {MAX_ROWS:,} lignes depassee. Import arrete."}
                )
                break

            row_dict: dict[str, Any] = {}
            for j, value in enumerate(row):
                if j < len(headers):
                    if value is None:
                        row_dict[headers[j]] = None
                    elif isinstance(value, (int, float)):
                        row_dict[headers[j]] = value
                    else:
                        row_dict[headers[j]] = str(value).strip()

            result.data.append(row_dict)
            result.imported_rows += 1

            if i - 2 < 5:
                result.preview.append(row_dict)

        result.total_rows = result.imported_rows
        wb.close()

    except ImportError:
        raise
    except Exception as e:
        raise ImportError(f"Erreur de lecture Excel : {str(e)}")

    return result


async def parse_file(content: bytes, filename: str) -> ImportResult:
    """Parse un fichier selon son extension (CSV ou Excel)."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".csv":
        return await parse_csv(content)
    elif ext in (".xlsx", ".xls"):
        return await parse_excel(content)
    else:
        raise ImportError(f"Extension '{ext}' non supportee")
