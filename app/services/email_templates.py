"""
Templates HTML centralises pour les emails Afrikalytics.

Chaque fonction retourne une chaine HTML prete a envoyer via send_email().
Toutes les donnees utilisateur sont echappees avec html.escape() pour
prevenir les injections XSS.
"""

from html import escape
from typing import Optional


# ---------------------------------------------------------------------------
# Template de base
# ---------------------------------------------------------------------------

def _base_template(content: str) -> str:
    """Template de base commun a tous les emails."""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        {content}
        <hr style="margin-top: 30px; border: none; border-top: 1px solid #eee;">
        <p style="color: #666; font-size: 12px;">
            &copy; 2026 Afrikalytics AI by Marketym. Tous droits r&eacute;serv&eacute;s.
        </p>
    </body>
    </html>
    """


def _button(url: str, label: str, *, color: str = "#2563eb") -> str:
    """Bouton CTA reutilisable."""
    return f"""
    <p style="margin: 30px 0;">
        <a href="{escape(url)}"
           style="background-color: {color}; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 8px; font-weight: bold;">
            {escape(label)}
        </a>
    </p>
    """


def _signature() -> str:
    """Signature commune a tous les emails."""
    return """
    <hr>
    <p><em>L'\u00e9quipe Afrikalytics AI by Marketym</em></p>
    """


# ---------------------------------------------------------------------------
# Auth - inscription
# ---------------------------------------------------------------------------

def welcome_email(full_name: str) -> str:
    """Email de bienvenue apres inscription (plan Basic gratuit)."""
    return _base_template(f"""
        <h2>Bienvenue {escape(full_name)} !</h2>
        <p>Votre compte Afrikalytics a \u00e9t\u00e9 cr\u00e9\u00e9 avec succ\u00e8s.</p>
        <p><strong>Plan :</strong> Basic (Gratuit)</p>
        <hr>
        <p>Avec votre compte Basic, vous pouvez :</p>
        <ul>
            <li>\u2705 Participer \u00e0 toutes nos \u00e9tudes</li>
            <li>\u2705 Voir un aper\u00e7u des insights</li>
            <li>\u2705 Acc\u00e9der au dashboard basic</li>
        </ul>
        <p>Pour acc\u00e9der aux r\u00e9sultats complets, insights d\u00e9taill\u00e9s et rapports PDF, passez \u00e0 <strong>Premium</strong> !</p>
        <hr>
        <p><a href="https://dashboard.afrikalytics.com">Acc\u00e9der \u00e0 mon dashboard \u2192</a></p>
        <p><a href="https://afrikalytics.com/premium">D\u00e9couvrir les offres Premium \u2192</a></p>
        {_signature()}
    """)


# ---------------------------------------------------------------------------
# Auth - code de verification 2FA
# ---------------------------------------------------------------------------

def verification_code_email(full_name: str, code: str) -> str:
    """Email de code de verification (login 2FA)."""
    return _base_template(f"""
        <h2>Code de v\u00e9rification</h2>
        <p>Bonjour {escape(full_name)},</p>
        <p>Voici votre code de connexion :</p>
        <div style="background-color: #f3f4f6; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1f2937;">{escape(code)}</span>
        </div>
        <p style="color: #666; font-size: 14px;">Ce code expire dans <strong>10 minutes</strong>.</p>
        <p style="color: #e74c3c; font-size: 14px;">Si vous n'avez pas demand\u00e9 ce code, ignorez cet email.</p>
        {_signature()}
    """)


def resend_verification_code_email(full_name: str, code: str) -> str:
    """Email de renvoi du code de verification."""
    return _base_template(f"""
        <h2>Nouveau code de v\u00e9rification</h2>
        <p>Bonjour {escape(full_name)},</p>
        <p>Voici votre nouveau code de connexion :</p>
        <div style="background-color: #f3f4f6; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1f2937;">{escape(code)}</span>
        </div>
        <p style="color: #666; font-size: 14px;">Ce code expire dans <strong>10 minutes</strong>.</p>
        {_signature()}
    """)


# ---------------------------------------------------------------------------
# Auth - mot de passe
# ---------------------------------------------------------------------------

def forgot_password_email(full_name: str, reset_url: str) -> str:
    """Email de reinitialisation de mot de passe."""
    return _base_template(f"""
        <h2>R\u00e9initialisation de mot de passe</h2>
        <p>Bonjour {escape(full_name)},</p>
        <p>Vous avez demand\u00e9 \u00e0 r\u00e9initialiser votre mot de passe Afrikalytics.</p>
        <p>Cliquez sur le bouton ci-dessous pour d\u00e9finir un nouveau mot de passe :</p>
        {_button(reset_url, "R\u00e9initialiser mon mot de passe")}
        <p style="color: #666; font-size: 14px;">Ce lien expire dans <strong>1 heure</strong>.</p>
        <p style="color: #666; font-size: 14px;">Si vous n'avez pas demand\u00e9 cette r\u00e9initialisation, ignorez cet email.</p>
        {_signature()}
    """)


def password_reset_confirmation_email(full_name: str) -> str:
    """Email de confirmation apres reinitialisation du mot de passe."""
    return _base_template(f"""
        <h2>Mot de passe modifi\u00e9</h2>
        <p>Bonjour {escape(full_name)},</p>
        <p>Votre mot de passe Afrikalytics a \u00e9t\u00e9 r\u00e9initialis\u00e9 avec succ\u00e8s.</p>
        <p>Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.</p>
        {_button("https://dashboard.afrikalytics.com/login", "Se connecter")}
        <p style="color: #e74c3c; font-size: 14px;">Si vous n'\u00eates pas \u00e0 l'origine de cette modification, contactez-nous imm\u00e9diatement.</p>
        {_signature()}
    """)


def password_changed_email(full_name: str) -> str:
    """Email de confirmation apres changement de mot de passe (users/change-password)."""
    return _base_template(f"""
        <h2>Mot de passe modifi\u00e9</h2>
        <p>Bonjour {escape(full_name)},</p>
        <p>Votre mot de passe Afrikalytics a \u00e9t\u00e9 modifi\u00e9 avec succ\u00e8s.</p>
        <p>Si vous n'\u00eates pas \u00e0 l'origine de cette modification, contactez-nous imm\u00e9diatement.</p>
        {_signature()}
    """)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def contact_form_email(
    name: str, email: str, company: Optional[str], message: str
) -> str:
    """Notification de nouveau message de contact (envoyee a l'equipe)."""
    company_display = escape(company) if company else "Non renseign\u00e9"
    return _base_template(f"""
        <h2>Nouveau message de contact</h2>
        <p><strong>Nom :</strong> {escape(name)}</p>
        <p><strong>Email :</strong> {escape(email)}</p>
        <p><strong>Entreprise :</strong> {company_display}</p>
        <hr>
        <p><strong>Message :</strong></p>
        <p>{escape(message)}</p>
        <hr>
        <p><em>Message envoy\u00e9 depuis le formulaire de contact Afrikalytics</em></p>
    """)


# ---------------------------------------------------------------------------
# Admin - creation de compte
# ---------------------------------------------------------------------------

def admin_user_created_email(
    full_name: str, email: str, password: str, plan: str
) -> str:
    """Email de bienvenue pour un utilisateur cree par un admin."""
    return _base_template(f"""
        <h2>Bienvenue sur Afrikalytics AI !</h2>
        <p>Bonjour {escape(full_name)},</p>
        <p>Votre compte a \u00e9t\u00e9 cr\u00e9\u00e9 avec succ\u00e8s.</p>
        <p><strong>Email :</strong> {escape(email)}</p>
        <p><strong>Mot de passe :</strong> {escape(password)}</p>
        <p><strong>Plan :</strong> {escape(plan.capitalize())}</p>
        {_button("https://dashboard.afrikalytics.com/login", "Se connecter")}
        <p style="color: #666;">Nous vous recommandons de changer votre mot de passe apr\u00e8s votre premi\u00e8re connexion.</p>
        {_signature()}
    """)


# ---------------------------------------------------------------------------
# Dashboard - rappels d'expiration d'abonnement
# ---------------------------------------------------------------------------

def subscription_reminder_j7_email(full_name: str, plan: str) -> str:
    """Rappel J-7 avant expiration de l'abonnement."""
    return _base_template(f"""
        <h2>Bonjour {escape(full_name)},</h2>
        <p>Votre abonnement <strong>{escape(plan.capitalize())}</strong> expire dans <strong>7 jours</strong>.</p>
        <p>Pour continuer \u00e0 profiter de tous les avantages Premium :</p>
        <ul>
            <li>\u2705 R\u00e9sultats en temps r\u00e9el</li>
            <li>\u2705 Insights complets</li>
            <li>\u2705 Rapports PDF d\u00e9taill\u00e9s</li>
            <li>\u2705 Dashboard avanc\u00e9</li>
        </ul>
        {_button("https://afrikalytics.com/checkout", "Renouveler mon abonnement")}
        {_signature()}
    """)


def subscription_reminder_j3_email(full_name: str, plan: str) -> str:
    """Rappel J-3 avant expiration de l'abonnement."""
    return _base_template(f"""
        <h2>Bonjour {escape(full_name)},</h2>
        <p>Votre abonnement <strong>{escape(plan.capitalize())}</strong> expire dans <strong>3 jours</strong>.</p>
        <p style="color: #e74c3c; font-weight: bold;">
            Sans renouvellement, vous perdrez l'acc\u00e8s aux fonctionnalit\u00e9s Premium.
        </p>
        {_button("https://afrikalytics.com/checkout", "Renouveler maintenant", color="#e74c3c")}
        {_signature()}
    """)


def subscription_reminder_j0_email(full_name: str, plan: str) -> str:
    """Rappel J-0 : dernier jour de l'abonnement."""
    return _base_template(f"""
        <h2>Bonjour {escape(full_name)},</h2>
        <p style="color: #e74c3c; font-size: 18px; font-weight: bold;">
            Votre abonnement {escape(plan.capitalize())} expire AUJOURD'HUI !
        </p>
        <p>Renouvelez maintenant pour ne pas perdre vos acc\u00e8s Premium.</p>
        <p style="margin: 30px 0;">
            <a href="https://afrikalytics.com/checkout"
               style="background-color: #e74c3c; color: white; padding: 16px 32px;
                      text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                RENOUVELER MAINTENANT
            </a>
        </p>
        {_signature()}
    """)


def subscription_expired_email(full_name: str, plan: str) -> str:
    """Notification d'expiration de l'abonnement (retrogradation vers Basic)."""
    return _base_template(f"""
        <h2>Bonjour {escape(full_name)},</h2>
        <p>Votre abonnement <strong>{escape(plan.capitalize())}</strong> a expir\u00e9.</p>
        <p>Votre compte a \u00e9t\u00e9 r\u00e9trograd\u00e9 au <strong>Plan Basic (gratuit)</strong>.</p>
        <p>Vous conservez l'acc\u00e8s \u00e0 :</p>
        <ul>
            <li>\u2705 Participation aux \u00e9tudes</li>
            <li>\u2705 Aper\u00e7u des insights</li>
            <li>\u2705 Dashboard basic</li>
        </ul>
        <p>Vous n'avez plus acc\u00e8s \u00e0 :</p>
        <ul>
            <li>\u274c R\u00e9sultats en temps r\u00e9el</li>
            <li>\u274c Insights complets</li>
            <li>\u274c Rapports PDF</li>
        </ul>
        {_button("https://afrikalytics.com/checkout", "R\u00e9activer mon abonnement Premium")}
        {_signature()}
    """)


def team_subscription_expired_email(
    member_name: str, owner_name: str
) -> str:
    """Notification aux membres d'equipe quand l'abonnement Entreprise expire."""
    return _base_template(f"""
        <h2>Bonjour {escape(member_name)},</h2>
        <p>L'abonnement Entreprise de <strong>{escape(owner_name)}</strong> a expir\u00e9.</p>
        <p>Votre compte a \u00e9t\u00e9 r\u00e9trograd\u00e9 au <strong>Plan Basic (gratuit)</strong>.</p>
        <p>Vous conservez l'acc\u00e8s \u00e0 :</p>
        <ul>
            <li>\u2705 Participation aux \u00e9tudes</li>
            <li>\u2705 Aper\u00e7u des insights</li>
            <li>\u2705 Dashboard basic</li>
        </ul>
        <p>Vous n'avez plus acc\u00e8s aux fonctionnalit\u00e9s Premium.</p>
        <p>Si vous souhaitez continuer avec un abonnement individuel :</p>
        {_button("https://afrikalytics.com/premium", "Voir les offres Premium")}
        {_signature()}
    """)


# ---------------------------------------------------------------------------
# Payments - confirmation de paiement
# ---------------------------------------------------------------------------

def payment_upgrade_email(full_name: str, plan: str) -> str:
    """Email de confirmation de paiement pour un utilisateur existant."""
    return _base_template(f"""
        <h2>F\u00e9licitations {escape(full_name)} !</h2>
        <p>Votre abonnement <strong>{escape(plan.capitalize())}</strong> est maintenant actif.</p>
        <hr>
        <p>Vous avez maintenant acc\u00e8s \u00e0 :</p>
        <ul>
            <li>R\u00e9sultats en temps r\u00e9el</li>
            <li>Insights complets</li>
            <li>Rapports PDF d\u00e9taill\u00e9s</li>
            <li>Dashboard avanc\u00e9</li>
            <li>Support prioritaire</li>
        </ul>
        <hr>
        <p><a href="https://dashboard.afrikalytics.com">Acc\u00e9der \u00e0 mon dashboard Premium</a></p>
        {_signature()}
    """)


def payment_new_user_email(
    name: str, email: str, temp_password: str, plan: str
) -> str:
    """Email de bienvenue + identifiants pour un nouvel utilisateur apres paiement."""
    return _base_template(f"""
        <h2>Bienvenue {escape(name or '')} !</h2>
        <p>Votre compte Afrikalytics <strong>{escape(plan.capitalize())}</strong> a \u00e9t\u00e9 cr\u00e9\u00e9 avec succ\u00e8s.</p>
        <hr>
        <h3>Vos identifiants de connexion :</h3>
        <p><strong>Email :</strong> {escape(email)}</p>
        <p><strong>Mot de passe temporaire :</strong> {escape(temp_password)}</p>
        <p style="color: #e74c3c;"><em>Pensez \u00e0 changer votre mot de passe apr\u00e8s votre premi\u00e8re connexion.</em></p>
        <hr>
        <p>Vous avez maintenant acc\u00e8s \u00e0 :</p>
        <ul>
            <li>R\u00e9sultats en temps r\u00e9el</li>
            <li>Insights complets</li>
            <li>Rapports PDF d\u00e9taill\u00e9s</li>
            <li>Dashboard avanc\u00e9</li>
            <li>Support prioritaire</li>
        </ul>
        <hr>
        <p><a href="https://dashboard.afrikalytics.com/login">Se connecter \u00e0 mon dashboard</a></p>
        {_signature()}
    """)


# ---------------------------------------------------------------------------
# Enterprise - gestion d'equipe
# ---------------------------------------------------------------------------

def enterprise_team_join_email(
    member_name: str, owner_name: str, old_plan: str
) -> str:
    """Email pour un utilisateur existant qui rejoint une equipe Entreprise."""
    pro_notice = (
        "<p style='color: #e74c3c;'><strong>Note :</strong> "
        "Votre abonnement Professionnel a \u00e9t\u00e9 annul\u00e9.</p>"
        if old_plan == "professionnel" else ""
    )
    return _base_template(f"""
        <h2>Bonne nouvelle !</h2>
        <p>Bonjour {escape(member_name)},</p>
        <p><strong>{escape(owner_name)}</strong> vous a ajout\u00e9(e) \u00e0 son \u00e9quipe Entreprise sur Afrikalytics.</p>
        <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p><strong>Votre nouveau plan :</strong> Entreprise</p>
            <p><strong>Ancien plan :</strong> {escape(old_plan.capitalize())}</p>
            {pro_notice}
        </div>
        <p>Vous pouvez continuer \u00e0 utiliser votre compte avec vos identifiants habituels.</p>
        {_button("https://dashboard.afrikalytics.com/login", "Acc\u00e9der au dashboard")}
        {_signature()}
    """)


def enterprise_team_invite_email(
    member_name: str,
    member_email: str,
    owner_name: str,
    temp_password: str,
) -> str:
    """Email d'invitation pour un nouveau membre d'equipe Entreprise."""
    return _base_template(f"""
        <h2>Bienvenue sur Afrikalytics AI !</h2>
        <p>Bonjour {escape(member_name)},</p>
        <p><strong>{escape(owner_name)}</strong> vous a invit\u00e9(e) \u00e0 rejoindre son \u00e9quipe sur Afrikalytics.</p>
        <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p><strong>Email :</strong> {escape(member_email)}</p>
            <p><strong>Mot de passe temporaire :</strong> {escape(temp_password)}</p>
            <p><strong>Plan :</strong> Entreprise</p>
        </div>
        <p style="color: #e74c3c;">Veuillez changer votre mot de passe apr\u00e8s votre premi\u00e8re connexion.</p>
        {_button("https://dashboard.afrikalytics.com/login", "Se connecter")}
        {_signature()}
    """)


def enterprise_team_removal_email(
    member_name: str, owner_name: str
) -> str:
    """Email de notification quand un membre est retire de l'equipe Entreprise."""
    return _base_template(f"""
        <h2>Changement de votre plan</h2>
        <p>Bonjour {escape(member_name)},</p>
        <p>Vous avez \u00e9t\u00e9 retir\u00e9(e) de l'\u00e9quipe Entreprise de <strong>{escape(owner_name)}</strong> sur Afrikalytics.</p>
        <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p><strong>Votre nouveau plan :</strong> Basic (gratuit)</p>
            <p>Votre compte reste actif et vous pouvez toujours vous connecter.</p>
        </div>
        <p>Si vous souhaitez acc\u00e9der aux fonctionnalit\u00e9s Premium, vous pouvez souscrire \u00e0 un abonnement individuel.</p>
        {_button("https://afrikalytics.com/premium", "Voir les offres")}
        {_signature()}
    """)
