import json
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc, func, or_
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

from database import get_db
from models import BlogPost, User
from app.utils import generate_slug, ensure_unique_slug
from app.dependencies import get_current_user
from app.permissions import check_blog_permission, get_paginated_results_stmt
from app.services.audit import log_action
from app.schemas.blog import (
    BlogPostCreate, BlogPostUpdate, BlogPostResponse, BlogPostPublic,
    BlogPostListResponse, BlogPostPublicListResponse,
    CategoryResponse, PopularPostResponse, SearchResponse,
)

router = APIRouter()


# ==================== ADMIN ENDPOINTS ====================

@router.post("/api/blog/posts", response_model=BlogPostResponse, status_code=201)
async def create_blog_post(
    data: BlogPostCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    if not data.slug:
        slug = generate_slug(data.title)
    else:
        slug = data.slug
    slug = ensure_unique_slug(db, slug)

    tags_json = json.dumps(data.tags) if data.tags else None

    new_post = BlogPost(
        title=data.title,
        slug=slug,
        excerpt=data.excerpt,
        content=data.content,
        featured_image=data.featured_image,
        category=data.category,
        tags=tags_json,
        author_id=current_user.id,
        status=data.status,
        scheduled_at=data.scheduled_at,
        meta_title=data.meta_title or data.title,
        meta_description=data.meta_description or data.excerpt,
        og_image=data.og_image or data.featured_image,
    )

    if data.status == "published":
        new_post.published_at = datetime.now(timezone.utc)

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="create", resource_type="blog_post",
            resource_id=new_post.id, details={"title": new_post.title, "slug": new_post.slug},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    response = BlogPostResponse.from_orm(new_post)
    response.author_name = current_user.full_name
    return response


@router.get("/api/blog/posts", response_model=BlogPostListResponse)
async def get_all_blog_posts(
    page: int = 1,
    per_page: int = 10,
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    per_page = min(per_page, 50)

    stmt = select(BlogPost).options(joinedload(BlogPost.author))

    if status:
        stmt = stmt.where(BlogPost.status == status)
    if category:
        stmt = stmt.where(BlogPost.category == category)
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                BlogPost.title.ilike(search_term),
                BlogPost.excerpt.ilike(search_term),
                BlogPost.content.ilike(search_term),
            )
        )

    stmt = stmt.order_by(desc(BlogPost.created_at))
    result = get_paginated_results_stmt(db, stmt, page, per_page)

    items_with_authors = []
    for post in result["items"]:
        post_dict = BlogPostResponse.from_orm(post)
        post_dict.author_name = post.author.full_name
        items_with_authors.append(post_dict)

    return {
        **result,
        "items": items_with_authors,
    }


@router.get("/api/blog/posts/{post_id}", response_model=BlogPostResponse)
async def get_blog_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    post = db.execute(
        select(BlogPost).options(joinedload(BlogPost.author)).where(BlogPost.id == post_id)
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Article non trouvé")

    response = BlogPostResponse.from_orm(post)
    response.author_name = post.author.full_name
    return response


@router.put("/api/blog/posts/{post_id}", response_model=BlogPostResponse)
async def update_blog_post(
    post_id: int,
    data: BlogPostUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    post = db.execute(
        select(BlogPost).options(joinedload(BlogPost.author)).where(BlogPost.id == post_id)
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Article non trouvé")

    update_data = data.dict(exclude_unset=True)

    if "slug" in update_data and update_data["slug"]:
        update_data["slug"] = ensure_unique_slug(db, update_data["slug"], post_id)

    if "tags" in update_data:
        update_data["tags"] = json.dumps(update_data["tags"]) if update_data["tags"] else None

    if "status" in update_data and update_data["status"] == "published" and not post.published_at:
        update_data["published_at"] = datetime.now(timezone.utc)

    for key, value in update_data.items():
        setattr(post, key, value)

    db.commit()
    db.refresh(post)

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="update", resource_type="blog_post",
            resource_id=post_id, details={"title": post.title, "updated_fields": list(data.dict(exclude_unset=True).keys())},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    response = BlogPostResponse.from_orm(post)
    response.author_name = post.author.full_name
    return response


@router.delete("/api/blog/posts/{post_id}")
async def delete_blog_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    post = db.execute(
        select(BlogPost).where(BlogPost.id == post_id)
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Article non trouvé")

    deleted_title = post.title

    # Audit log BEFORE deletion
    try:
        log_action(
            db=db, user_id=current_user.id, action="delete", resource_type="blog_post",
            resource_id=post_id, details={"deleted_title": deleted_title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    db.delete(post)
    db.commit()
    return {"message": "Article supprimé avec succès"}


@router.post("/api/blog/posts/{post_id}/publish", response_model=BlogPostResponse)
async def publish_blog_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    post = db.execute(
        select(BlogPost).options(joinedload(BlogPost.author)).where(BlogPost.id == post_id)
    ).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Article non trouvé")

    post.status = "published"
    post.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(post)

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="publish", resource_type="blog_post",
            resource_id=post_id, details={"title": post.title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    response = BlogPostResponse.from_orm(post)
    response.author_name = post.author.full_name
    return response


# ==================== PUBLIC ENDPOINTS ====================

@router.get("/api/blog/public/posts", response_model=BlogPostPublicListResponse)
async def get_public_blog_posts(
    page: int = 1,
    per_page: int = 10,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    per_page = min(per_page, 50)

    stmt = select(BlogPost).options(joinedload(BlogPost.author)).where(
        BlogPost.status == "published",
        BlogPost.published_at.isnot(None),
    )

    if category:
        stmt = stmt.where(BlogPost.category == category)

    stmt = stmt.order_by(desc(BlogPost.published_at))
    result = get_paginated_results_stmt(db, stmt, page, per_page)

    items_public = []
    for post in result["items"]:
        post_dict = BlogPostPublic.from_orm(post)
        post_dict.author_name = post.author.full_name
        items_public.append(post_dict)

    return {
        **result,
        "items": items_public,
    }


@router.get("/api/blog/public/posts/{slug}", response_model=BlogPostPublic)
async def get_public_blog_post_by_slug(
    slug: str,
    db: Session = Depends(get_db),
):
    post = db.execute(
        select(BlogPost).options(joinedload(BlogPost.author)).where(
            BlogPost.slug == slug,
            BlogPost.status == "published",
        )
    ).scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=404, detail="Article non trouvé")

    post.increment_views(db)

    response = BlogPostPublic.from_orm(post)
    response.author_name = post.author.full_name
    return response


@router.get("/api/blog/public/categories", response_model=List[CategoryResponse])
async def get_blog_categories(db: Session = Depends(get_db)):
    categories = db.execute(
        select(
            BlogPost.category,
            func.count(BlogPost.id).label('count')
        ).where(
            BlogPost.status == "published",
            BlogPost.category.isnot(None),
        ).group_by(BlogPost.category)
    ).all()

    return [
        {"name": cat.category, "count": cat.count}
        for cat in categories
    ]


@router.get("/api/blog/public/search", response_model=SearchResponse)
async def search_blog_posts(
    q: str,
    page: int = 1,
    per_page: int = 10,
    db: Session = Depends(get_db),
):
    per_page = min(per_page, 50)
    search_term = f"%{q}%"

    stmt = select(BlogPost).options(joinedload(BlogPost.author)).where(
        BlogPost.status == "published",
        or_(
            BlogPost.title.ilike(search_term),
            BlogPost.excerpt.ilike(search_term),
            BlogPost.content.ilike(search_term),
        ),
    ).order_by(desc(BlogPost.published_at))

    result = get_paginated_results_stmt(db, stmt, page, per_page)

    items_public = []
    for post in result["items"]:
        post_dict = BlogPostPublic.from_orm(post)
        post_dict.author_name = post.author.full_name
        items_public.append(post_dict)

    return {
        "items": items_public,
        "total": result["total"],
        "query": q,
    }


@router.get("/api/blog/public/popular", response_model=List[PopularPostResponse])
async def get_popular_posts(
    limit: int = 5,
    db: Session = Depends(get_db),
):
    posts = db.execute(
        select(BlogPost).where(
            BlogPost.status == "published"
        ).order_by(desc(BlogPost.views)).limit(limit)
    ).scalars().all()
    return posts


@router.get("/api/blog/public/related/{post_id}", response_model=List[BlogPostPublic])
async def get_related_posts(
    post_id: int,
    limit: int = 3,
    db: Session = Depends(get_db),
):
    current_post = db.execute(
        select(BlogPost).where(BlogPost.id == post_id)
    ).scalar_one_or_none()
    if not current_post:
        return []

    related = db.execute(
        select(BlogPost).options(joinedload(BlogPost.author)).where(
            BlogPost.status == "published",
            BlogPost.category == current_post.category,
            BlogPost.id != post_id,
        ).order_by(desc(BlogPost.published_at)).limit(limit)
    ).scalars().all()

    items_public = []
    for post in related:
        post_dict = BlogPostPublic.from_orm(post)
        post_dict.author_name = post.author.full_name
        items_public.append(post_dict)

    return items_public
