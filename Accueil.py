# -*- coding: utf-8 -*-
# Tuteur Mathématique IA (Système Éducatif Marocain)

import streamlit as st
import requests
import json
import os
import time
import base64
import bcrypt 
from PIL import Image
from io import BytesIO
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs

# *** Librairies Nécessaire ***
from supabase import create_client, Client
from streamlit_cookies_manager import EncryptedCookieManager

# --- Configuration et Paramètres de l'Application ---

st.set_page_config(
    page_title="Tuteur IA Mathématiques (Système Marocain)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 1. Initialisation des Cookies ---
cookies = EncryptedCookieManager(
    prefix="gemini_math_app/",
    password=st.secrets.get("COOKIE_PASSWORD", "super_secret_default_key"),
)
if not cookies.ready():
    st.stop()
# -----------------------------------------------------------------

# Constantes et Secrets
MAX_REQUESTS = 5
REFERRAL_BONUS = 10 # 10 questions en plus pour l'affilie
REFERRAL_PARAM = "ref_code"
ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL", "admin@example.com")
max_retries = 3
COOKIE_KEY_EMAIL = "user_auth_email"
SUPABASE_TABLE_NAME = "users"

# Configuration de la cle API
API_KEY = st.secrets.get("GEMINI_API_KEY", "PLACEHOLDER_FOR_API_KEY")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- 2. Initialisation Supabase Client ---
try:
    supabase_url: str = st.secrets["SUPABASE_URL"]
    supabase_key: str = st.secrets["SUPABASE_KEY"]
    
    supabase: Client = create_client(supabase_url, supabase_key)
    users_table = supabase.table(SUPABASE_TABLE_NAME)
except KeyError:
    st.error("Erreur de configuration: Veuillez ajouter les cles Supabase (URL, KEY) dans `secrets.toml`.")
    st.stop()
except Exception as e:
    st.error(f"Erreur d'initialisation Supabase: {e}")
    st.stop()
    
# --- Initialisation de l'Etat de la Session ---
if 'auth_status' not in st.session_state: st.session_state.auth_status = 'logged_out'
if 'user_email' not in st.session_state: st.session_state.user_email = None
if 'user_data' not in st.session_state: st.session_state.user_data = None
# Valeur par defaut mise a jour pour correspondre au selectbox
if 'user_lang' not in st.session_state: st.session_state.user_lang = 'Francais' 
if 'response_type' not in st.session_state: st.session_state.response_type = 'steps'
if 'school_level' not in st.session_state: st.session_state.school_level = 'Tronc Commun'
if 'requests_today' not in st.session_state: st.session_state.requests_today = 0
if 'is_unlimited' not in st.session_state: st.session_state.is_unlimited = False
if 'should_rerun' not in st.session_state: st.session_state.should_rerun = False 

# --- Fonctions Supabase Partagees ---

def hash_password(password: str) -> str:
    """Hachage securise du mot de passe avec bcrypt."""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def check_password(password: str, hashed_password: str) -> bool:
    """Verifie le mot de passe entre par rapport au hachage stocke."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_user_by_email(email: str):
    """Recupere les donnees utilisateur depuis Supabase."""
    try:
        response = users_table.select("*").eq("email", email).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Erreur de recuperation utilisateur: {e}")
        return None

def update_user_data(email, data: dict, use_service_key=False):
    """Met a jour les donnees utilisateur dans Supabase."""
    client_to_use = supabase
    try:
        if use_service_key:
            # Necessite SUPABASE_SERVICE_KEY dans secrets.toml
            service_key = st.secrets["SUPABASE_SERVICE_KEY"]
            client_to_use = create_client(supabase_url, service_key)
            
        response = client_to_use.table(SUPABASE_TABLE_NAME).update(data).eq("email", email).execute()
        
        if response.data:
            if st.session_state.user_data and st.session_state.user_email == email:
                # Mise a jour de l'etat de session si l'utilisateur courant est mis a jour
                st.session_state.user_data.update(response.data[0]) 
            return True
        return False
    except KeyError:
        st.error("Erreur: Cle de service Supabase manquante pour l'operation administrateur.")
        return False
    except Exception as e:
        print(f"Erreur de mise a jour Supabase pour {email}: {e}")
        return False

# --- Fonctions Auxiliaires (Helper Functions) ---

def get_image_part(uploaded_file):
    """
    Cree la partie 'inlineData' pour l'API Gemini.
    """
    if uploaded_file is not None:
        bytes_data = uploaded_file.getvalue()
        mime_type = uploaded_file.type
        
        # Verification du type MIME supporte
        if mime_type not in ["image/png", "image/jpeg", "image/jpg"]:
            if uploaded_file.name.lower().endswith('.png'):
                mime_type = "image/png"
            elif uploaded_file.name.lower().endswith(('.jpg', '.jpeg')):
                mime_type = "image/jpeg"
            else:
                st.warning("Format d'image non supporte. Veuillez utiliser JPG ou PNG.")
                return None
                
        base64_encoded_data = base64.b64encode(bytes_data).decode('utf-8')
        
        return {
            "inlineData": {
                "data": base64_encoded_data,
                "mimeType": mime_type 
            }
        }
    return None

def stream_text_simulation(text):
    for chunk in text.split():
        yield chunk + " "
        time.sleep(0.02)

# --- Fonction Principale: Appel API ---

def call_gemini_api(prompt, image_part=None):
    
    if API_KEY == "PLACEHOLDER_FOR_API_KEY" or not API_KEY:
        st.error("Erreur de configuration : Veuillez ajouter la cle GEMINI_API_KEY.")
        return "Veuillez fournir une cle API valide.", []

    email = st.session_state.user_email
    user_data = st.session_state.user_data
    current_date_str = str(date.today())
    
    # 1. Application de la Limite de Requetes
    max_total_requests = MAX_REQUESTS + user_data.get('bonus_questions', 0)
    
    if not user_data.get('is_unlimited', False):
        
        if user_data.get('last_request_date') != current_date_str:
            st.session_state.requests_today = 0
            user_data['requests_today'] = 0
            user_data['last_request_date'] = current_date_str
            update_user_data(email, {'requests_today': 0, 'last_request_date': current_date_str})

        current_count = st.session_state.requests_today

        if current_count >= max_total_requests:
            st.error(f"Limite atteinte : Vous avez atteint le maximum de requetes ({max_total_requests}) pour aujourd'hui. Revenez demain ou consultez la page 'Affiliation' pour gagner plus de requetes.")
            return "Limite de requetes atteinte.", []
            
        st.session_state.requests_today = current_count + 1

    # Construction des instructions pour le modele
    lang_choice = user_data.get('lang', 'Francais')
    response_type = user_data.get('response_type', 'steps')
    school_level_raw = user_data.get('school_level', 'Tronc Commun')
    
    # Nettoyage des parentheses/accents dans le niveau scolaire pour plus de surete dans le System Prompt
    school_level_safe = school_level_raw.replace('(', '').replace(')', '').replace('è', 'e').replace('é', 'e').replace('É', 'E').replace('à', 'a').replace('À', 'A')

    # --- DEFINITION DES PROMPTS EN FONCTION DE LA LANGUE CHOISIE ---
    
    if lang_choice == 'Francais':
        # Prompt systeme en FR (nettoye des accents dans la partie statique pour le 400 ERROR)
        system_prompt_base = f"Tu es un tuteur specialise en mathematiques, expert du systeme educatif marocain (niveau {school_level_safe}). Ta mission est de fournir une assistance precise et didactique. Si une image est fournie, tu dois l'analyser et resoudre le probleme."
        lang_instruction = "Tu dois repondre exclusivement en francais, en utilisant les termes mathematiques usuels."
        
        if response_type == 'answer':
            style_instruction = "Fournis uniquement la reponse finale et concise du probleme, sans aucune explication detaillee ni etapes intermediaires."
        elif response_type == 'steps':
            style_instruction = "Fournis les etapes detaillees de resolution de maniere structuree et methodique pour aider l'etudiant a suivre le raisonnement."
        else:
            style_instruction = "Fournis une explication conceptuelle approfondie du probleme ou du sujet, et concentre-toi sur les theories et les concepts impliques."
            
    else: # Anglais
        # Prompt systeme en EN (ASCII-safe)
        system_prompt_base = f"You are a specialized mathematics tutor, expert in the Moroccan educational system (level {school_level_safe}). Your mission is to provide accurate and didactic assistance. If an image is provided, you must analyze it and solve the problem."
        lang_instruction = "You must answer exclusively in English, using standard mathematical terminology."
        
        if response_type == 'answer':
            style_instruction = "Provide only the final, concise answer to the problem, without any detailed explanation or intermediate steps."
        elif response_type == 'steps':
            style_instruction = "Provide detailed, structured, and methodical resolution steps to help the student follow the reasoning."
        else:
            style_instruction = "Provide a deep conceptual explanation of the problem or subject, focusing on the theories and concepts involved."

    # L'instruction finale est la concatenation de toutes les parties
    final_system_prompt = f"{system_prompt_base} {lang_instruction} {style_instruction} Use Markdown format to organize your response, and ensure that mathematical formulas are formatted in LaTeX."

    contents_parts = []
    if image_part: contents_parts.append(image_part)
    if prompt: contents_parts.append({"text": prompt})
        
    if not contents_parts:
        return "Veuillez fournir une question ou une image.", []

    payload = {
        "contents": [{"parts": contents_parts}],
        "tools": [{"google_search": {} }],
        "systemInstruction": final_system_prompt,
    }

    headers = { 'Content-Type': 'application/json' } 
    
    # On utilise json.dumps avec ensure_ascii=False pour l'encodage UTF-8 explicite
    json_data = json.dumps(payload, ensure_ascii=False).encode('utf8')

    # Mecanisme de Re-essai (Retry)
    for attempt in range(max_retries):
        try:
            full_url = f"{API_URL}?key={API_KEY}"
            
            # On envoie les donnees comme bytes encode en utf8
            response = requests.post(full_url, headers=headers, data=json_data)
            
            response.raise_for_status() 
            
            # Si le code arrive ici, la requete a reussi (code 200)
            result = response.json()
            
            # Mise a jour du compteur dans Supabase
            if not user_data.get('is_unlimited', False):
                update_user_data(email, {'requests_today': st.session_state.requests_today, 'last_request_date': current_date_str})
                
            candidate = result.get('candidates', [None])[0]
            
            if candidate and candidate.get('content') and candidate['content'].get('parts'):
                generated_text = candidate['content']['parts'][0].get('text', "Aucun texte trouve.")
                
                sources = []
                grounding_metadata = candidate.get('groundingMetadata')
                if grounding_metadata and grounding_metadata.get('groundingAttributions'):
                    sources = [
                        { 'uri': attr.get('web', {}).get('uri'), 'title': attr.get('web', {}).get('title'),}
                        for attr in grounding_metadata['groundingAttributions']
                        if attr.get('web', {}).get('title')
                    ]
                
                return generated_text, sources
            else:
                return "Desole, le modele n'a pas pu fournir de reponse. Veuillez reessayer avec une autre requete.", []

        except requests.exceptions.HTTPError as e:
            # Traiter les erreurs 4XX et 5XX. Important pour le 400.
            error_details = response.text
            print(f"API Error Details: {error_details}") 
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            
            # Retourner l'erreur apres la derniere tentative
            return f"Echec final de la connexion (Code {response.status_code}). Veuillez verifier la validite de votre cle API dans `secrets.toml` ou le format de l'image si elle a ete telechargee. Details du serveur: {error_details}", []

        except requests.exceptions.RequestException as e:
            # Traiter les erreurs de reseau (DNS, timeout, etc.)
            st.error(f"Erreur reseau (Tentative {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return f"Echec de la connexion apres {max_retries} tentatives: {e}.", []
        except Exception as e:
            return f"Erreur inattendue: {e}", []
    
    return "Echec de la generation de la reponse.", []

# --- Fonctions d'Authentification ---

def load_user_session(email, save_cookie=False):
    user_data = get_user_by_email(email)
    
    if user_data:
        if save_cookie:
            cookies[COOKIE_KEY_EMAIL] = email
            cookies.save()
            
        st.session_state.user_email = email
        st.session_state.user_data = user_data
        # تحميل القيم من قاعدة البيانات 
        st.session_state.user_lang = user_data.get('lang', 'Francais') # Mise a jour: 'fr' -> 'Francais'
        st.session_state.response_type = user_data.get('response_type', 'steps')
        st.session_state.school_level = user_data.get('school_level', 'Tronc Commun')
        st.session_state.is_unlimited = user_data.get('is_unlimited', False)
        
        current_date_str = str(date.today())
        
        # Gestion du compteur quotidien
        if user_data.get('last_request_date') != current_date_str:
            st.session_state.requests_today = 0
        else:
            st.session_state.requests_today = user_data.get('requests_today', 0)
            
        st.session_state.auth_status = 'logged_in'
        st.session_state.should_rerun = True 
        return True
    return False


def handle_login():
    """Traite la connexion et la verification du mot de passe."""
    email = st.session_state.login_email.lower()
    password = st.session_state.login_password
    
    user_data = get_user_by_email(email)
    
    if user_data and check_password(password, user_data.get('password_hash', '')):
        st.success("Connexion reussie! Bienvenue.")
        load_user_session(email, save_cookie=True)
    else:
        st.error("E-mail ou mot de passe incorrect.")

def handle_register():
    """Traite l'inscription, verifie le code de parrainage et accorde la recompense."""
    email = st.session_state.reg_email.lower()
    password = st.session_state.reg_password
    confirm_password = st.session_state.reg_password_confirm
    
    if password != confirm_password:
        st.error("Les mots de passe ne correspondent pas.")
        return
    if len(password) < 6:
        st.error("Le mot de passe doit contenir au moins 6 caracteres.")
        return
        
    if get_user_by_email(email):
        st.error("Cet e-mail est deja enregistre. Veuillez vous connecter.")
        return

    # --- LOGIQUE DE PARRAINAGE ---
    referrer_email = None
    query_params = st.query_params
    
    if REFERRAL_PARAM in query_params:
        potential_referrer_email = query_params[REFERRAL_PARAM]
        if isinstance(potential_referrer_email, list):
            potential_referrer_email = potential_referrer_email[0]  
            
        referrer_data = get_user_by_email(potential_referrer_email)
        if referrer_data:
            referrer_email = potential_referrer_email
            current_bonus = referrer_data.get('bonus_questions', 0)
            new_bonus = current_bonus + REFERRAL_BONUS
            
            if update_user_data(referrer_email, {'bonus_questions': new_bonus}, use_service_key=True):
                 st.info(f"Felicitations! Le parrain ({referrer_email}) a recu {REFERRAL_BONUS} questions bonus.")
            
    # Sauvegarder le nouvel utilisateur
    new_user_data = {
        'email': email,
        'password_hash': hash_password(password),
        # VALEURS الافتراضية الثابتة 
        'lang': 'Francais', # Mise a jour: 'fr' -> 'Francais'
        'response_type': 'steps', 
        'school_level': 'Tronc Commun',
        'is_unlimited': False,
        'requests_today': 0,
        'last_request_date': str(date.today()),
        'bonus_questions': 0, 
        'referred_by': referrer_email, 
    }
    
    try:
        users_table.insert([new_user_data]).execute()
        st.success("Inscription et connexion reussies! 🥳")
        load_user_session(email, save_cookie=True)
    except Exception as e:
        st.error(f"Echec de l'inscription: {e}. (Verifiez les regles RLS de Supabase.)")

# --- UI d'Authentification ---

def auth_ui():
    st.header("Connexion / Inscription")
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
            
            st.subheader("Vos Preferences par Defaut")
            st.caption("Votre compte sera configure par defaut sur: **Francais** (Reponse par **etapes detaillees**, et Niveau Scolaire **Tronc Commun**).")

            query_params = st.query_params
            if REFERRAL_PARAM in query_params:
                ref_email = query_params[REFERRAL_PARAM]
                if isinstance(ref_email, list): ref_email = ref_email[0]
                st.info(f"Vous vous inscrivez via le lien de parrainage ({ref_email}). Votre parrain recevra un bonus!")

            st.form_submit_button("S'inscrire", type="secondary", on_click=handle_register)


# --- Fonctions de mise a jour du profil ---

def update_profile_settings():
    """Met a jour les parametres utilisateur dans la base de donnees et la session."""
    email = st.session_state.user_email
    
    # Mettre a jour l'etat de session
    st.session_state.user_lang = st.session_state.settings_lang
    st.session_state.response_type = st.session_state.settings_response_type
    st.session_state.school_level = st.session_state.settings_school_level
    
    # Mettre a jour la base de donnees
    data_to_update = {
        'lang': st.session_state.settings_lang,
        'response_type': st.session_state.settings_response_type,
        'school_level': st.session_state.settings_school_level
    }
    
    if update_user_data(email, data_to_update):
        st.success("Parametres mis a jour avec succes! Veuillez recharger la page si necessaire.")
    else:
        st.error("Echec de la mise a jour des parametres.")

# --- UI du Profil et des Parametres ---

def profile_ui():
    st.sidebar.header("⚙️ Parametres Utilisateur")
    
    current_data = st.session_state.user_data
    
    # Correction: Normaliser la valeur de la langue pour la selectbox
    # Cela يسمح بـ gerer les anciennes valeurs stockees (ex: 'fr' au lieu de 'Francais')
    db_lang = current_data.get('lang', 'Francais')
    lang_options = ['Francais', 'Anglais']
    
    if db_lang not in lang_options:
        safe_lang = 'Francais' # Default to Francais if the value is corrupted or legacy ('fr')
    else:
        safe_lang = db_lang

    # Selectbox de la langue de reponse (AI)
    st.sidebar.subheader("Langue de Reponse de l'AI")
    st.sidebar.selectbox(
        "Choisissez la langue des reponses mathematiques:",
        options=lang_options,
        key='settings_lang',
        index=lang_options.index(safe_lang) # Use the safe_lang
    )

    # Selectbox du type de reponse
    st.sidebar.subheader("Format de Reponse")
    response_type_options = {
        'steps': 'Étapes détaillées et méthodiques',
        'conceptual': 'Explication conceptuelle (Théorie et Concepts)',
        'answer': 'Réponse finale concise uniquement'
    }
    st.sidebar.selectbox(
        "Choisissez le style de resolution de l'AI:",
        options=list(response_type_options.keys()),
        format_func=lambda x: response_type_options[x],
        key='settings_response_type',
        index=list(response_type_options.keys()).index(current_data.get('response_type', 'steps'))
    )

    # Selectbox du niveau scolaire
    st.sidebar.subheader("Niveau Scolaire Marocain")
    school_levels = [
        'Tronc Commun', '1ère Année Bac (Sciences)', '2ème Année Bac (Sciences Physiques)',
        '2ème Année Bac (Sciences Mathématiques)', 'Ecoles Supérieures/Classes Préparatoires'
    ]
    st.sidebar.selectbox(
        "Choisissez votre niveau scolaire:",
        options=school_levels,
        key='settings_school_level',
        index=school_levels.index(current_data.get('school_level', 'Tronc Commun'))
    )
    
    # Bouton de sauvegarde des parametres
    st.sidebar.button("Sauvegarder les Parametres", type="primary", on_click=update_profile_settings)

    st.sidebar.markdown("---")

    # Informations sur l'utilisateur et le quota
    st.sidebar.header("Mon Quota")
    
    is_unlimited = current_data.get('is_unlimited', False)
    requests_used = st.session_state.requests_today
    max_total_requests = MAX_REQUESTS + current_data.get('bonus_questions', 0)
    
    st.sidebar.write(f"**Utilisateur:** {st.session_state.user_email}")
    
    if is_unlimited:
        st.sidebar.success("Accès ILLIMITÉ (Compte Premium)")
    else:
        st.sidebar.write(f"**Bonus questions:** {current_data.get('bonus_questions', 0)}")
        st.sidebar.write(f"**Quota journalier:** {requests_used} / {max_total_requests}")
        if requests_used >= max_total_requests:
            st.sidebar.error("Limite atteinte pour aujourd'hui.")

    st.sidebar.markdown("---")
    # Section Affiliation
    st.sidebar.header("🚀 Affiliation")
    referral_link = f"{st.get_option('server.baseUrl')}?{REFERRAL_PARAM}={st.session_state.user_email}"
    st.sidebar.caption("Partagez ce lien pour gagner 10 questions bonus!")
    st.sidebar.code(referral_link)
    
    # Bouton de deconnexion
    st.sidebar.button("Deconnexion", on_click=handle_logout)

def handle_logout():
    """Efface la session et les cookies, puis relance l'application."""
    if COOKIE_KEY_EMAIL in cookies:
        del cookies[COOKIE_KEY_EMAIL]
        cookies.save()
        
    st.session_state.auth_status = 'logged_out'
    st.session_state.user_email = None
    st.session_state.user_data = None
    st.session_state.should_rerun = True

# --- UI Principale de l'Application ---

def main_app_ui():
    
    st.title("💡 Tuteur Mathematique Specialise (Systeme Marocain)")
    st.markdown("---")

    st.markdown("""
    **Bienvenue!** Je suis votre **assistant intelligent specialise**, pret a vous aider a resoudre vos problemes de mathematiques. Vous pouvez poser une question ou **telecharger une image** de l'exercice.
    """)

    uploaded_file = st.file_uploader(
        "Optionnel : Telechargez une photo d'un exercice de mathematiques (JPG ou PNG). Maximum 4 Mo.",
        type=["png", "jpg", "jpeg"],
        key="image_uploader"
    )

    image_part_to_send = get_image_part(uploaded_file)
    if uploaded_file is not None:
        try:
            # Affichage de l'image telechargee
            image = Image.open(BytesIO(uploaded_file.getvalue()))
            st.image(image, caption='Image telechargee.', use_column_width=True)
        except Exception as e:
            st.error(f"Erreur lors du chargement de l'image : {e}")

    user_prompt = st.text_area(
        "Ajoutez votre question ou votre instruction ici (meme si vous avez telecharge une image).",
        height=100,
        key="prompt_input"
    )

    if st.button("Generer la Reponse Mathematique", use_container_width=True, type="primary"):
        if not user_prompt and not uploaded_file:
            st.warning("Veuillez entrer une question ou telecharger une image pour commencer la generation.")
        else:
            if uploaded_file and uploaded_file.size > 4 * 1024 * 1024:
                st.error("L'image est trop volumineuse (maximum 4 Mo).")
            else:
                with st.spinner("Analyse du probleme et generation de la reponse..."):
                    response_text, sources = call_gemini_api(user_prompt, image_part_to_send)
                
                # --- AFFICHAGE DU RESULTAT ---
                st.markdown("---")
                
                # Le titre est affiche dans la langue de l'interface
                st.subheader(f"✅ Reponse Generee ({st.session_state.user_lang})") 
                
                # Utiliser st.markdown pour interpreter le Markdown/LaTeX de la reponse
                st.markdown(response_text)
                
                if sources:
                    st.subheader("🌐 Sources utilisees (Google Search Grounding)")
                    for source in sources:
                        st.markdown(f"**[{source['title']}]**({source['uri']})")
                
                # Affiche le decompte de questions restantes
                if not st.session_state.is_unlimited:
                    max_total_requests = MAX_REQUESTS + st.session_state.user_data.get('bonus_questions', 0)
                    remaining = max_total_requests - st.session_state.requests_today
                    if remaining > 0:
                         st.info(f"Questions restantes aujourd'hui : **{remaining}**")
                    else:
                        st.error("Limite journaliere atteinte.")

# --- Boucle Principale de l'Application ---

def main():
    
    # 1. Verification de l'etat d'authentification par cookie
    if st.session_state.auth_status == 'logged_out' and COOKIE_KEY_EMAIL in cookies:
        email_from_cookie = cookies[COOKIE_KEY_EMAIL]
        if email_from_cookie and load_user_session(email_from_cookie):
            st.session_state.auth_status = 'logged_in'

    # 2. Gestion de l'action de Rerun
    if st.session_state.should_rerun:
        st.session_state.should_rerun = False
        st.rerun()

    # 3. Affichage de l'interface
    if st.session_state.auth_status == 'logged_in':
        # L'utilisateur est connecte : Afficher le profil et l'application principale
        profile_ui()
        main_app_ui()
    else:
        # L'utilisateur n'est pas connecte : Afficher l'interface de connexion/inscription
        auth_ui()

# --- Execution ---
if __name__ == '__main__':
    main()



