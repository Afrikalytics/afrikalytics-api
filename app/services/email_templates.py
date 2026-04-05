"""
Templates HTML centralises pour les emails Afrikalytics.

Chaque fonction retourne une chaine HTML prete a envoyer via send_email().
Toutes les donnees utilisateur sont echappees avec html.escape() pour
prevenir les injections XSS.

Note: Unicode characters are written directly (not as \\uXXXX escapes)
because Python 3.11 f-string parser rejects backslash sequences in
triple-quoted f-strings (fixed in Python 3.12 via PEP 701).
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
    name = escape(full_name)
    return _base_template(
        f"<h2>Bienvenue {name} !</h2>"
        f"<p>Votre compte Afrikalytics a été créé avec succès.</p>"
        "<p><strong>Plan :</strong> Basic (Gratuit)</p>"
        "<hr>"
        "<p>Avec votre compte Basic, vous pouvez :</p>"
        "<ul>"
        "    <li>✅ Participer à toutes nos études</li>"
        "    <li>✅ Voir un aperçu des insights</li>"
        "    <li>✅ Accéder au dashboard basic</li>"
        "</ul>"
        "<p>Pour accéder aux résultats complets, insights détaillés et rapports PDF, "
        "passez à <strong>Premium</strong> !</p>"
        "<hr>"
        '<p><a href="https://dashboard.afrikalytics.com">Accéder à mon dashboard →</a></p>'
        '<p><a href="https://afrikalytics.com/premium">Découvrir les offres Premium →</a></p>'
        f"{_signature()}"
    )


# ---------------------------------------------------------------------------
# Auth - code de verification 2FA
# ---------------------------------------------------------------------------

def verification_code_email(full_name: str, code: str) -> str:
    """Email de code de verification (login 2FA)."""
    name = escape(full_name)
    safe_code = escape(code)
    return _base_template(
        "<h2>Code de vérification</h2>"
        f"<p>Bonjour {name},</p>"
        "<p>Voici votre code de connexion :</p>"
        '<div style="background-color: #f3f4f6; padding: 20px; text-align: center; '
        'margin: 20px 0; border-radius: 8px;">'
        f'    <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; '
        f'color: #1f2937;">{safe_code}</span>'
        "</div>"
        '<p style="color: #666; font-size: 14px;">Ce code expire dans <strong>10 minutes</strong>.</p>'
        '<p style="color: #e74c3c; font-size: 14px;">'
        "Si vous n'avez pas demandé ce code, ignorez cet email.</p>"
        f"{_signature()}"
    )


def resend_verification_code_email(full_name: str, code: str) -> str:
    """Email de renvoi du code de verification."""
    name = escape(full_name)
    safe_code = escape(code)
    return _base_template(
        "<h2>Nouveau code de vérification</h2>"
        f"<p>Bonjour {name},</p>"
        "<p>Voici votre nouveau code de connexion :</p>"
        '<div style="background-color: #f3f4f6; padding: 20px; text-align: center; '
        'margin: 20px 0; border-radius: 8px;">'
        f'    <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; '
        f'color: #1f2937;">{safe_code}</span>'
        "</div>"
        '<p style="color: #666; font-size: 14px;">Ce code expire dans <strong>10 minutes</strong>.</p>'
        f"{_signature()}"
    )


# ---------------------------------------------------------------------------
# Auth - mot de passe
# ---------------------------------------------------------------------------

def forgot_password_email(full_name: str, reset_url: str) -> str:
    """Email de reinitialisation de mot de passe."""
    name = escape(full_name)
    btn = _button(reset_url, "Réinitialiser mon mot de passe")
    return _base_template(
        "<h2>Réinitialisation de mot de passe</h2>"
        f"<p>Bonjour {name},</p>"
        "<p>Vous avez demandé à réinitialiser votre mot de passe Afrikalytics.</p>"
        "<p>Cliquez sur le bouton ci-dessous pour définir un nouveau mot de passe :</p>"
        f"{btn}"
        '<p style="color: #666; font-size: 14px;">Ce lien expire dans <strong>1 heure</strong>.</p>'
        '<p style="color: #666; font-size: 14px;">'
        "Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>"
        f"{_signature()}"
    )


def password_reset_confirmation_email(full_name: str) -> str:
    """Email de confirmation apres reinitialisation du mot de passe."""
    name = escape(full_name)
    btn = _button("https://dashboard.afrikalytics.com/login", "Se connecter")
    return _base_template(
        "<h2>Mot de passe modifié</h2>"
        f"<p>Bonjour {name},</p>"
        "<p>Votre mot de passe Afrikalytics a été réinitialisé avec succès.</p>"
        "<p>Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.</p>"
        f"{btn}"
        '<p style="color: #e74c3c; font-size: 14px;">'
        "Si vous n'êtes pas à l'origine de cette modification, contactez-nous immédiatement.</p>"
        f"{_signature()}"
    )


def password_changed_email(full_name: str) -> str:
    """Email de confirmation apres changement de mot de passe (users/change-password)."""
    name = escape(full_name)
    return _base_template(
        "<h2>Mot de passe modifié</h2>"
        f"<p>Bonjour {name},</p>"
        "<p>Votre mot de passe Afrikalytics a été modifié avec succès.</p>"
        "<p>Si vous n'êtes pas à l'origine de cette modification, contactez-nous immédiatement.</p>"
        f"{_signature()}"
    )


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

def contact_form_email(
    name: str, email: str, company: Optional[str], message: str
) -> str:
    """Notification de nouveau message de contact (envoyee a l'equipe)."""
    company_display = escape(company) if company else "Non renseigné"
    return _base_template(
        "<h2>Nouveau message de contact</h2>"
        f"<p><strong>Nom :</strong> {escape(name)}</p>"
        f"<p><strong>Email :</strong> {escape(email)}</p>"
        f"<p><strong>Entreprise :</strong> {company_display}</p>"
        "<hr>"
        "<p><strong>Message :</strong></p>"
        f"<p>{escape(message)}</p>"
        "<hr>"
        "<p><em>Message envoyé depuis le formulaire de contact Afrikalytics</em></p>"
    )


# ---------------------------------------------------------------------------
# Admin - creation de compte
# ---------------------------------------------------------------------------

def admin_user_created_email(
    full_name: str, email: str, password: str, plan: str
) -> str:
    """Email de bienvenue pour un utilisateur cree par un admin."""
    name = escape(full_name)
    btn = _button("https://dashboard.afrikalytics.com/login", "Se connecter")
    return _base_template(
        "<h2>Bienvenue sur Afrikalytics AI !</h2>"
        f"<p>Bonjour {name},</p>"
        "<p>Votre compte a été créé avec succès.</p>"
        f"<p><strong>Email :</strong> {escape(email)}</p>"
        f"<p><strong>Mot de passe :</strong> {escape(password)}</p>"
        f"<p><strong>Plan :</strong> {escape(plan.capitalize())}</p>"
        f"{btn}"
        '<p style="color: #666;">Nous vous recommandons de changer votre mot de passe '
        "après votre première connexion.</p>"
        f"{_signature()}"
    )


# ---------------------------------------------------------------------------
# Dashboard - rappels d'expiration d'abonnement
# ---------------------------------------------------------------------------

def subscription_reminder_j7_email(full_name: str, plan: str) -> str:
    """Rappel J-7 avant expiration de l'abonnement."""
    name = escape(full_name)
    plan_label = escape(plan.capitalize())
    btn = _button("https://afrikalytics.com/checkout", "Renouveler mon abonnement")
    return _base_template(
        f"<h2>Bonjour {name},</h2>"
        f"<p>Votre abonnement <strong>{plan_label}</strong> expire dans "
        "<strong>7 jours</strong>.</p>"
        "<p>Pour continuer à profiter de tous les avantages Premium :</p>"
        "<ul>"
        "    <li>✅ Résultats en temps réel</li>"
        "    <li>✅ Insights complets</li>"
        "    <li>✅ Rapports PDF détaillés</li>"
        "    <li>✅ Dashboard avancé</li>"
        "</ul>"
        f"{btn}"
        f"{_signature()}"
    )


def subscription_reminder_j3_email(full_name: str, plan: str) -> str:
    """Rappel J-3 avant expiration de l'abonnement."""
    name = escape(full_name)
    plan_label = escape(plan.capitalize())
    btn = _button("https://afrikalytics.com/checkout", "Renouveler maintenant", color="#e74c3c")
    return _base_template(
        f"<h2>Bonjour {name},</h2>"
        f"<p>Votre abonnement <strong>{plan_label}</strong> expire dans "
        "<strong>3 jours</strong>.</p>"
        '<p style="color: #e74c3c; font-weight: bold;">'
        "Sans renouvellement, vous perdrez l'accès aux fonctionnalités Premium.</p>"
        f"{btn}"
        f"{_signature()}"
    )


def subscription_reminder_j0_email(full_name: str, plan: str) -> str:
    """Rappel J-0 : dernier jour de l'abonnement."""
    name = escape(full_name)
    plan_label = escape(plan.capitalize())
    return _base_template(
        f"<h2>Bonjour {name},</h2>"
        '<p style="color: #e74c3c; font-size: 18px; font-weight: bold;">'
        f"Votre abonnement {plan_label} expire AUJOURD'HUI !</p>"
        "<p>Renouvelez maintenant pour ne pas perdre vos accès Premium.</p>"
        '<p style="margin: 30px 0;">'
        '    <a href="https://afrikalytics.com/checkout"'
        '       style="background-color: #e74c3c; color: white; padding: 16px 32px;'
        '              text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">'
        "        RENOUVELER MAINTENANT"
        "    </a>"
        "</p>"
        f"{_signature()}"
    )


def subscription_expired_email(full_name: str, plan: str) -> str:
    """Notification d'expiration de l'abonnement (retrogradation vers Basic)."""
    name = escape(full_name)
    plan_label = escape(plan.capitalize())
    btn = _button("https://afrikalytics.com/checkout", "Réactiver mon abonnement Premium")
    return _base_template(
        f"<h2>Bonjour {name},</h2>"
        f"<p>Votre abonnement <strong>{plan_label}</strong> a expiré.</p>"
        "<p>Votre compte a été rétrogradé au <strong>Plan Basic (gratuit)</strong>.</p>"
        "<p>Vous conservez l'accès à :</p>"
        "<ul>"
        "    <li>✅ Participation aux études</li>"
        "    <li>✅ Aperçu des insights</li>"
        "    <li>✅ Dashboard basic</li>"
        "</ul>"
        "<p>Vous n'avez plus accès à :</p>"
        "<ul>"
        "    <li>❌ Résultats en temps réel</li>"
        "    <li>❌ Insights complets</li>"
        "    <li>❌ Rapports PDF</li>"
        "</ul>"
        f"{btn}"
        f"{_signature()}"
    )


def team_subscription_expired_email(
    member_name: str, owner_name: str
) -> str:
    """Notification aux membres d'equipe quand l'abonnement Entreprise expire."""
    name = escape(member_name)
    owner = escape(owner_name)
    btn = _button("https://afrikalytics.com/premium", "Voir les offres Premium")
    return _base_template(
        f"<h2>Bonjour {name},</h2>"
        f"<p>L'abonnement Entreprise de <strong>{owner}</strong> a expiré.</p>"
        "<p>Votre compte a été rétrogradé au <strong>Plan Basic (gratuit)</strong>.</p>"
        "<p>Vous conservez l'accès à :</p>"
        "<ul>"
        "    <li>✅ Participation aux études</li>"
        "    <li>✅ Aperçu des insights</li>"
        "    <li>✅ Dashboard basic</li>"
        "</ul>"
        "<p>Vous n'avez plus accès aux fonctionnalités Premium.</p>"
        "<p>Si vous souhaitez continuer avec un abonnement individuel :</p>"
        f"{btn}"
        f"{_signature()}"
    )


# ---------------------------------------------------------------------------
# Payments - confirmation de paiement
# ---------------------------------------------------------------------------

def payment_upgrade_email(full_name: str, plan: str) -> str:
    """Email de confirmation de paiement pour un utilisateur existant."""
    name = escape(full_name)
    plan_label = escape(plan.capitalize())
    return _base_template(
        f"<h2>Félicitations {name} !</h2>"
        f"<p>Votre abonnement <strong>{plan_label}</strong> est maintenant actif.</p>"
        "<hr>"
        "<p>Vous avez maintenant accès à :</p>"
        "<ul>"
        "    <li>Résultats en temps réel</li>"
        "    <li>Insights complets</li>"
        "    <li>Rapports PDF détaillés</li>"
        "    <li>Dashboard avancé</li>"
        "    <li>Support prioritaire</li>"
        "</ul>"
        "<hr>"
        '<p><a href="https://dashboard.afrikalytics.com">Accéder à mon dashboard Premium</a></p>'
        f"{_signature()}"
    )


def payment_new_user_email(
    name: str, email: str, temp_password: str, plan: str
) -> str:
    """Email de bienvenue + identifiants pour un nouvel utilisateur apres paiement."""
    safe_name = escape(name or "")
    plan_label = escape(plan.capitalize())
    return _base_template(
        f"<h2>Bienvenue {safe_name} !</h2>"
        f"<p>Votre compte Afrikalytics <strong>{plan_label}</strong> a été créé avec succès.</p>"
        "<hr>"
        "<h3>Vos identifiants de connexion :</h3>"
        f"<p><strong>Email :</strong> {escape(email)}</p>"
        f"<p><strong>Mot de passe temporaire :</strong> {escape(temp_password)}</p>"
        '<p style="color: #e74c3c;"><em>'
        "Pensez à changer votre mot de passe après votre première connexion.</em></p>"
        "<hr>"
        "<p>Vous avez maintenant accès à :</p>"
        "<ul>"
        "    <li>Résultats en temps réel</li>"
        "    <li>Insights complets</li>"
        "    <li>Rapports PDF détaillés</li>"
        "    <li>Dashboard avancé</li>"
        "    <li>Support prioritaire</li>"
        "</ul>"
        "<hr>"
        '<p><a href="https://dashboard.afrikalytics.com/login">Se connecter à mon dashboard</a></p>'
        f"{_signature()}"
    )


# ---------------------------------------------------------------------------
# Enterprise - gestion d'equipe
# ---------------------------------------------------------------------------

def enterprise_team_join_email(
    member_name: str, owner_name: str, old_plan: str
) -> str:
    """Email pour un utilisateur existant qui rejoint une equipe Entreprise."""
    name = escape(member_name)
    owner = escape(owner_name)
    old = escape(old_plan.capitalize())
    pro_notice = (
        '<p style="color: #e74c3c;"><strong>Note :</strong> '
        "Votre abonnement Professionnel a été annulé.</p>"
        if old_plan == "professionnel" else ""
    )
    btn = _button("https://dashboard.afrikalytics.com/login", "Accéder au dashboard")
    return _base_template(
        "<h2>Bonne nouvelle !</h2>"
        f"<p>Bonjour {name},</p>"
        f"<p><strong>{owner}</strong> vous a ajouté(e) à son équipe Entreprise sur Afrikalytics.</p>"
        '<div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">'
        "    <p><strong>Votre nouveau plan :</strong> Entreprise</p>"
        f"    <p><strong>Ancien plan :</strong> {old}</p>"
        f"    {pro_notice}"
        "</div>"
        "<p>Vous pouvez continuer à utiliser votre compte avec vos identifiants habituels.</p>"
        f"{btn}"
        f"{_signature()}"
    )


def enterprise_team_invite_email(
    member_name: str,
    member_email: str,
    owner_name: str,
    temp_password: str,
) -> str:
    """Email d'invitation pour un nouveau membre d'equipe Entreprise."""
    name = escape(member_name)
    owner = escape(owner_name)
    btn = _button("https://dashboard.afrikalytics.com/login", "Se connecter")
    return _base_template(
        "<h2>Bienvenue sur Afrikalytics AI !</h2>"
        f"<p>Bonjour {name},</p>"
        f"<p><strong>{owner}</strong> vous a invité(e) à rejoindre son équipe sur Afrikalytics.</p>"
        '<div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">'
        f"    <p><strong>Email :</strong> {escape(member_email)}</p>"
        f"    <p><strong>Mot de passe temporaire :</strong> {escape(temp_password)}</p>"
        "    <p><strong>Plan :</strong> Entreprise</p>"
        "</div>"
        '<p style="color: #e74c3c;">'
        "Veuillez changer votre mot de passe après votre première connexion.</p>"
        f"{btn}"
        f"{_signature()}"
    )


def enterprise_team_removal_email(
    member_name: str, owner_name: str
) -> str:
    """Email de notification quand un membre est retire de l'equipe Entreprise."""
    name = escape(member_name)
    owner = escape(owner_name)
    btn = _button("https://afrikalytics.com/premium", "Voir les offres")
    return _base_template(
        "<h2>Changement de votre plan</h2>"
        f"<p>Bonjour {name},</p>"
        f"<p>Vous avez été retiré(e) de l'équipe Entreprise de <strong>{owner}</strong> "
        "sur Afrikalytics.</p>"
        '<div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">'
        "    <p><strong>Votre nouveau plan :</strong> Basic (gratuit)</p>"
        "    <p>Votre compte reste actif et vous pouvez toujours vous connecter.</p>"
        "</div>"
        "<p>Si vous souhaitez accéder aux fonctionnalités Premium, vous pouvez "
        "souscrire à un abonnement individuel.</p>"
        f"{btn}"
        f"{_signature()}"
    )
