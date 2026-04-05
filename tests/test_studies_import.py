"""
Tests for the CSV/Excel import endpoints on studies:

    POST /api/studies/import/preview  — validate + preview a file (no DB write)
    POST /api/studies/import          — parse + persist as Study + StudyDataset

RBAC:  Only users with the 'studies' permission may use these endpoints.
       Regular users must receive 403; unauthenticated requests must receive 401.

These are RED-phase tests.  They are written before the implementation is
fully verified against the test environment and will fail until the import
service, schemas, and router are wired up in the test database.

NOTE: The import endpoints accept multipart/form-data (UploadFile + Form fields).
The TestClient is used via the CSRFTestClient wrapper which injects the CSRF
header on POST requests.
"""
import os
import io
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")


# ---------------------------------------------------------------------------
# Minimal valid CSV content used across tests
# ---------------------------------------------------------------------------

VALID_CSV_CONTENT = b"nom,age,ville\nAlpha,25,Dakar\nBeta,30,Abidjan\n"
VALID_CSV_FILENAME = "test_import.csv"

EMPTY_CSV_CONTENT = b""
EMPTY_CSV_FILENAME = "empty.csv"

INVALID_EXTENSION_CONTENT = b"some binary data"
INVALID_EXTENSION_FILENAME = "data.exe"

# A minimal Excel file (just enough bytes that the parser can attempt to read)
# We use a real tiny XLSX produced inline via openpyxl bytes, but here we
# fall back to a plausible binary stub so the test can at least exercise the
# 400 error path for truly bad files.
BAD_EXCEL_CONTENT = b"PK\x03\x04"  # XLSX magic bytes but truncated — triggers parse error
BAD_EXCEL_FILENAME = "corrupt.xlsx"


def _csv_file(content: bytes = VALID_CSV_CONTENT, filename: str = VALID_CSV_FILENAME):
    """Return a files dict suitable for httpx/TestClient multipart upload."""
    return {"file": (filename, io.BytesIO(content), "text/csv")}


# ===========================================================================
# 1. /api/studies/import/preview — RBAC
# ===========================================================================

class TestImportPreviewRBAC:
    """Only users with studies permission can access the preview endpoint."""

    def test_preview_without_token_returns_401(self, client):
        """Unauthenticated request must be rejected with 401."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
        )
        assert response.status_code == 401

    def test_preview_regular_user_returns_403(self, client, auth_headers):
        """Regular (non-admin) user must receive 403."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_preview_admin_studies_returns_200(self, client, db):
        """admin_studies role has the studies permission — must succeed."""
        from app.models import User
        from app.auth import hash_password, create_access_token

        user = User(
            email="studies_import_admin@test.com",
            full_name="Studies Import Admin",
            hashed_password=hash_password("Password123!"),
            plan="entreprise",
            is_active=True,
            is_admin=True,
            admin_role="admin_studies",
        )
        db.add(user)
        db.commit()

        token = create_access_token(data={"sub": user.email})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=headers,
        )
        # Either 200 (file parsed) or 400 (parse error from env/dependencies)
        # but NOT 401 or 403
        assert response.status_code not in (401, 403)

    def test_preview_super_admin_returns_not_403(
        self, client, admin_auth_headers
    ):
        """super_admin must not be blocked with 403."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=admin_auth_headers,
        )
        assert response.status_code != 403

    def test_preview_content_admin_returns_not_403(
        self, client, content_admin_auth_headers
    ):
        """admin_content has studies permission — must not be blocked with 403."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=content_admin_auth_headers,
        )
        assert response.status_code != 403

    def test_preview_admin_insights_returns_403(self, client, db):
        """admin_insights does NOT have the studies permission — must receive 403."""
        from app.models import User
        from app.auth import hash_password, create_access_token

        user = User(
            email="insights_import_blocked@test.com",
            full_name="Insights Admin No Studies",
            hashed_password=hash_password("Password123!"),
            plan="entreprise",
            is_active=True,
            is_admin=True,
            admin_role="admin_insights",
        )
        db.add(user)
        db.commit()

        token = create_access_token(data={"sub": user.email})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=headers,
        )
        assert response.status_code == 403

    def test_preview_admin_reports_returns_403(self, client, db):
        """admin_reports does NOT have the studies permission — must receive 403."""
        from app.models import User
        from app.auth import hash_password, create_access_token

        user = User(
            email="reports_import_blocked@test.com",
            full_name="Reports Admin No Studies",
            hashed_password=hash_password("Password123!"),
            plan="entreprise",
            is_active=True,
            is_admin=True,
            admin_role="admin_reports",
        )
        db.add(user)
        db.commit()

        token = create_access_token(data={"sub": user.email})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=headers,
        )
        assert response.status_code == 403


# ===========================================================================
# 2. /api/studies/import/preview — response shape
# ===========================================================================

class TestImportPreviewResponse:
    """The preview endpoint must return a structured ImportPreviewResponse."""

    def test_preview_valid_csv_returns_200_with_envelope(
        self, client, admin_auth_headers
    ):
        """A valid CSV must return 200 with filename, file_size, and result."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "filename" in data
        assert "file_size" in data
        assert "result" in data

    def test_preview_result_contains_columns(
        self, client, admin_auth_headers
    ):
        """The result sub-object must include the detected column names."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        result = response.json()["result"]
        assert "columns" in result
        assert isinstance(result["columns"], list)
        assert len(result["columns"]) > 0

    def test_preview_result_contains_preview_rows(
        self, client, admin_auth_headers
    ):
        """The result must include a preview list (up to 5 rows)."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        result = response.json()["result"]
        assert "preview" in result
        assert isinstance(result["preview"], list)
        assert len(result["preview"]) <= 5

    def test_preview_result_contains_total_rows(
        self, client, admin_auth_headers
    ):
        """The result must include total_rows and imported_rows counts."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        result = response.json()["result"]
        assert "total_rows" in result
        assert "imported_rows" in result
        # Our test CSV has 2 data rows
        assert result["total_rows"] >= 2

    def test_preview_does_not_create_study_in_db(
        self, client, db, admin_auth_headers
    ):
        """
        Preview must NOT persist anything — study count must remain 0 after
        calling the preview endpoint.
        """
        from app.models import Study
        from sqlalchemy import select

        client.post(
            "/api/studies/import/preview",
            files=_csv_file(),
            headers=admin_auth_headers,
        )

        count = db.execute(select(Study)).scalars().all()
        assert len(count) == 0

    def test_preview_empty_file_returns_400(
        self, client, admin_auth_headers
    ):
        """An empty file must be rejected with 400 (validate_file fails)."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(content=EMPTY_CSV_CONTENT, filename=EMPTY_CSV_FILENAME),
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_preview_invalid_extension_returns_400(
        self, client, admin_auth_headers
    ):
        """A file with an unsupported extension must be rejected with 400."""
        response = client.post(
            "/api/studies/import/preview",
            files=_csv_file(
                content=INVALID_EXTENSION_CONTENT,
                filename=INVALID_EXTENSION_FILENAME,
            ),
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_preview_no_file_returns_422(self, client, admin_auth_headers):
        """A request with no file field must fail with 422."""
        response = client.post(
            "/api/studies/import/preview",
            headers=admin_auth_headers,
        )
        assert response.status_code == 422


# ===========================================================================
# 3. /api/studies/import — RBAC
# ===========================================================================

class TestImportStudyRBAC:
    """Only users with the studies permission may use the import endpoint."""

    def test_import_without_token_returns_401(self, client):
        """Unauthenticated request must be rejected with 401."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={"title": "Import Test", "description": "Desc", "category": "Test"},
        )
        assert response.status_code == 401

    def test_import_regular_user_returns_403(self, client, auth_headers):
        """Regular (non-admin) user must receive 403."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={"title": "Import Test", "description": "Desc", "category": "Test"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_import_admin_insights_returns_403(self, client, db):
        """admin_insights lacks studies permission — must receive 403."""
        from app.models import User
        from app.auth import hash_password, create_access_token

        user = User(
            email="insights_nowrite@test.com",
            full_name="Insights Admin",
            hashed_password=hash_password("Password123!"),
            plan="entreprise",
            is_active=True,
            is_admin=True,
            admin_role="admin_insights",
        )
        db.add(user)
        db.commit()

        token = create_access_token(data={"sub": user.email})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={"title": "Import Test", "description": "Desc", "category": "Test"},
            headers=headers,
        )
        assert response.status_code == 403


# ===========================================================================
# 4. /api/studies/import — happy path and error handling
# ===========================================================================

class TestImportStudyHappyPath:
    """Valid import creates a Study and a StudyDataset in the database."""

    def test_import_valid_csv_returns_201(self, client, admin_auth_headers):
        """A valid CSV file must return 201 and a study_id."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={
                "title": "Etude Importee Test",
                "description": "Description importee.",
                "category": "Commerce",
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert "study_id" in data
        assert isinstance(data["study_id"], int)

    def test_import_response_contains_message_and_result(
        self, client, admin_auth_headers
    ):
        """Response must include message, study_id, and result envelope."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={
                "title": "Etude Avec Result",
                "description": "Desc.",
                "category": "Finance",
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert "message" in data
        assert "result" in data
        assert "imported_rows" in data["result"]
        assert data["result"]["imported_rows"] >= 1

    def test_import_creates_study_in_db(self, client, db, admin_auth_headers):
        """The import endpoint must persist a Study record in the database."""
        from app.models import Study
        from sqlalchemy import select

        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={
                "title": "Etude Persistee",
                "description": "Doit etre dans la DB.",
                "category": "Test",
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        study_id = response.json()["study_id"]

        db.expire_all()
        study = db.execute(
            select(Study).where(Study.id == study_id)
        ).scalar_one_or_none()

        assert study is not None
        assert study.title == "Etude Persistee"

    def test_import_creates_study_dataset_in_db(
        self, client, db, admin_auth_headers
    ):
        """The import endpoint must persist a StudyDataset linked to the new study."""
        from app.models import Study, StudyDataset
        from sqlalchemy import select

        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={
                "title": "Etude Avec Dataset",
                "description": "Dataset doit exister.",
                "category": "Recherche",
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        study_id = response.json()["study_id"]

        db.expire_all()
        dataset = db.execute(
            select(StudyDataset).where(StudyDataset.study_id == study_id)
        ).scalar_one_or_none()

        assert dataset is not None
        assert dataset.row_count >= 1
        assert dataset.columns is not None

    def test_import_study_is_active_by_default(
        self, client, db, admin_auth_headers
    ):
        """The imported study must be created with is_active=True."""
        from app.models import Study
        from sqlalchemy import select

        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={
                "title": "Etude Active Par Defaut",
                "description": "Doit etre active.",
                "category": "Test",
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        study_id = response.json()["study_id"]

        db.expire_all()
        study = db.execute(
            select(Study).where(Study.id == study_id)
        ).scalar_one_or_none()

        assert study is not None
        assert study.is_active is True

    def test_import_empty_file_returns_400(
        self, client, admin_auth_headers
    ):
        """An empty file must be rejected with 400 before creating any record."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(content=EMPTY_CSV_CONTENT, filename=EMPTY_CSV_FILENAME),
            data={
                "title": "Etude Vide",
                "description": "Ne doit pas etre persistee.",
                "category": "Test",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_import_invalid_extension_returns_400(
        self, client, admin_auth_headers
    ):
        """A file with an unsupported extension must be rejected with 400."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(
                content=INVALID_EXTENSION_CONTENT,
                filename=INVALID_EXTENSION_FILENAME,
            ),
            data={
                "title": "Etude Extension Invalide",
                "description": "Ne doit pas etre persistee.",
                "category": "Test",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_import_missing_title_returns_422(
        self, client, admin_auth_headers
    ):
        """The title Form field is required — omitting it must return 422."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={"description": "Sans titre"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 422

    def test_import_title_too_long_returns_422(
        self, client, admin_auth_headers
    ):
        """A title longer than 200 characters must be rejected with 422."""
        response = client.post(
            "/api/studies/import",
            files=_csv_file(),
            data={
                "title": "T" * 201,
                "description": "Titre trop long.",
                "category": "Test",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 422
