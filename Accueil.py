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
    page_title="Tuteur IA Mathématiques (Système Marocاني)",
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
REFERRAL_BONUS = 10 # 10 questions en plus pour l'affilié
REFERRAL_PARAM = "ref_code"
ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL", "admin@example.com")
max_retries = 3
COOKIE_KEY_EMAIL = "user_auth_email"
SUPABASE_TABLE_NAME = "users"

# Configuration de la clé API
API_KEY = st.secrets.get("GEMINI_API_KEY", "PLACEHOLDER_FOR_API_KEY")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- 2. Initialisation Supabase Client ---
try:
    supabase_url: str = st.secrets["SUPABASE_URL"]
    supabase_key: str = st.secrets["SUPABASE_KEY"]
    
    supabase: Client = create_client(supabase_url, supabase_key)
    users_table = supabase.table(SUPABASE_TABLE_NAME)
except KeyError:
    st.error("Erreur de configuration: Veuillez ajouter les clés Supabase (URL, KEY) dans `secrets.toml`.")
    st.stop()
except Exception as e:
    st.error(f"Erreur d'initialisation Supabase: {e}")
    st.stop()
    
# --- Initialisation de l'État de la Session ---
if 'auth_status' not in st.session_state: st.session_state.auth_status = 'logged_out'
if 'user_email' not in st.session_state: st.session_state.user_email = None
if 'user_data' not in st.session_state: st.session_state.user_data = None
if 'user_lang' not in st.session_state: st.session_state.user_lang = 'fr'
if 'response_type' not in st.session_state: st.session_state.response_type = 'steps'
if 'school_level' not in st.session_state: st.session_state.school_level = 'Tronc Commun'
if 'requests_today' not in st.session_state: st.session_state.requests_today = 0
if 'is_unlimited' not in st.session_state: st.session_state.is_unlimited = False
if 'should_rerun' not in st.session_state: st.session_state.should_rerun = False # مفتاح جديد لإعادة التحميل

# --- Fonctions Supabase Partagées ---

def hash_password(password: str) -> str:
    """Hachage sécurisé du mot de passe avec bcrypt."""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def check_password(password: str, hashed_password: str) -> bool:
    """Vérifie le mot de passe entré par rapport au hachاج المخزون."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_user_by_email(email: str):
    """Récupère les données utilisateur depuis Supabase."""
    try:
        response = users_table.select("*").eq("email", email).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Erreur de récupération utilisateur: {e}")
        return None

def update_user_data(email, data: dict, use_service_key=False):
    """Met à jour les données utilisateur dans Supabase."""
    client_to_use = supabase
    try:
        if use_service_key:
            # Nécessite SUPABASE_SERVICE_KEY dans secrets.toml
            service_key = st.secrets["SUPABASE_SERVICE_KEY"]
            client_to_use = create_client(supabase_url, service_key)
            
        response = client_to_use.table(SUPABASE_TABLE_NAME).update(data).eq("email", email).execute()
        
        if response.data:
            if st.session_state.user_data and st.session_state.user_email == email:
                st.session_state.user_data.update(response.data[0])
            return True
        return False
    except KeyError:
        st.error("Erreur: Clé de service Supabase manquante pour l'opération administrateur.")
        return False
    except Exception as e:
        print(f"Erreur de mise à jour Supabase pour {email}: {e}")
        return False

# --- Fonctions Auxiliaires (Helper Functions) ---

def get_image_part(uploaded_file):
    """
    Crée la partie 'inlineData' لـ API Gemini.
    يحتوي على تحقق للتأكد من أن mimeType صحيح.
    """
    if uploaded_file is not None:
        bytes_data = uploaded_file.getvalue()
        mime_type = uploaded_file.type
        
        # التحقق من أن تنسيق MIME مدعوم
        if mime_type not in ["image/png", "image/jpeg", "image/jpg"]:
            # محاولة تخمين التنسيق الافتراضي
            if uploaded_file.name.lower().endswith('.png'):
                mime_type = "image/png"
            elif uploaded_file.name.lower().endswith(('.jpg', '.jpeg')):
                mime_type = "image/jpeg"
            else:
                st.warning("تنسيق صورة غير مدعوم. نرجو استخدام JPG أو PNG.")
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
        st.error("Erreur de configuration : Veuillez ajouter la clé GEMINI_API_KEY.")
        return "Veuillez fournir une clé API valide.", []

    email = st.session_state.user_email
    user_data = st.session_state.user_data
    current_date_str = str(date.today())
    
    # 1. Application de la Limite de Requêtes
    max_total_requests = MAX_REQUESTS + user_data.get('bonus_questions', 0)
    
    if not user_data.get('is_unlimited', False):
        
        if user_data.get('last_request_date') != current_date_str:
            st.session_state.requests_today = 0
            user_data['requests_today'] = 0
            user_data['last_request_date'] = current_date_str
            update_user_data(email, {'requests_today': 0, 'last_request_date': current_date_str})

        current_count = st.session_state.requests_today

        if current_count >= max_total_requests:
            st.error(f"Limite atteinte : Vous avez atteint le maximum de requêtes ({max_total_requests}) pour aujourd'hui. Revenez demain أو consultez la page 'Affiliation' pour gagner plus de requêtes.")
            return "Limite de requêtes atteinte.", []
            
        st.session_state.requests_today = current_count + 1

    # Construction des instructions pour le modèle
    lang = user_data.get('lang', 'fr')
    response_type = user_data.get('response_type', 'steps')
    school_level = user_data.get('school_level', 'Tronc Commun')
    
    system_prompt_base = f"Tu es un tuteur spécialisé en mathématiques, expert du système éducatif marocain (niveau '{school_level}'). Ta mission est de fournir une assistance précise et didactique. Si une image est fournie, tu dois l'analyser et résoudre le problème."

    # FIX: Suppression du formatage Markdown (**) des instructions du style 
    # car cela provoque l'erreur "Invalid value at 'system_instruction'".
    if response_type == 'answer':
        style_instruction = "Fournis uniquement la réponse finale et concise du problème, sans aucune explication détaillée ni étapes intermédiaires."
    elif response_type == 'steps':
        style_instruction = "Fournis les étapes détaillées de résolution de manière structurée et méthodique pour aider l'étudiant à suivre le raisonnement."
    else:
        style_instruction = "Fournis une explication conceptuelle approfondie du problème ou du sujet, et concentre-toi sur les théories et les concepts impliqués."
        
    lang_instruction = "Tu dois répondre exclusivement en français." if lang == 'fr' else "Tu dois répondre exclusivement en français، en utilisant les termes mathématiques usuels."

    # L'instruction finale demande toujours au modèle d'utiliser Markdown pour la SORTIE.
    final_system_prompt = f"{system_prompt_base} {lang_instruction} {style_instruction} Utilise le format Markdown pour organiser ta réponse, et assure-toi que les formules mathématiques sont formatées en LaTeX."

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

    # Mécanisme de Ré-essai (Retry)
    for attempt in range(max_retries):
        try:
            full_url = f"{API_URL}?key={API_KEY}"
            
            response = requests.post(full_url, headers=headers, data=json.dumps(payload))
            
            # 1. Capture spécifique du code 400 pour un meilleur diagnostic
            response.raise_for_status() 
            
            # Si le code arrive ici، la requête a réussi (code 200)
            result = response.json()
            
            # Mise à jour du compteur dans Supabase
            if not user_data.get('is_unlimited', False):
                update_user_data(email, {'requests_today': st.session_state.requests_today, 'last_request_date': current_date_str})
                
            candidate = result.get('candidates', [None])[0]
            
            if candidate and candidate.get('content') and candidate['content'].get('parts'):
                generated_text = candidate['content']['parts'][0].get('text', "Aucun texte trouvé.")
                
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
                return "Désolé, le modèle n'a pas pu fournir de réponse. Veuillez réessayer avec une autre requête.", []

        except requests.exceptions.HTTPError as e:
            # Traiter les erreurs 4XX et 5XX. Important pour le 400.
            error_details = response.text
            st.error(f"Échec de la connexion (Tentative {attempt + 1}/{max_retries}): {e}. \n\n**Détails du serveur (Google API):** \n`{error_details}`")
            print(f"API Error Details: {error_details}") # Affichage dans la console pour le débogage
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            
            # Retourner l'erreur détaillée après la dernière tentative
            return f"Échec final de la connexion (Code {response.status_code}). Veuillez vérifier la validité de votre clé API dans `secrets.toml` أو le format de l'image si elle a été téléchargée.", []

        except requests.exceptions.RequestException as e:
            # Traiter les erreurs de réseau (DNS, timeout, etc.)
            st.error(f"Erreur réseau (Tentative {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return f"Échec de la connexion après {max_retries} tentatives: {e}.", []
        except Exception as e:
            return f"خطأ غير متوقع: {e}", []
    
    return "فشل توليد الإجابة.", []

# --- Fonctions d'Authentification ---

def load_user_session(email, save_cookie=False):
    user_data = get_user_by_email(email)
    
    if user_data:
        if save_cookie:
            cookies[COOKIE_KEY_EMAIL] = email
            cookies.save()
            
        st.session_state.user_email = email
        st.session_state.user_data = user_data
        # تحميل القيم من قاعدة البيانات (ستكون القيم الافتراضية إذا تم التسجيل الآن)
        st.session_state.user_lang = user_data.get('lang', 'fr')
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
        st.session_state.should_rerun = True # إعلام التطبيق بضرورة إعادة التحميل
        return True
    return False


def handle_login():
    """Traite la connexion et la vérification du mot de passe."""
    email = st.session_state.login_email.lower()
    password = st.session_state.login_password
    
    user_data = get_user_by_email(email)
    
    if user_data and check_password(password, user_data.get('password_hash', '')):
        # استخدام st.success قبل load_user_session
        st.success("Connexion réussie! Bienvenue.")
        load_user_session(email, save_cookie=True)
        # لا نستخدم st.experimental_rerun() هنا لتجنب الخطأ
    else:
        st.error("E-mail أو mot de passe incorrect.")

def handle_register():
    """Traite l'inscription، vérifie le code de parrainage et accorde la récompense."""
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

    # --- LOGIQUE DE PARRAINAGE ---
    referrer_email = None
    query_params = st.query_params
    
    if REFERRAL_PARAM in query_params:
        potential_referrer_email = query_params[REFERRAL_PARAM]
        # Dans Streamlit، les query params peuvent être des listes. On prend le premier élément.
        if isinstance(potential_referrer_email, list):
            potential_referrer_email = potential_referrer_email[0]  
            
        # 1. Vérifier si l'e-mail du parrain existe
        referrer_data = get_user_by_email(potential_referrer_email)
        if referrer_data:
            referrer_email = potential_referrer_email
            # 2. Accorder le bonus de 10 questions au parrain (Bonus_questions)
            current_bonus = referrer_data.get('bonus_questions', 0)
            new_bonus = current_bonus + REFERRAL_BONUS
            
            if update_user_data(referrer_email, {'bonus_questions': new_bonus}, use_service_key=True):
                 st.info(f"Félicitations! Le parrain ({referrer_email}) a reçu {REFERRAL_BONUS} questions bonus.")
            
    # Sauvegarder le nouvel utilisateur
    new_user_data = {
        'email': email,
        'password_hash': hash_password(password),
        # VALEURS الافتراضية الثابتة (لأن الخيارات أزيلت من الواجهة)
        'lang': 'fr', 
        'response_type': 'steps', 
        'school_level': 'Tronc Commun',
        'is_unlimited': False,
        'requests_today': 0,
        'last_request_date': str(date.today()),
        'bonus_questions': 0, # Le nouvel utilisateur commence avec 0 bonus
        'referred_by': referrer_email, # Enregistrer l'e-mail du parrain
    }
    
    try:
        users_table.insert([new_user_data]).execute()
        st.success("Inscription et connexion réussies! 🥳")
        load_user_session(email, save_cookie=True)
        # لا نستخدم st.experimental_rerun() هنا لتجنب الخطأ
    except Exception as e:
        st.error(f"Échec de l'inscription: {e}. (Vérifiez les règles RLS de Supabase.)")

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
            # عند النقر على زر تسجيل الدخول، يتم استدعاء الدالة handle_login
            st.form_submit_button("Connexion", type="primary", on_click=handle_login)

    with col2:
        with st.form("register_form"):
            st.subheader("S'inscrire")
            st.text_input("E-mail", key="reg_email")
            st.text_input("Mot de passe", type="password", key="reg_password")
            st.text_input("Confirmer le mot de passe", type="password", key="reg_password_confirm")
            
            # --- خيارات التفضيلات الافتراضية ---
            st.subheader("Vos Préférences par Défaut")
            st.caption("Votre compte سيكون مكوّناً بشكل افتراضي على: **الفرنسية** (الإجابة عبر **الخطوات التفصيلية**، والمستوى الدراسي **الجذع المشترك**).")


            # Affiche si un code de parrainage est détecté dans l'URL
            query_params = st.query_params
            if REFERRAL_PARAM in query_params:
                ref_email = query_params[REFERRAL_PARAM]
                if isinstance(ref_email, list): ref_email = ref_email[0]
                st.info(f"Vous vous inscrivez via le lien de parrainage ({ref_email}). Votre parrain recevra un bonus!")

            # عند النقر على زر التسجيل، يتم استدعاء الدالة handle_register
            st.form_submit_button("S'inscrire", type="secondary", on_click=handle_register)


# --- UI Principale de l'Application ---

def main_app_ui():
    
    st.title("💡 Tuteur Mathématique Spécialisé (Système المغربي)")
    st.markdown("---")

    st.markdown("""
    **Bienvenue!** أنا **مساعدك الذكي المتخصص**، جاهز لمساعدتك في حل مسائل الرياضيات الخاصة بك. يمكنك طرح سؤال أو **تحميل صورة** للتمرين.
    """)

    uploaded_file = st.file_uploader(
        "Optionnel : Téléchargez une photo d'un exercice de mathématiques (JPG أو PNG). الحد الأقصى 4 ميجابايت.",
        type=["png", "jpg", "jpeg"],
        key="image_uploader"
    )

    image_part_to_send = get_image_part(uploaded_file)
    if uploaded_file is not None:
        try:
            image = Image.open(BytesIO(uploaded_file.getvalue()))
            st.image(image, caption='Image téléchargée.', use_column_width=True)
        except Exception as e:
            st.error(f"Erreur lors du chargement de l'image : {e}")

    user_prompt = st.text_area(
        "Ajoutez votre question ou votre instruction ici (même si vous avez téléchargé une image).",
        height=100,
        key="prompt_input"
    )

    if st.button("Générer la Réponse Mathématique", use_container_width=True, type="primary"):
        if not user_prompt and not uploaded_file:
            st.warning("Veuillez entrer une question أو télécharger une image pour commencer la génération.")
        else:
            if uploaded_file and uploaded_file.size > 4 * 1024 * 1024:
                st.error("L'image est trop volumineuse. Veuillez télécharger un fichier de moins de 4 Mo.")
            elif uploaded_file and image_part_to_send is None:
                st.error("تعذّر معالجة الصورة. تأكد من أن التنسيق هو JPG أو PNG.")
            else:
                
                with st.spinner('L\'IA analyse et prépare la réponse...'):
                    # نمرر image_part_to_send، حتى لو كان None (في حال عدم وجود صورة)
                    generated_text, sources = call_gemini_api(user_prompt, image_part_to_send)
                
                st.subheader("✅ Réponse Générée :")
                
                if generated_text and "Limite de requêtes atteinte" not in generated_text:
                    st.write_stream(stream_text_simulation(generated_text))
                    
                    if sources:
                        st.subheader("🌐 Sources Citées :")
                        unique_sources = set()
                        for s in sources:
                            if s['uri'] and s['title']:
                                unique_sources.add((s['title'], s['uri']))
                        
                        source_markdown = ""
                        for title, uri in unique_sources:
                            source_markdown += f"- [{title}]({uri})\n"
                        
                        st.markdown(source_markdown)
                    else:
                        st.caption("Aucune source de recherche externe n'a été utilisée pour cette réponse.")

                else:
                    # يتم عرض خطأ API التفصيلي هنا
                    st.markdown(generated_text)


# --- Contrôle du Flux الرئيسي وإعادة التحميل ---

# 1. تحقق من الكوكي عند بدء التشغيل
if st.session_state.auth_status == 'logged_out':
    remembered_email = cookies.get(COOKIE_KEY_EMAIL)
    if remembered_email:
        if load_user_session(remembered_email):
            st.toast(f"Bienvenue، {remembered_email.split('@')[0]}! Connexion automatique.")
            st.rerun()
            
# 2. عرض الواجهة المناسبة
if st.session_state.auth_status == 'logged_out':
    auth_ui()
else:
    # إذا كان المستخدم مسجلاً دخوله، اعرض الواجهة الرئيسية
    main_app_ui()

    # الشريط الجانبي للحالة
    st.sidebar.header(f"Statut de l'Utilisateur")
    st.sidebar.markdown(f"**E-mail:** `{st.session_state.user_email}`")
    
    if st.session_state.is_unlimited:
        status_message = "✅ **Utilisation Illimitée (VIP)**"
        color = "#28a745"
    else:
        max_total_requests = MAX_REQUESTS + st.session_state.user_data.get('bonus_questions', 0)
        requests_left = max_total_requests - st.session_state.requests_today
        status_message = f"Requêtes restantes aujourd'hui: **{requests_left}** / {max_total_requests}"
        color = "#007bff" if requests_left > 0 else "#dc3545"

    st.sidebar.markdown(f"""
    <div style='background-color:#e9ecef; padding:10px; border-radius:5px; text-align:center; border-left: 5px solid {color};'>
        <span style='font-weight: bold; color: {color};'>{status_message}</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.sidebar.markdown("---")

# 3. معالجة إعادة التحميل التلقائي بعد تسجيل الدخول/التسجيل بنجاح
# هذا يضمن إعادة تحميل واحدة فقط، مع تجنب الخطأ السابق
if st.session_state.should_rerun:
    st.session_state.should_rerun = False
    st.experimental_rerun()



