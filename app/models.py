from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import backref, declared_attr, relationship
from sqlalchemy.sql import func, text

from app.database import Base


# ================================================================
# MIXIN: SoftDeleteMixin
# ================================================================

class SoftDeleteMixin:
    """Mixin for soft-delete support. Adds deleted_at column and is_deleted property."""

    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    @property
    def is_deleted(self):
        return self.deleted_at is not None


# ================================================================
# MODEL: User
# ================================================================

class User(SoftDeleteMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(50), nullable=False, server_default=text("'basic'"))
    order_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("'true'"))
    is_admin = Column(Boolean, nullable=False, server_default=text("'false'"))
    admin_role = Column(String(50), nullable=True)
    parent_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    subscriptions = relationship("Subscription", back_populates="user", lazy="dynamic")
    blog_posts = relationship("BlogPost", back_populates="author", lazy="dynamic")

    def __repr__(self):
        return f"<User {self.email}>"


# ================================================================
# MODEL: Study
# ================================================================

class Study(SoftDeleteMixin, Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    duration = Column(String(50), default="15-20 min")
    deadline = Column(String(50), nullable=True)
    status = Column(String(50), server_default=text("'Ouvert'"))
    icon = Column(String(50), default="users")
    embed_url_particulier = Column(String(2000), nullable=True)
    embed_url_entreprise = Column(String(2000), nullable=True)
    embed_url_results = Column(String(2000), nullable=True)
    report_url_basic = Column(String(2000), nullable=True)
    report_url_premium = Column(String(2000), nullable=True)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<Study {self.title}>"


# ================================================================
# MODEL: Subscription
# ================================================================

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String(50), nullable=False)
    status = Column(String(50), default="active")
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="subscriptions")

    def __repr__(self):
        return f"<Subscription {self.user_id} - {self.plan}>"


# ================================================================
# MODEL: Insight
# ================================================================

class Insight(SoftDeleteMixin, Base):
    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id"), nullable=False)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=True)
    key_findings = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    recommendations = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    author = Column(String(100), nullable=True)
    images = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    is_published = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<Insight {self.title}>"


# ================================================================
# MODEL: Report
# ================================================================

class Report(SoftDeleteMixin, Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    file_url = Column(String(2000), nullable=False)
    file_name = Column(String(300), nullable=True)
    file_size = Column(Integer, nullable=True)
    report_type = Column(String(50), default="premium")
    download_count = Column(Integer, default=0)
    is_available = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<Report {self.title}>"


# ================================================================
# MODEL: BlogPost
# ================================================================

class BlogPost(SoftDeleteMixin, Base):
    __tablename__ = "blog_posts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'scheduled')",
            name="ck_blog_posts_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    excerpt = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    featured_image = Column(String(2000), nullable=True)
    category = Column(String(100), nullable=True, index=True)
    tags = Column(JSONB, server_default=text("'[]'::jsonb"))

    # Author
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author = relationship("User", back_populates="blog_posts")

    # Status & scheduling
    status = Column(String(20), server_default=text("'draft'"), index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # SEO
    meta_title = Column(String(200), nullable=True)
    meta_description = Column(String(500), nullable=True)
    og_image = Column(String(2000), nullable=True)

    # Stats
    views = Column(Integer, server_default=text("0"))

    # Reading time (calculated automatically)
    reading_time = Column(Integer, nullable=True)  # in minutes

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<BlogPost {self.title}>"

    # Helper methods
    def is_published_status(self):
        """Check if the post is published"""
        return self.status == "published" and self.published_at is not None

    def increment_views(self, db):
        """Atomically increment view count to avoid race conditions."""
        db.execute(
            update(BlogPost)
            .where(BlogPost.id == self.id)
            .values(views=BlogPost.views + 1)
        )
        db.commit()


# ================================================================
# MODEL: NewsletterSubscriber
# ================================================================

class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    status = Column(String(50), default="active")
    source = Column(String(100), default="blog_footer")
    is_confirmed = Column(Boolean, default=False)
    confirmation_token = Column(String(255), nullable=True)
    unsubscribe_token = Column(String(255), nullable=True)

    # Timestamps
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<NewsletterSubscriber {self.email}>"


# ================================================================
# MODEL: NewsletterCampaign
# ================================================================

class NewsletterCampaign(Base):
    __tablename__ = "newsletter_campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'sent', 'failed')",
            name="ck_newsletter_campaigns_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    blog_post_id = Column(Integer, ForeignKey("blog_posts.id"), nullable=True, index=True)
    subject = Column(String(255), nullable=False)
    preview_text = Column(String(500), nullable=True)
    status = Column(String(20), default="draft", index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    recipients_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<NewsletterCampaign {self.subject}>"


# ================================================================
# MODEL: Contact
# ================================================================

class Contact(SoftDeleteMixin, Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(254), nullable=False)
    company = Column(String(200), nullable=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Contact {self.name}>"


# ================================================================
# MODEL: VerificationCode
# ================================================================

class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(String(6), nullable=False)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<VerificationCode {self.user_id}>"


# ================================================================
# MODEL: TokenBlacklist
# ================================================================

class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<TokenBlacklist {self.jti}>"


# ================================================================
# MODEL: AuditLog
# ================================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_action_created", "user_id", "action", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(Integer, nullable=True)
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.resource_type}>"
