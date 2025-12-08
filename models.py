from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(50), default="basic")  # basic, professionnel, entreprise
    order_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    admin_role = Column(String(50), nullable=True)  # super_admin, admin_content, admin_studies, admin_insights, admin_reports
    parent_user_id = Column(Integer, nullable=True)  # Pour les sous-utilisateurs entreprise
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<User {self.email}>"


class Study(Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    duration = Column(String(50), nullable=True)  # Ex: "15-20 min"
    deadline = Column(String(100), nullable=True)  # Ex: "28 Février 2024"
    status = Column(String(50), default="Ouvert")  # Ouvert, Fermé, Bientôt
    icon = Column(String(50), default="users")  # users, trending, chart, file
    embed_url_particulier = Column(String(500), nullable=True)  # URL iframe sondage particulier
    embed_url_entreprise = Column(String(500), nullable=True)  # URL iframe sondage entreprise
    embed_url_results = Column(String(500), nullable=True)  # URL iframe résultats (dashboard)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Study {self.title}>"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    plan = Column(String(50), nullable=False)
    status = Column(String(50), default="active")  # active, cancelled, expired
    woocommerce_order_id = Column(String(100), nullable=True)
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Subscription {self.user_id} - {self.plan}>"
    
    # ================================================================
# MODELS BLOG - À AJOUTER DANS models.py
# ================================================================
# Ces modèles sont à ajouter dans votre fichier models.py existant
# ================================================================

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
import json


# ================================================================
# MODÈLE : BlogPost
# ================================================================

class BlogPost(Base):
    __tablename__ = "blog_posts"

    # ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Contenu principal
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    excerpt = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    featured_image = Column(String(500), nullable=True)
    
    # Organisation
    category = Column(String(100), nullable=True, index=True)
    tags = Column(Text, nullable=True)  # JSON string: '["AI", "Tendances"]'
    
    # Auteur (relation avec User)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    author = relationship("User", backref="blog_posts")
    
    # Statut & Publication
    status = Column(String(50), default="draft", index=True)  # draft, published, scheduled
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    
    # SEO
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(String(500), nullable=True)
    og_image = Column(String(500), nullable=True)  # Open Graph image
    
    # Analytics
    views = Column(Integer, default=0)
    
    # Temps de lecture (calculé automatiquement par trigger SQL)
    reading_time = Column(Integer, nullable=True)  # en minutes
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<BlogPost {self.title}>"
    
    # Helper methods
    def get_tags_list(self):
        """Convertir le string JSON en liste Python"""
        if self.tags:
            try:
                return json.loads(self.tags)
            except:
                return []
        return []
    
    def set_tags_list(self, tags_list):
        """Convertir une liste Python en string JSON"""
        if tags_list:
            self.tags = json.dumps(tags_list)
        else:
            self.tags = None
    
    def is_published(self):
        """Vérifier si l'article est publié"""
        return self.status == "published" and self.published_at is not None
    
    def increment_views(self, db):
        """Incrémenter le nombre de vues"""
        self.views += 1
        db.commit()


# ================================================================
# MODÈLE : NewsletterSubscriber
# ================================================================

class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    # ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Email
    email = Column(String(255), unique=True, nullable=False, index=True)
    
    # Statut
    status = Column(String(50), default="active", index=True)  # active, unsubscribed
    
    # Confirmation (double opt-in)
    is_confirmed = Column(Boolean, default=False)
    confirmation_token = Column(String(255), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Source
    source = Column(String(100), default="blog_footer")
    
    # Unsubscribe
    unsubscribe_token = Column(String(255), unique=True, nullable=True)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<NewsletterSubscriber {self.email}>"
    
    def is_active(self):
        """Vérifier si l'abonné est actif"""
        return self.status == "active" and self.is_confirmed


# ================================================================
# MODÈLE : NewsletterCampaign
# ================================================================

class NewsletterCampaign(Base):
    __tablename__ = "newsletter_campaigns"

    # ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Article associé
    blog_post_id = Column(Integer, ForeignKey("blog_posts.id", ondelete="SET NULL"), nullable=True)
    blog_post = relationship("BlogPost", backref="newsletter_campaigns")
    
    # Contenu email
    subject = Column(String(255), nullable=False)
    preview_text = Column(String(255), nullable=True)
    
    # Statut
    status = Column(String(50), default="draft")  # draft, scheduled, sent, failed
    
    # Envoi
    sent_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Stats
    recipients_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<NewsletterCampaign {self.subject}>"
    
    def get_open_rate(self):
        """Calculer le taux d'ouverture"""
        if self.recipients_count > 0:
            return round((self.opened_count / self.recipients_count) * 100, 2)
        return 0
    
    def get_click_rate(self):
        """Calculer le taux de clic"""
        if self.recipients_count > 0:
            return round((self.clicked_count / self.recipients_count) * 100, 2)
        return 0


# ================================================================
# HELPER FUNCTIONS
# ================================================================

def generate_slug(title):
    """
    Générer un slug depuis un titre
    Exemple: "Les 5 Tendances IA en 2025" → "les-5-tendances-ia-en-2025"
    """
    import re
    import unicodedata
    
    # Normaliser les accents
    slug = unicodedata.normalize('NFKD', title)
    slug = slug.encode('ascii', 'ignore').decode('utf-8')
    
    # Minuscules
    slug = slug.lower()
    
    # Remplacer espaces et caractères spéciaux par des tirets
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    
    # Supprimer les tirets au début et à la fin
    slug = slug.strip('-')
    
    # Limiter à 100 caractères
    slug = slug[:100]
    
    return slug


def ensure_unique_slug(db, slug, post_id=None):
    """
    S'assurer que le slug est unique
    Si existe déjà, ajouter un suffixe numérique
    """
    original_slug = slug
    counter = 1
    
    while True:
        # Vérifier si le slug existe
        query = db.query(BlogPost).filter(BlogPost.slug == slug)
        
        # Si on modifie un article existant, exclure son propre ID
        if post_id:
            query = query.filter(BlogPost.id != post_id)
        
        existing = query.first()
        
        if not existing:
            return slug
        
        # Slug existe, ajouter un suffixe
        slug = f"{original_slug}-{counter}"
        counter += 1
        
        # Sécurité : max 100 tentatives
        if counter > 100:
            import secrets
            slug = f"{original_slug}-{secrets.token_hex(4)}"
            break
    
    return slug


def calculate_reading_time(content):
    """
    Calculer le temps de lecture estimé
    Basé sur 200 mots par minute
    """
    import re
    
    # Supprimer les balises HTML
    text = re.sub(r'<[^>]+>', '', content)
    
    # Compter les mots
    words = len(text.split())
    
    # Calculer temps (minimum 1 minute)
    reading_time = max(1, round(words / 200))
    
    return reading_time


# ================================================================
# CONSTANTES UTILES
# ================================================================

BLOG_CATEGORIES = [
    "Digital & AI",
    "Finance",
    "RH & Talents",
    "Agriculture",
    "Santé",
    "Éducation",
    "Commerce",
    "Actualités"
]

BLOG_STATUSES = {
    "draft": "Brouillon",
    "published": "Publié",
    "scheduled": "Programmé"
}

NEWSLETTER_STATUSES = {
    "active": "Actif",
    "unsubscribed": "Désabonné"
}

CAMPAIGN_STATUSES = {
    "draft": "Brouillon",
    "scheduled": "Programmé",
    "sent": "Envoyé",
    "failed": "Échoué"
}


# ================================================================
# EXEMPLE D'UTILISATION
# ================================================================

"""
# Créer un article
from models import BlogPost, generate_slug, ensure_unique_slug
from database import get_db

db = next(get_db())

slug = generate_slug("Les 5 Tendances IA en 2025")
slug = ensure_unique_slug(db, slug)

new_post = BlogPost(
    title="Les 5 Tendances IA en 2025",
    slug=slug,
    excerpt="Découvrez les tendances...",
    content="<p>Contenu HTML...</p>",
    category="Digital & AI",
    tags='["IA", "Tendances", "2025"]',
    author_id=1,
    status="draft"
)

db.add(new_post)
db.commit()
db.refresh(new_post)

# Récupérer les tags sous forme de liste
tags_list = new_post.get_tags_list()  # ["IA", "Tendances", "2025"]

# Modifier les tags
new_post.set_tags_list(["IA", "Afrique", "Innovation"])
db.commit()

# Publier l'article
from datetime import datetime
new_post.status = "published"
new_post.published_at = datetime.utcnow()
db.commit()

# Incrémenter les vues
new_post.increment_views(db)
"""


class Insight(Base):
    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    key_findings = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    is_published = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Insight {self.title}>"


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_url = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size = Column(String(50), nullable=True)
    download_count = Column(Integer, default=0)
    is_available = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Report {self.title}>"
