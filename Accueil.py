# -*- coding: utf-8 -*-
# Tuteur Mathématique IA (Système Éducatif Marocain) - Cleaned & Corrected

import streamlit as st
import requests
import json
import os
import time
import base64
import bcrypt 
from PIL import Image
from io import BytesIO
from datetime import date
from supabase import create_client, Client
from streamlit_cookies_manager import EncryptedCookieManager
from urllib.parse import urlparse, parse_qs

# --- I. Configuration Globale ---

st.set_page_config(
    page_title="Tuteur IA Mathématiques (Système Marocain)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constantes et Secrets
MAX_REQUESTS = 5
REFERRAL_BONUS = 10
REFERRAL_PARAM = "ref_code"
max_retries = 3
COOKIE_KEY_EMAIL = "user_auth_email"
SUPABASE_TABLE_NAME = "users"

# Configuration des API Keys depuis secrets.toml
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SUPABASE_URL: str = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY: str = st.secrets["SUPABASE_KEY"]
    SERVICE_KEY = st.secrets.get("SUPABASE_SERVICE_KEY") # Service key pour les opérations admin/bonus
except KeyError as e:
    st.error(f"Erreur de configuration: Clé manquante dans secrets.toml: {e}. L'application ne démarrera pas correctement.")
    st.stop()
    
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- II. Initialisation des Clients et de l'État ---

# 1. Initialisation des Cookies
cookies = EncryptedCookieManager(
    prefix="gemini_math_app/",
    password=st.secrets.get("COOKIE_PASSWORD", "super_secret_default_key"), # Utilisez un mot de passe fort ici
)
if not cookies.ready():
    st.stop()

# 2. Initialisation Supabase Client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    users_table = supabase.table(SUPABASE_TABLE_NAME)
except Exception as e:
    st.error(f"Erreur d'initialisation Supabase: {e}")
    st.stop()
    
# 3. Initialisation de l'État de la Session
if 'auth_status' not in st.session_state: st.session_state.auth_status = 'logged_out'
if 'user_email' not in st.session_state: st.session_state.user_email = None
if 'user_data' not in st.session_state: st.session_state.user_data = None
if 'requests_today' not in st.session_state: st.session_state.requests_today = 0
if 'is_unlimited' not in st.session_state: st.session_state.is_unlimited = False
if 'should_rerun' not in st.session_state: st.session_state.should_rerun = False


# --- III. Fonctions de Base (Supabase & Crypto) ---

def get_supabase_client(use_service_key: bool = False) -> Client:
    """Retourne le client Supabase standard ou le client avec clé de service."""
    if use_service_key and SERVICE_KEY:
        return create_client(SUPABASE_URL, SERVICE_KEY)
    return supabase

def hash_password(password: str) -> str:
    """Hachage sécurisé du mot de passe avec bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password: str, hashed_password: str) -> bool:
    """Vérifie le mot de passe entré."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_user_by_email(email: str):
    """Récupère les données utilisateur."""
    try:
        response = users_table.select("*").eq("email", email).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Erreur de récupération utilisateur: {e}")
        return None

def update_user_data(email, data: dict, use_service_key=False):
    """Met à jour les données utilisateur."""
    try:
        client_to_use = get_supabase_client(use_service_key)
        response = client_to_use.table(SUPABASE_TABLE_NAME).update(data).eq("email", email).execute()
        
        if response.data and st.session_state.user_email == email:
            # Mise à jour de la session si l'utilisateur actuel est modifié
            st.session_state.user_data.update(response.data[0])
            return True
        return False
    except Exception as e:
        print(f"Erreur de mise à jour Supabase: {e}")
        return False


# --- IV. Logique de l'API Gemini ---

def get_image_part(uploaded_file):
    """Crée la partie 'inlineData' pour l'API Gemini."""
    if uploaded_file is None:
        return None
        
    bytes_data = uploaded_file.getvalue()
    mime_type = uploaded_file.type
    
    # Validation du format (même si Streamlit filtre, c'est une bonne pratique)
    if mime_type not in ["image/png", "image/jpeg", "image/jpg"]:
        st.warning("تنسيق صورة غير مدعوم. نرجو استخدام JPG أو PNG.")
        return None
            
    base64_encoded_data = base64.b64encode(bytes_data).decode('utf-8')
    return {
        "inlineData": {
            "data": base64_encoded_data,
            "mimeType": mime_type
        }
    }

def build_system_prompt():
    """Construit la System Instruction complète, en évitant les formats risqués."""
    user_data = st.session_state.user_data
    school_level = user_data.get('school_level', 'Tronc Commun')
    response_type = user_data.get('response_type', 'steps')
    lang = user_data.get('lang', 'fr')

    # Base: Spécialisation et niveau
    base_prompt = (
        f"Tu es un tuteur spécialisé en mathématiques, expert du système éducatif marocain (niveau {school_level}). "
        "Ta mission est de fournir une assistance précise et didactique. Si une image est fournie, tu dois l'analyser et résoudre le problème."
    )
    
    # Style de réponse (sans formatage Markdown ici)
    if response_type == 'answer':
        style_instruction = "Fournis uniquement la réponse finale et concise du problème, sans aucune explication détaillée ni étapes intermédiaires."
    elif response_type == 'concept':
        style_instruction = "Fournis une explication conceptuelle approfondie du problème ou du sujet, et concentre-toi sur les théories et les concepts impliqués."
    else: # 'steps' par défaut
        style_instruction = "Fournis les étapes détaillées de résolution de manière structurée et méthodique pour aider l'étudiant à suivre le raisonnement."

    # Langue
    lang_instruction = "Tu dois répondre exclusivement en français." if lang == 'fr' else "Tu dois répondre exclusivement en français، en utilisant les termes mathématiques usuels."

    # Instruction finale (demander Markdown/LaTeX pour la sortie)
    final_prompt = (
        f"{base_prompt} {lang_instruction} {style_instruction} "
        "Utilise le format Markdown pour organiser ta réponse, et assure-toi que les formules mathématiques sont formatées en LaTeX."
    )
    return final_prompt

@st.cache_resource
def stream_text_simulation(text):
    """Simule la frappe de texte pour une meilleure UX."""
    for chunk in text.split():
        yield chunk + " "
        time.sleep(0.02)

def call_gemini_api(prompt: str, image_part=None):
    """Appelle l'API Gemini avec gestion des limites et des erreurs."""
    
    email = st.session_state.user_email
    user_data = st.session_state.user_data
    current_date_str = str(date.today())
    
    # 1. Vérification des Limites
    max_total_requests = MAX_REQUESTS + user_data.get('bonus_questions', 0)
    if not user_data.get('is_unlimited', False):
        
        # Réinitialisation du compteur si la date a changé
        if user_data.get('last_request_date') != current_date_str:
            st.session_state.requests_today = 0
            # Mise à jour immédiate de la DB (pas critique de l'attendre)
            update_user_data(email, {'requests_today': 0, 'last_request_date': current_date_str})

        current_count = st.session_state.requests_today

        if current_count >= max_total_requests:
            st.error(f"Limite atteinte: Vous avez atteint le maximum de requêtes ({max_total_requests}) pour aujourd'hui. Revenez demain!")
            return "Limite de requêtes atteinte.", []
            
        st.session_state.requests_today = current_count + 1 # Incrémenter avant l'appel

    # 2. Construction du Payload
    final_system_prompt = build_system_prompt()
    
    contents_parts = []
    if image_part: contents_parts.append(image_part)
    if prompt: contents_parts.append({"text": prompt})
        
    if not contents_parts:
        return "Veuillez fournir une question ou une image.", []

    payload = {
        "contents": [{"parts": contents_parts}],
        "tools": [{"google_search": {} }],
        "config": {
            "systemInstruction": final_system_prompt,
        }
    }

    headers = { 'Content-Type': 'application/json' }

    # 3. Mécanisme de Ré-essai (Retry Loop)
    for attempt in range(max_retries):
        try:
            full_url = f"{API_URL}?key={API_KEY}"
            response = requests.post(full_url, headers=headers, data=json.dumps(payload))
            response.raise_for_status() # Lève une erreur pour les codes 4XX/5XX
            
            result = response.json()
            
            # Mise à jour du compteur dans Supabase APRES succès (si non illimité)
            if not user_data.get('is_unlimited', False):
                update_user_data(email, {'requests_today': st.session_state.requests_today, 'last_request_date': current_date_str})
                
            # Extraction de la réponse et des sources
            candidate = result.get('candidates', [None])[0]
            if candidate and candidate.get('content') and candidate['content'].get('parts'):
                generated_text = candidate['content']['parts'][0].get('text', "Aucun texte trouvé.")
                
                sources = []
                grounding_metadata = candidate.get('groundingMetadata')
                if grounding_metadata and grounding_metadata.get('groundingAttributions'):
                    sources = [
                        {'uri': attr.get('web', {}).get('uri'), 'title': attr.get('web', {}).get('title')}
                        for attr in grounding_metadata['groundingAttributions']
                        if attr.get('web', {}).get('title')
                    ]
                
                return generated_text, sources
            else:
                return "Désolé, le modèle n'a pas pu fournir de réponse. Veuillez réessayer.", []

        except requests.exceptions.HTTPError as e:
            error_details = response.text
            # Diagnostic spécifique de l'erreur 400
            if response.status_code == 400 and 'system_instruction' in error_details:
                 st.error("❌ **Erreur d'Argument (Code 400)**: La 'System Instruction' est invalide (longueur ou format non supporté par l'API). **Veuillez contacter le développeur.**")
                 return f"Échec final (Code 400). Cause probable: systemInstruction non valide.", []
                 
            st.error(f"Échec de la connexion (Tentative {attempt + 1}/{max_retries}, Code {response.status_code}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            
            return f"Échec final de la connexion (Code {response.status_code}). Vérifiez la clé API ou l'erreur du serveur.", []

        except requests.exceptions.RequestException as e:
            st.error(f"Erreur réseau (Tentative {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return f"Échec de la connexion après {max_retries} tentatives.", []
            
        except Exception as e:
            return f"خطأ غير متوقع: {e}", []
    
    return "فشل توليد الإجابة.", []


# --- V. Fonctions d'Authentification et de Session ---

def load_user_session(email, save_cookie=False):
    """Charge les données utilisateur et met à jour la session."""
    user_data = get_user_by_email(email)
    
    if user_data:
        if save_cookie:
            cookies[COOKIE_KEY_EMAIL] = email
            cookies.save()
            
        st.session_state.user_email = email
        st.session_state.user_data = user_data
        
        # Chargement des préférences utilisateur
        st.session_state.is_unlimited = user_data.get('is_unlimited', False)
        
        # Gestion du compteur quotidien (pour la vérification immédiate)
        current_date_str = str(date.today())
        if user_data.get('last_request_date') != current_date_str:
            st.session_state.requests_today = 0
        else:
            st.session_state.requests_today = user_data.get('requests_today', 0)
            
        st.session_state.auth_status = 'logged_in'
        st.session_state.should_rerun = True
        return True
    return False

def handle_login():
    """Gère la connexion."""
    email = st.session_state.login_email.lower()
    password = st.session_state.login_password
    
    user_data = get_user_by_email(email)
    
    if user_data and check_password(password, user_data.get('password_hash', '')):
        st.success("Connexion réussie! Bienvenue.")
        load_user_session(email, save_cookie=True)
    else:
        st.error("E-mail ou mot de passe incorrect.")

def handle_register():
    """Gère l'inscription et le parrainage."""
    email = st.session_state.reg_email.lower()
    password = st.session_state.reg_password
    confirm_password = st.session_state.reg_password_confirm
    
    if password != confirm_password:
        st.error("Les mots de passe ne correspondent pas.")
        return
    if len(password) < 6:
        st.error("Le mot de passe doit contenir au moins 6 caractères.")
        return
        
    if get_user_by_email(email):
        st.error("Cet e-mail est déjà enregistré. Veuillez vous connecter.")
        return

    # Logique de Parrainage
    referrer_email = None
    query_params = st.query_params
    
    if REFERRAL_PARAM in query_params:
        potential_referrer_email = query_params[REFERRAL_PARAM]
        if isinstance(potential_referrer_email, list): potential_referrer_email = potential_referrer_email[0]
            
        referrer_data = get_user_by_email(potential_referrer_email)
        if referrer_data and referrer_data['email'] != email: # Éviter l'auto-parrainage
            referrer_email = potential_referrer_email
            current_bonus = referrer_data.get('bonus_questions', 0)
            new_bonus = current_bonus + REFERRAL_BONUS
            
            # Utilisation de la clé de service pour l'opération d'écriture (plus sûr)
            if update_user_data(referrer_email, {'bonus_questions': new_bonus}, use_service_key=True):
                 st.info(f"Félicitations! Le parrain ({referrer_email}) a reçu {REFERRAL_BONUS} questions bonus.")
            
    # Sauvegarder le nouvel utilisateur
    new_user_data = {
        'email': email,
        'password_hash': hash_password(password),
        'lang': 'fr', 
        'response_type': 'steps', 
        'school_level': 'Classes Préparatoires', # Niveau par défaut plus pertinent pour un tuteur avancé
        'is_unlimited': False,
        'requests_today': 0,
        'last_request_date': str(date.today()),
        'bonus_questions': 0,
        'referred_by': referrer_email,
    }
    
    try:
        users_table.insert([new_user_data]).execute()
        st.success("Inscription et connexion réussies! 🥳")
        load_user_session(email, save_cookie=True)
    except Exception as e:
        st.error(f"Échec de l'inscription: {e}. (Vérifiez les règles RLS de Supabase.)")


# --- VI. Interface Utilisateur (UI) ---

def auth_ui():
    """Interface de connexion/inscription."""
    st.header("🔑 Connexion / Inscription")
    st.markdown("---")

    col1, col2 = st.columns(2)
    
    with col1:
        with st.form("login_form"):
            st.subheader("Se Connecter")
            st.text_input("E-mail", key="login_email")
            st.text_input("Mot de passe", type="password", key="login_password")
            st.form_submit_button("Connexion", type="primary", on_click=handle_login)

    with col2:
        with st.form("register_form"):
            st.subheader("S'inscrire")
            st.text_input("E-mail", key="reg_email")
            st.text_input("Mot de passe", type="password", key="reg_password")
            st.text_input("Confirmer le mot de passe", type="password", key="reg_password_confirm")
            
            st.subheader("Vos Préférences par Défaut")
            st.caption("Compte configuré par défaut: **Français** (Étapes détaillées, niveau **Classes Préparatoires**).")

            query_params = st.query_params
            if REFERRAL_PARAM in query_params:
                ref_email = query_params.get(REFERRAL_PARAM)
                if isinstance(ref_email, list): ref_email = ref_email[0]
                st.info(f"Vous vous inscrivez via le lien de parrainage ({ref_email}). Votre parrain recevra un bonus!")

            st.form_submit_button("S'inscrire", type="secondary", on_click=handle_register)


def main_app_ui():
    """Interface principale de l'application (pour les utilisateurs connectés)."""
    
    st.title("💡 Tuteur Mathématique Spécialisé (نظام المغرب)")
    st.markdown("---")

    st.markdown("أنا **مساعدك الذكي المتخصص**، جاهز لمساعدتك. يمكنك طرح سؤال أو **تحميل صورة** للتمرين.")

    col_upload, col_prompt = st.columns([1, 2])
    
    with col_upload:
        uploaded_file = st.file_uploader(
            "Optionnel : Téléchargez une photo (JPG / PNG, max 4 Mo).",
            type=["png", "jpg", "jpeg"],
            key="image_uploader"
        )
        image_part_to_send = get_image_part(uploaded_file)
        if uploaded_file and image_part_to_send:
            try:
                image = Image.open(BytesIO(uploaded_file.getvalue()))
                st.image(image, caption='Image téléchargée.', use_column_width=True)
            except Exception:
                st.error("Erreur lors du chargement de l'image.")
    
    with col_prompt:
        user_prompt = st.text_area(
            "Ajoutez votre question ou votre instruction ici.",
            height=250,
            key="prompt_input"
        )
        
        if st.button("Générer la Réponse Mathématique", use_container_width=True, type="primary"):
            if not user_prompt and not uploaded_file:
                st.warning("Veuillez entrer une question ou télécharger une image pour commencer.")
            elif uploaded_file and image_part_to_send is None:
                st.error("تعذّر معالجة الصورة. تأكد من أن التنسيق هو JPG أو PNG.")
            else:
                with st.spinner('L\'IA analyse et prépare la réponse...'):
                    generated_text, sources = call_gemini_api(user_prompt, image_part_to_send)
                
                st.subheader("✅ Réponse Générée :")
                
                if generated_text and "Limite de requêtes atteinte" not in generated_text and "Échec final" not in generated_text:
                    st.write_stream(stream_text_simulation(generated_text))
                    
                    if sources:
                        st.subheader("🌐 Sources Citées :")
                        # Utilisation d'un set pour les sources uniques
                        unique_sources = set((s['title'], s['uri']) for s in sources if s['uri'] and s['title'])
                        source_markdown = "\n".join([f"- [{title}]({uri})" for title, uri in unique_sources])
                        st.markdown(source_markdown)
                    else:
                        st.caption("Aucune source de recherche externe n'a été utilisée pour cette réponse.")
                else:
                    st.markdown(generated_text) # Affiche les messages d'erreur détaillés

    # Sidebar
    max_total_requests = MAX_REQUESTS + st.session_state.user_data.get('bonus_questions', 0)
    requests_left = max_total_requests - st.session_state.requests_today

    st.sidebar.header(f"Statut : {st.session_state.user_email}")
    st.sidebar.markdown(f"**Niveau Actuel:** {st.session_state.user_data.get('school_level', 'Non Défini')}")
    st.sidebar.markdown(f"**Bonus Affiliation:** {st.session_state.user_data.get('bonus_questions', 0)} questions")

    if st.session_state.is_unlimited:
        status_message = "✅ **Utilisation Illimitée (VIP)**"
        color = "#28a745"
    else:
        status_message = f"Requêtes restantes aujourd'hui: **{requests_left}** / {max_total_requests}"
        color = "#007bff" if requests_left > 0 else "#dc3545"

    st.sidebar.markdown(f"""
    <div style='background-color:#e9ecef; padding:10px; border-radius:5px; text-align:center; border-left: 5px solid {color};'>
        <span style='font-weight: bold; color: {color};'>{status_message}</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Déconnexion 🚪"):
        cookies[COOKIE_KEY_EMAIL] = ""
        cookies.save()
        st.session_state.auth_status = 'logged_out'
        st.session_state.should_rerun = True


# --- VII. Contrôle du Flux Principal ---

# 1. Vérification du Cookie au démarrage (Tentative d'auto-connexion)
if st.session_state.auth_status == 'logged_out':
    remembered_email = cookies.get(COOKIE_KEY_EMAIL)
    if remembered_email:
        load_user_session(remembered_email) # load_user_session met should_rerun à True si succès
        
# 2. Affichage de l'UI
if st.session_state.auth_status == 'logged_out':
    auth_ui()
else:
    main_app_ui()

# 3. Traitement de l'auto-rerun (Une seule fois après l'auth)
if st.session_state.should_rerun:
    st.session_state.should_rerun = False
    st.rerun() # Redémarrage pour mettre à jour la session
