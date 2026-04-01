from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
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

    def soft_delete(self) -> None:
        """Mark this record as deleted (set deleted_at to now)."""
        from datetime import datetime, timezone
        self.deleted_at = datetime.now(timezone.utc)


# ================================================================
# MODEL: User
# ================================================================

class User(SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "plan IN ('basic', 'professionnel', 'entreprise')",
            name="ck_users_plan",
        ),
        CheckConstraint(
            "admin_role IS NULL OR admin_role IN ("
            "'super_admin', 'admin_content', 'admin_studies', "
            "'admin_insights', 'admin_reports')",
            name="ck_users_admin_role",
        ),
        # Composite unique: one SSO identity per provider (P16 fix)
        # Replaces the old global unique on sso_id alone, which would
        # cause collisions between different SSO providers.
        UniqueConstraint("sso_provider", "sso_id", name="uq_users_sso_provider_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(50), nullable=False, server_default=text("'basic'"))
    order_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    admin_role = Column(String(50), nullable=True)
    # ondelete=SET NULL: keep sub-users if the parent account is deleted
    parent_user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # SSO fields
    sso_provider = Column(String(20), nullable=True)   # "google", "microsoft", None
    # sso_id uniqueness enforced per-provider via partial index ix_users_sso_provider_id
    sso_id = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    # Relationships — use default lazy="select" to avoid loading 4 extra tables
    # on every User query. Use selectinload()/joinedload() explicitly in queries
    # that need related data (see routers).
    subscriptions = relationship("Subscription", back_populates="user")
    blog_posts = relationship("BlogPost", back_populates="author")
    notifications = relationship("Notification", back_populates="user")
    api_keys = relationship("ApiKey", back_populates="user")

    def __repr__(self):
        return f"<User {self.email}>"


# ================================================================
# MODEL: Study
# ================================================================

class Study(SoftDeleteMixin, Base):
    __tablename__ = "studies"
    __table_args__ = (
        CheckConstraint(
            "status IN ('Ouvert', 'Ferme', 'Bientot')",
            name="ck_studies_status",
        ),
        Index("ix_studies_active", "is_active", "deleted_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    duration = Column(String(50), server_default=text("'15-20 min'"))
    deadline = Column(String(50), nullable=True)
    status = Column(String(50), server_default=text("'Ouvert'"))
    icon = Column(String(50), server_default=text("'users'"))
    embed_url_particulier = Column(String(2000), nullable=True)
    embed_url_entreprise = Column(String(2000), nullable=True)
    embed_url_results = Column(String(2000), nullable=True)
    report_url_basic = Column(String(2000), nullable=True)
    report_url_premium = Column(String(2000), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    # Relationships
    # imported data extracted to StudyDataset (P4 fix — avoids bloating
    # the transactional studies table with multi-MB JSONB payloads)
    # Relationships — default lazy loading to avoid pulling multi-MB JSONB
    # datasets and all insights/reports on every Study query.
    dataset = relationship(
        "StudyDataset", back_populates="study", uselist=False,
        cascade="all, delete-orphan",
    )
    insights = relationship("Insight", back_populates="study")
    reports = relationship("Report", back_populates="study")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    def __repr__(self):
        return f"<Study {self.title}>"


# ================================================================
# MODEL: StudyDataset (P4 — extracted from Study.imported_data)
# ================================================================

class StudyDataset(Base):
    """
    Stores imported CSV/Excel data for a study in a dedicated table.

    Previously this data lived as JSONB columns directly on the studies table
    (imported_data, imported_columns, imported_row_count, import_source).
    Extracting it avoids bloating the transactional studies table with
    potentially multi-MB JSONB payloads and allows independent lifecycle
    management (e.g. re-import without touching the study metadata).
    """
    __tablename__ = "study_datasets"

    id = Column(BigInteger, primary_key=True, index=True)
    study_id = Column(
        BigInteger,
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    data = Column(JSONB, nullable=False)         # The actual rows
    columns = Column(JSONB, nullable=False)       # Column names list
    row_count = Column(Integer, nullable=False)   # Number of imported rows
    source_filename = Column(String(255), nullable=True)  # Original file name

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    study = relationship("Study", back_populates="dataset")

    def __repr__(self):
        return f"<StudyDataset study_id={self.study_id} rows={self.row_count}>"


# ================================================================
# MODEL: Subscription
# ================================================================

class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
        # Partial unique index: at most one active subscription per user
        Index(
            "uq_one_active_subscription_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=CASCADE: delete subscriptions when the user account is deleted
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, server_default=text("'active'"))
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="subscriptions")

    def __repr__(self):
        return f"<Subscription {self.user_id} - {self.plan}>"


# ================================================================
# MODEL: Payment
# ================================================================

class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_payments_amount_positive",
        ),
        Index("ix_payments_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=SET NULL: keep payment records even if the user account is deleted
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subscription_id = Column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Payment details
    amount = Column(Integer, nullable=False)  # Amount in FCFA
    currency = Column(String(3), nullable=False, server_default=text("'XOF'"))

    # Provider info
    provider = Column(String(50), nullable=False)  # "paydunya", "woocommerce"
    provider_ref = Column(String(255), nullable=True, unique=True)
    provider_status = Column(String(50), nullable=True)

    # Payment metadata
    plan = Column(String(50), nullable=False)
    payment_method = Column(String(50), nullable=True)  # "mobile_money", "card", etc.

    status = Column(
        String(20), nullable=False, server_default=text("'pending'")
    )

    metadata_json = Column(JSONB, nullable=True)  # Any additional provider data

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user = relationship("User", backref="payments")
    subscription = relationship("Subscription", backref="payments")

    def __repr__(self):
        return f"<Payment {self.id} - {self.provider} - {self.status}>"


# ================================================================
# MODEL: Insight
# ================================================================

class Insight(SoftDeleteMixin, Base):
    __tablename__ = "insights"
    __table_args__ = (
        Index("ix_insights_study_id", "study_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=CASCADE: delete insights when the parent study is deleted
    study_id = Column(
        BigInteger, ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=True)
    key_findings = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    recommendations = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    author = Column(String(100), nullable=True)
    images = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    is_published = Column(Boolean, nullable=False, server_default=text("false"))

    # Relationships
    study = relationship("Study", back_populates="insights")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    def __repr__(self):
        return f"<Insight {self.title}>"


# ================================================================
# MODEL: Report
# ================================================================

class Report(SoftDeleteMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('basic', 'premium')",
            name="ck_reports_report_type",
        ),
        Index("ix_reports_study_id", "study_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=CASCADE: delete reports when the parent study is deleted
    study_id = Column(
        BigInteger, ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    file_url = Column(String(2000), nullable=False)
    file_name = Column(String(300), nullable=True)
    file_size = Column(Integer, nullable=True)
    report_type = Column(String(50), nullable=False, server_default=text("'premium'"))
    download_count = Column(Integer, nullable=False, server_default=text("0"))
    is_available = Column(Boolean, nullable=False, server_default=text("true"))

    # Relationships
    study = relationship("Study", back_populates="reports")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

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

    id = Column(BigInteger, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    excerpt = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    featured_image = Column(String(2000), nullable=True)
    category = Column(String(100), nullable=True, index=True)
    tags = Column(JSONB, server_default=text("'[]'::jsonb"))

    # Author — SET NULL so posts survive user deletion
    author_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    author = relationship("User", back_populates="blog_posts")

    # Status & scheduling
    status = Column(String(20), nullable=False, server_default=text("'draft'"), index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # SEO
    meta_title = Column(String(200), nullable=True)
    meta_description = Column(String(500), nullable=True)
    og_image = Column(String(2000), nullable=True)

    # Stats
    views = Column(Integer, nullable=False, server_default=text("0"))

    # Reading time (calculated automatically)
    reading_time = Column(Integer, nullable=True)  # in minutes

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    def __repr__(self):
        return f"<BlogPost {self.title}>"

    def is_published_status(self):
        """Check if the post is published."""
        return self.status == "published" and self.published_at is not None

    def increment_views(self, db):
        """Atomically increment view count. Caller is responsible for commit."""
        db.execute(
            update(BlogPost)
            .where(BlogPost.id == self.id)
            .values(views=BlogPost.views + 1)
        )
        # NOTE: Do NOT commit here — let the caller or request lifecycle manage
        # the transaction boundary. This prevents unexpected partial commits.


# ================================================================
# MODEL: NewsletterSubscriber
# ================================================================

class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'unsubscribed', 'bounced')",
            name="ck_newsletter_subscribers_status",
        ),
        Index(
            "ix_newsletter_confirmed_active",
            "id",
            postgresql_where=text("is_confirmed = true AND status = 'active'"),
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    status = Column(String(50), nullable=False, server_default=text("'active'"))
    source = Column(String(100), nullable=False, server_default=text("'blog_footer'"))
    is_confirmed = Column(Boolean, nullable=False, server_default=text("false"))

    # Security: tokens are stored as SHA-256 hashes. The plaintext token is
    # generated at subscription time, emailed to the user, and NEVER persisted.
    # The prefix (first 8 chars of the raw token) allows log correlation without
    # revealing the full secret. Lookup is done by hash, not plaintext.
    confirmation_token_hash = Column(String(64), nullable=True, index=True)
    confirmation_token_prefix = Column(String(8), nullable=True)
    unsubscribe_token_hash = Column(String(64), nullable=True, index=True)
    unsubscribe_token_prefix = Column(String(8), nullable=True)

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

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=SET NULL: keep campaign records even if the linked blog post is deleted
    blog_post_id = Column(
        BigInteger,
        ForeignKey("blog_posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subject = Column(String(255), nullable=False)
    preview_text = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, server_default=text("'draft'"), index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    recipients_count = Column(Integer, nullable=False, server_default=text("0"))
    opened_count = Column(Integer, nullable=False, server_default=text("0"))
    clicked_count = Column(Integer, nullable=False, server_default=text("0"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    def __repr__(self):
        return f"<NewsletterCampaign {self.subject}>"


# ================================================================
# MODEL: Contact
# ================================================================

class Contact(SoftDeleteMixin, Base):
    __tablename__ = "contacts"

    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(254), nullable=False)
    company = Column(String(200), nullable=True)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, server_default=text("false"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Contact {self.name}>"


# ================================================================
# MODEL: VerificationCode
# ================================================================

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    __table_args__ = (
        # Composite index for the common "find active code for user" query
        Index(
            "ix_verification_codes_user_active",
            "user_id",
            "is_used",
            "expires_at",
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=CASCADE: purge codes when the user account is deleted
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code = Column(String(6), nullable=False)
    is_used = Column(Boolean, nullable=False, server_default=text("false"))
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

    id = Column(BigInteger, primary_key=True, index=True)
    jti = Column(String(255), unique=True, nullable=False, index=True)
    # ondelete=CASCADE: purge blacklisted tokens when the user account is deleted
    # nullable for family-level revocations not tied to a specific user
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Refresh token rotation: family grouping for compromise detection
    token_family = Column(String(255), nullable=True, index=True)
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

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=SET NULL: keep audit trail even if the user account is deleted
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(BigInteger, nullable=True)
    details = Column(JSONB, nullable=True)
    # Network metadata — never log raw tokens, passwords, or API keys in these fields
    ip_address = Column(String(45), nullable=True)   # IPv4 or IPv6 (max 45 chars)
    user_agent = Column(String(500), nullable=True)  # Browser/client identifier

    # Timestamps — indexed for partition-based cleanup and time-range queries
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.resource_type}>"


# ================================================================
# MODEL: Notification
# ================================================================

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "is_read", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=CASCADE: purge notifications when the user account is deleted
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Renamed from "type" (SQL reserved word) to "notification_type" in the application
    # layer; DB column name kept as "type" for backward compatibility via Column(name=...)
    notification_type = Column(
        "type", String(50), nullable=False
    )  # "study_created", "payment_confirmed", etc.
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, server_default=text("false"), index=True)
    # Changed from JSON to JSONB for index support and better performance
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification {self.id} - {self.notification_type}>"


# ================================================================
# MODEL: ApiKey
# ================================================================

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(BigInteger, primary_key=True, index=True)
    # ondelete=CASCADE: revoke API keys when the user account is deleted
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Security: the raw API key is shown ONCE at creation time and never stored.
    # Only the SHA-256 hash is persisted for validation, and the first 8 chars
    # (prefix) are kept for display/identification in the dashboard.
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    key_prefix = Column(String(8), nullable=False)  # e.g. "ak_xK3mP" — safe to display
    name = Column(String(100), nullable=False)  # "Mon site web", "App mobile"
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    allowed_origins = Column(JSONB, nullable=True)  # ["https://monsite.com"]
    # FIX P8: was `default=["read"]` — mutable list shared across instances.
    # Now uses server_default so the DB supplies the value on INSERT.
    permissions = Column(
        JSONB,
        nullable=False,
        server_default=text('\'["read"]\'::jsonb'),
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey {self.name} (prefix={self.key_prefix}...)>"


# ================================================================
# MODEL: MarketplaceTemplate
# ================================================================

class MarketplaceTemplate(Base):
    __tablename__ = "marketplace_templates"
    __table_args__ = (
        CheckConstraint(
            "plan_required IN ('basic', 'professionnel', 'entreprise')",
            name="ck_marketplace_templates_plan_required",
        ),
        CheckConstraint(
            "price >= 0",
            name="ck_marketplace_templates_price_non_negative",
        ),
        CheckConstraint(
            "rating >= 0.0 AND rating <= 5.0",
            name="ck_marketplace_templates_rating_range",
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, index=True)  # retail, finance, sante, etc.
    # FIX P9: was `default=[]` — mutable list shared across instances.
    # Now uses server_default so the DB supplies the value on INSERT.
    tags = Column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    preview_image_url = Column(String(500), nullable=True)
    layout_json = Column(JSONB, nullable=False)  # DashboardLayout JSON
    demo_data = Column(JSONB, nullable=True)
    # ondelete=SET NULL: keep templates even if the author account is deleted
    author_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_published = Column(Boolean, nullable=False, server_default=text("false"), index=True)
    is_free = Column(Boolean, nullable=False, server_default=text("true"))
    price = Column(Integer, nullable=False, server_default=text("0"))  # Prix en FCFA
    plan_required = Column(String(20), nullable=False, server_default=text("'basic'"))
    install_count = Column(Integer, nullable=False, server_default=text("0"))
    rating = Column(Float, nullable=False, server_default=text("0.0"))
    rating_count = Column(Integer, nullable=False, server_default=text("0"))
    widget_count = Column(Integer, nullable=False, server_default=text("0"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    author = relationship("User", backref="marketplace_templates")

    def __repr__(self):
        return f"<MarketplaceTemplate {self.name}>"


# ================================================================
# MODEL: DashboardLayout (user-saved dashboard configurations)
# ================================================================

class DashboardLayout(Base):
    __tablename__ = "dashboard_layouts"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    layout = Column(JSONB, nullable=False)  # Full DashboardLayout JSON (widgets + positions)
    is_template = Column(Boolean, nullable=False, server_default=text("false"))
    template_category = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<DashboardLayout {self.name}>"


# ================================================================
# MODEL: SSOExchangeCode
# ================================================================

class SSOExchangeCode(Base):
    """
    Short-lived, single-use code that substitutes the JWT in SSO redirect URLs.

    Flow:
      1. SSO callback generates this code (TTL: 60 s) and stores the associated JWT.
      2. Callback redirects browser to: /login?sso_code=<code>&sso=true
      3. Frontend POSTs code to POST /api/auth/sso/exchange.
      4. Exchange endpoint validates (not expired, not used), marks it used,
         and returns the JWT in the JSON response body — never in a URL.

    Security properties:
      - JWT never appears in server logs, browser history, or Referer headers.
      - 60-second TTL limits the exposure window.
      - is_used flag prevents replay attacks.
      - Code is 32 bytes of URL-safe random data (256-bit entropy).
    """
    __tablename__ = "sso_exchange_codes"

    id = Column(BigInteger, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    # ondelete=CASCADE: purge exchange codes when the user account is deleted
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Pre-generated JWT stored server-side; never transmitted via URL.
    access_token = Column(Text, nullable=False)
    is_used = Column(Boolean, nullable=False, server_default=text("false"))
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SSOExchangeCode user_id={self.user_id} used={self.is_used}>"
