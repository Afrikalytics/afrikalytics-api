"""
Tests pour les endpoints du blog — /api/blog/*

Couvre:
- Admin : POST, GET liste, GET detail, PUT, DELETE, publish
- Public : GET /api/blog/public/posts (liste publiee), GET /api/blog/public/posts/{slug}
- Public : GET /api/blog/public/categories, GET /api/blog/public/search?q=...
- Public : GET /api/blog/public/popular
"""

BASE_BLOG_POST_PAYLOAD = {
    "title": "Article sur le marche ivoirien 2026",
    "excerpt": "Analyse du marche de Cote d'Ivoire pour l'annee 2026.",
    "content": "Contenu detaille de l'article sur le marche ivoirien. Il s'agit d'une analyse complete.",
    "category": "Marche",
    "status": "draft",
    "tags": ["marche", "afrique", "investissement"],
}


class TestAdminCreateBlogPost:
    """Tests pour POST /api/blog/posts."""

    def test_super_admin_can_create_blog_post(
        self, client, admin_auth_headers
    ):
        response = client.post(
            "/api/blog/posts",
            json=BASE_BLOG_POST_PAYLOAD,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == BASE_BLOG_POST_PAYLOAD["title"]
        assert data["category"] == BASE_BLOG_POST_PAYLOAD["category"]
        assert data["status"] == "draft"
        assert "id" in data
        assert "slug" in data

    def test_create_published_post_sets_published_at(
        self, client, admin_auth_headers
    ):
        payload = {**BASE_BLOG_POST_PAYLOAD, "status": "published"}
        response = client.post(
            "/api/blog/posts",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    def test_regular_user_cannot_create_blog_post_returns_403(
        self, client, auth_headers
    ):
        response = client.post(
            "/api/blog/posts",
            json=BASE_BLOG_POST_PAYLOAD,
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_create_blog_post_without_token_returns_401(self, client):
        response = client.post("/api/blog/posts", json=BASE_BLOG_POST_PAYLOAD)

        assert response.status_code == 401

    def test_create_blog_post_missing_required_fields_returns_422(
        self, client, admin_auth_headers
    ):
        # Manque 'content' (obligatoire)
        incomplete_payload = {"title": "Titre seul"}
        response = client.post(
            "/api/blog/posts",
            json=incomplete_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 422


class TestAdminListBlogPosts:
    """Tests pour GET /api/blog/posts."""

    def test_super_admin_can_list_all_posts(
        self, client, blog_post, admin_auth_headers
    ):
        response = client.get("/api/blog/posts", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1

    def test_list_posts_response_contains_pagination_fields(
        self, client, blog_post, admin_auth_headers
    ):
        response = client.get("/api/blog/posts", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        for field in ["items", "total", "page", "per_page", "total_pages"]:
            assert field in data, f"Champ de pagination '{field}' manquant"

    def test_regular_user_cannot_list_admin_posts_returns_403(
        self, client, blog_post, auth_headers
    ):
        response = client.get("/api/blog/posts", headers=auth_headers)

        assert response.status_code == 403

    def test_list_posts_without_token_returns_401(self, client):
        response = client.get("/api/blog/posts")

        assert response.status_code == 401


class TestAdminGetBlogPostById:
    """Tests pour GET /api/blog/posts/{post_id}."""

    def test_super_admin_can_get_post_by_id(
        self, client, blog_post, admin_auth_headers
    ):
        response = client.get(
            f"/api/blog/posts/{blog_post.id}", headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == blog_post.id
        assert data["title"] == blog_post.title
        assert data["slug"] == blog_post.slug

    def test_get_nonexistent_post_returns_404(self, client, admin_auth_headers):
        response = client.get(
            "/api/blog/posts/99999", headers=admin_auth_headers
        )

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_regular_user_cannot_get_admin_post_returns_403(
        self, client, blog_post, auth_headers
    ):
        response = client.get(
            f"/api/blog/posts/{blog_post.id}", headers=auth_headers
        )

        assert response.status_code == 403


class TestAdminUpdateBlogPost:
    """Tests pour PUT /api/blog/posts/{post_id}."""

    def test_super_admin_can_update_blog_post(
        self, client, blog_post, admin_auth_headers
    ):
        updated_payload = {"title": "Article Mis a Jour", "status": "published"}
        response = client.put(
            f"/api/blog/posts/{blog_post.id}",
            json=updated_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Article Mis a Jour"
        assert data["status"] == "published"

    def test_update_sets_published_at_when_publishing(
        self, client, blog_post, admin_auth_headers, db
    ):
        """Publier un article draft doit remplir published_at."""
        # S'assurer que le post est en draft au depart
        from app.models import BlogPost
        db.query(BlogPost).filter(BlogPost.id == blog_post.id).update(
            {"status": "draft", "published_at": None}
        )
        db.commit()

        response = client.put(
            f"/api/blog/posts/{blog_post.id}",
            json={"status": "published"},
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["published_at"] is not None

    def test_regular_user_cannot_update_blog_post_returns_403(
        self, client, blog_post, auth_headers
    ):
        response = client.put(
            f"/api/blog/posts/{blog_post.id}",
            json={"title": "Tentative"},
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_update_nonexistent_post_returns_404(
        self, client, admin_auth_headers
    ):
        response = client.put(
            "/api/blog/posts/99999",
            json={"title": "N'existe pas"},
            headers=admin_auth_headers,
        )

        assert response.status_code == 404


class TestAdminDeleteBlogPost:
    """Tests pour DELETE /api/blog/posts/{post_id}."""

    def test_super_admin_can_delete_blog_post(
        self, client, blog_post, admin_auth_headers
    ):
        response = client.delete(
            f"/api/blog/posts/{blog_post.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_deleted_post_no_longer_accessible(
        self, client, blog_post, admin_auth_headers
    ):
        """Apres suppression, le GET doit retourner 404."""
        client.delete(
            f"/api/blog/posts/{blog_post.id}", headers=admin_auth_headers
        )

        get_response = client.get(
            f"/api/blog/posts/{blog_post.id}", headers=admin_auth_headers
        )
        assert get_response.status_code == 404

    def test_regular_user_cannot_delete_blog_post_returns_403(
        self, client, blog_post, auth_headers
    ):
        response = client.delete(
            f"/api/blog/posts/{blog_post.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403


class TestAdminPublishBlogPost:
    """Tests pour POST /api/blog/posts/{post_id}/publish."""

    def test_super_admin_can_publish_blog_post(
        self, client, blog_post, admin_auth_headers
    ):
        response = client.post(
            f"/api/blog/posts/{blog_post.id}/publish",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    def test_publish_nonexistent_post_returns_404(
        self, client, admin_auth_headers
    ):
        response = client.post(
            "/api/blog/posts/99999/publish",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    def test_regular_user_cannot_publish_blog_post_returns_403(
        self, client, blog_post, auth_headers
    ):
        response = client.post(
            f"/api/blog/posts/{blog_post.id}/publish",
            headers=auth_headers,
        )

        assert response.status_code == 403


class TestPublicBlogPosts:
    """Tests pour les endpoints publics GET /api/blog/public/posts."""

    def test_public_can_list_published_posts(self, client, blog_post):
        response = client.get("/api/blog/public/posts")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_public_list_contains_pagination_fields(self, client, blog_post):
        response = client.get("/api/blog/public/posts")

        assert response.status_code == 200
        data = response.json()
        for field in ["items", "total", "page", "per_page", "total_pages"]:
            assert field in data

    def test_public_list_does_not_require_auth(self, client):
        """Le endpoint public ne necessite pas de token."""
        response = client.get("/api/blog/public/posts")

        # Doit repondre 200 (meme vide), pas 401
        assert response.status_code == 200

    def test_public_list_only_shows_published_posts(
        self, client, blog_post, admin_auth_headers
    ):
        """Un post en draft ne doit pas apparaitre dans la liste publique."""
        # Creer un post en draft
        client.post(
            "/api/blog/posts",
            json={**BASE_BLOG_POST_PAYLOAD, "status": "draft"},
            headers=admin_auth_headers,
        )

        response = client.get("/api/blog/public/posts")

        assert response.status_code == 200
        # Tous les items doivent avoir published_at non null
        for item in response.json()["items"]:
            assert item["published_at"] is not None


class TestPublicBlogPostBySlug:
    """Tests pour GET /api/blog/public/posts/{slug}."""

    def test_public_can_get_published_post_by_slug(self, client, blog_post):
        response = client.get(f"/api/blog/public/posts/{blog_post.slug}")

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == blog_post.slug
        assert data["title"] == blog_post.title

    def test_get_nonexistent_slug_returns_404(self, client):
        response = client.get("/api/blog/public/posts/slug-inexistant-xyz")

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_get_post_by_slug_increments_views(self, client, blog_post, db):
        """Chaque acces au detail public doit incrementer le compteur de vues."""
        from app.models import BlogPost
        initial_views = blog_post.views

        client.get(f"/api/blog/public/posts/{blog_post.slug}")

        db.expire_all()
        updated_post = db.query(BlogPost).filter(
            BlogPost.id == blog_post.id
        ).first()
        assert updated_post.views > initial_views


class TestPublicBlogCategories:
    """Tests pour GET /api/blog/public/categories."""

    def test_public_can_get_categories(self, client, blog_post):
        response = client.get("/api/blog/public/categories")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_categories_contain_expected_fields(self, client, blog_post):
        response = client.get("/api/blog/public/categories")

        assert response.status_code == 200
        data = response.json()
        # La fixture blog_post a status='published' et une categorie
        if data:
            for item in data:
                assert "name" in item
                assert "count" in item
                assert item["count"] > 0


class TestPublicBlogSearch:
    """Tests pour GET /api/blog/public/search."""

    def test_public_search_returns_matching_posts(self, client, blog_post):
        # Chercher par mot present dans le titre de la fixture
        response = client.get("/api/blog/public/search?q=Article")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "Article"

    def test_public_search_no_results_returns_empty_list(self, client, blog_post):
        response = client.get(
            "/api/blog/public/search?q=MotInexistantXYZ123456"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []


class TestPublicBlogPopular:
    """Tests pour GET /api/blog/public/popular."""

    def test_public_can_get_popular_posts(self, client, blog_post):
        response = client.get("/api/blog/public/popular")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_popular_posts_respect_limit_parameter(self, client, blog_post):
        response = client.get("/api/blog/public/popular?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2
