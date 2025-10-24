# -*- coding: utf-8 -*-
# Tuteur Mathématique IA (Système Éducatif Marocain) - Page de Paramètres

import streamlit as st
import bcrypt
from supabase import create_client, Client
from datetime import date
from streamlit_cookies_manager import EncryptedCookieManager # تمت الإضافة للاستخدام الآمن للـ logout

# 🌟🌟🌟 الحل: ضمان تهيئة جميع مفاتيح st.session_state الأساسية 🌟🌟🌟
# هذا يحل مشكلة AttributeError إذا تم تحميل الصفحة مباشرة
if 'auth_status' not in st.session_state: st.session_state.auth_status = 'logged_out'
if 'user_email' not in st.session_state: st.session_state.user_email = None
if 'user_data' not in st.session_state: st.session_state.user_data = None
# مفاتيح الإعدادات التي تستخدمها الواجهة
if 'school_level' not in st.session_state: st.session_state.school_level = 'Tronc Commun' # قيمة افتراضية معقولة
if 'response_type' not in st.session_state: st.session_state.response_type = 'steps'
if 'user_lang' not in st.session_state: st.session_state.user_lang = 'fr' # تم تعديلها لتوافق المفتاح المستخدم (user_lang)
# 🌟🌟🌟 نهاية كتلة التهيئة 🌟🌟🌟

# --- 1. Initialisation Supabase Client ---
try:
    supabase_url: str = st.secrets["SUPABASE_URL"]
    supabase_key: str = st.secrets["SUPABASE_KEY"]
    SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"] # مفتاح الخدمة أصبح ضرورياً
    
    supabase: Client = create_client(supabase_url, supabase_key)
    users_table = supabase.table("users")

    # تهيئة Cookies (لضرورة handle_logout)
    cookies = EncryptedCookieManager(
        prefix="gemini_math_app/",
        password=st.secrets.get("COOKIE_PASSWORD", "super_secret_default_key"), 
    )
    if not cookies.ready():
        st.stop()
        
except KeyError as e:
    st.error(f"Erreur de configuration: Clé manquante dans secrets.toml: {e}.")
    st.stop()
except Exception as e:
    st.error(f"Erreur d'initialisation Supabase: {e}")
    st.stop()

# Constantes
SUPABASE_TABLE_NAME = "users"
COOKIE_KEY_EMAIL = "user_auth_email"


# --- Fonctions Supabase Partagées (Réimplémentées pour la page) ---

def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def get_supabase_client(use_service_key: bool = False) -> Client:
    """Récupère le client Supabase standard ou le client avec clé de service."""
    if use_service_key and SERVICE_KEY:
        return create_client(supabase_url, SERVICE_KEY)
    return supabase

def update_user_data(email, data: dict, use_service_key=False):
    client_to_use = get_supabase_client(use_service_key)
    try:
        response = client_to_use.table(SUPABASE_TABLE_NAME).update(data).eq("email", email).execute()
        
        if response.data:
            if st.session_state.user_data and st.session_state.user_email == email:
                st.session_state.user_data.update(response.data[0])
                # تحديث مفاتيح الجلسة الفردية بعد التحديث
                if 'lang' in data: st.session_state.user_lang = data['lang']
                if 'response_type' in data: st.session_state.response_type = data['response_type']
                if 'school_level' in data: st.session_state.school_level = data['school_level']
            return True
        return False
    except Exception as e:
        print(f"Erreur de mise à jour Supabase: {e}")
        return False
    
def handle_logout():
    """Déconnexion complète مع حذف الكوكيز."""
    cookies[COOKIE_KEY_EMAIL] = ""
    cookies.save()
    st.session_state.auth_status = 'logged_out'
    st.session_state.user_email = None
    st.session_state.user_data = None
    # إعادة تهيئة المفاتيح لمنع الخطأ عند العودة
    st.session_state.school_level = 'Tronc Commun'
    st.session_state.response_type = 'steps'
    st.session_state.user_lang = 'fr'
    st.success("Déconnexion réussie. Redirection vers la page d'accueil.")
    st.rerun()


# --- Fonctions de Traitement ---

def handle_save_settings():
    email = st.session_state.user_email
    
    # 🌟 المفاتيح المستخدمة في واجهة المستخدم (settings_*) هي مفاتيح مؤقتة
    new_data = {
        'lang': st.session_state.settings_lang,
        'response_type': st.session_state.settings_response_type,
        'school_level': st.session_state.settings_school_level,
    }
    
    # نستخدم مفتاح 'lang' هنا لأنه هو المستخدم في قاعدة البيانات
    if update_user_data(email, new_data):
        # لم نعد بحاجة لتحديث مفاتيح الجلسة الفردية هنا، لأن update_user_data يقوم بذلك
        st.success("Préférences sauvegardées avec succès!")
        st.rerun() # تحديث الصفحة لتعكس الإعدادات الجديدة
    else:
        st.error("Erreur: Les préférences n'ont pas été sauvegardées.")

def handle_change_password():
    email = st.session_state.user_email
    # يجب تهيئة هذه المفاتيح في st.session_state إذا لم تُكتب في الواجهة بعد
    new_password = st.session_state.get('new_password', '')
    confirm_new_password = st.session_state.get('confirm_new_password', '')

    if not new_password or new_password != confirm_new_password:
        st.error("Les mots de passe ne correspondent pas.")
        return
    
    if len(new_password) < 6:
        st.error("Le mot de passe doit contenir au moins 6 caractères.")
        return

    if update_user_data(email, {'password_hash': hash_password(new_password)}, use_service_key=True):
        st.success("Mot de passe changé avec succès! 🔑")
        # Réinitialiser les champs pour l'UX
        st.session_state.new_password = ''
        st.session_state.confirm_new_password = ''
        # يجب تحديث st.session_state.new_password = '' بعد النجاح
    else:
        st.error("Erreur lors de la mise à jour du mot de passe.")


# --- UI de la Page ---

if st.session_state.auth_status != 'logged_in':
    st.warning("Veuillez vous connecter sur la page d'accueil pour accéder aux paramètres.")
    st.stop()

# تحقق دفاعي لضمان وجود البيانات الرئيسية
if not st.session_state.user_data:
    st.warning("الرجاء تسجيل الخروج والدخول مجدداً لتحميل بيانات الحساب بشكل صحيح.")
    st.button("تسجيل الخروج", on_click=handle_logout)
    st.stop()
    
st.title("⚙️ Paramètres de l'Application")
st.markdown(f"Connecté en tant que: **{st.session_state.user_email}**")
st.markdown("---")

# 1. Préférences d'Assistance
with st.container(border=True):
    st.header("Préférences d'Assistance")
    with st.form("preferences_form"):
        school_levels = ['Tronc Commun', '1ère Année Bac (Sciences)', '2ème Année Bac (Sciences Maths A)', '2ème Année Bac (Sciences Maths B)', '2ème Année Bac (Sciences Expérimentales)', 'Écoles Supérieures/Classes Préparatoires']
        
        # 🌟 استخدام مفتاح st.session_state.school_level للمؤشر
        try:
            current_level_index = school_levels.index(st.session_state.school_level)
        except ValueError:
            current_level_index = 0
            
        st.selectbox(
            "Niveau Scolaire",
            options=school_levels,
            key="settings_school_level",
            index=current_level_index
        )
        
        # 🌟 استخدام مفتاح st.session_state.user_lang للمؤشر
        st.radio(
            "Langue Préférée pour les Réponses",
            options=['fr', 'ar'],
            format_func=lambda x: 'Français' if x == 'fr' else 'Arabe',
            key="settings_lang",
            index=0 if st.session_state.user_lang == 'fr' else 1
        )
        
        response_options = {'answer': 'Réponse Finale Seulement', 'steps': 'Étapes Détaillées', 'explanation': 'Explication Conceptuelle'}
        response_keys = list(response_options.keys())
        
        # 🌟 استخدام مفتاح st.session_state.response_type للمؤشر
        try:
            current_response_index = response_keys.index(st.session_state.response_type)
        except ValueError:
            current_response_index = 1

        st.selectbox(
            "Type de Réponse par Défaut",
            options=response_keys,
            format_func=lambda x: response_options[x],
            key="settings_response_type",
            index=current_response_index
        )

        st.form_submit_button("Sauvegarder les Préférences", type="primary", on_click=handle_save_settings, use_container_width=True)

st.markdown("---")

# 2. Changer le Mot de Passe
with st.container(border=True):
    st.header("Sécurité du Compte")
    with st.form("password_change_form"):
        # يجب تمرير القيمة الفارغة لتفادي الخطأ إذا كان هناك 'rerun'
        st.text_input("Nouveau Mot de Passe", type="password", key="new_password", value="")
        st.text_input("Confirmer le Nouveau Mot de Passe", type="password", key="confirm_new_password", value="")
        st.form_submit_button("Changer le Mot de Passe", type="secondary", on_click=handle_change_password, use_container_width=True)
