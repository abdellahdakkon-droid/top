# -*- coding: utf-8 -*-

import streamlit as st
import bcrypt
from supabase import create_client, Client
from datetime import date

# --- 1. Initialisation Supabase Client ---
try:
    supabase_url: str = st.secrets["SUPABASE_URL"]
    supabase_key: str = st.secrets["SUPABASE_KEY"]
    
    supabase: Client = create_client(supabase_url, supabase_key)
    users_table = supabase.table("users")
except Exception as e:
    st.error(f"Erreur d'initialisation Supabase: {e}")
    st.stop()

# Constantes
SUPABASE_TABLE_NAME = "users"

# --- Fonctions Supabase Partagées (Réimplémentées pour la page) ---

def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def update_user_data(email, data: dict, use_service_key=False):
    client_to_use = supabase
    try:
        if use_service_key:
            service_key = st.secrets["SUPABASE_SERVICE_KEY"]
            client_to_use = create_client(supabase_url, service_key)
            
        response = client_to_use.table(SUPABASE_TABLE_NAME).update(data).eq("email", email).execute()
        
        if response.data:
            if st.session_state.user_data and st.session_state.user_email == email:
                st.session_state.user_data.update(response.data[0])
            return True
        return False
    except Exception as e:
        print(f"Erreur de mise à jour Supabase: {e}")
        return False
    
def handle_logout():
    # Déconnexion est gérée dans Accueil.py (main) pour la suppression des cookies, mais on peut réinitialiser ici
    st.session_state.auth_status = 'logged_out'
    st.session_state.user_email = None
    st.session_state.user_data = None
    st.success("Déconnexion réussie. Redirection vers la page d'accueil.")
    st.experimental_rerun()


# --- Fonctions de Traitement ---

def handle_save_settings():
    email = st.session_state.user_email

    new_data = {
        'lang': st.session_state.settings_lang,
        'response_type': st.session_state.settings_response_type,
        'school_level': st.session_state.settings_school_level,
    }
    
    if update_user_data(email, new_data):
        st.session_state.user_lang = st.session_state.settings_lang
        st.session_state.response_type = st.session_state.settings_response_type
        st.session_state.school_level = st.session_state.settings_school_level
        st.success("Préférences sauvegardées avec succès!")
        st.experimental_rerun()
    else:
        st.error("Erreur: Les préférences n'ont pas été sauvegardées.")

def handle_change_password():
    email = st.session_state.user_email
    new_password = st.session_state.new_password
    confirm_new_password = st.session_state.confirm_new_password

    if not new_password or new_password != confirm_new_password:
        st.error("Les mots de passe ne correspondent pas.")
        return
    
    if len(new_password) < 6:
        st.error("Le mot de passe doit contenir au moins 6 caractères.")
        return

    if update_user_data(email, {'password_hash': hash_password(new_password)}):
        st.success("Mot de passe changé avec succès! 🔑")
        # Réinitialiser les champs pour l'UX
        st.session_state.new_password = ''
        st.session_state.confirm_new_password = ''
    else:
        st.error("Erreur lors de la mise à jour du mot de passe.")


# --- UI de la Page ---

if st.session_state.auth_status != 'logged_in':
    st.warning("Veuillez vous connecter sur la page d'accueil pour accéder aux paramètres.")
    st.stop()

st.title("⚙️ Paramètres de l'Application")
st.markdown(f"Connecté en tant que: **{st.session_state.user_email}**")
st.markdown("---")

# 1. Préférences d'Assistance
with st.container(border=True):
    st.header("Préférences d'Assistance")
    with st.form("preferences_form"):
        school_levels = ['Tronc Commun', '1ère Année Bac (Sciences)', '2ème Année Bac (Sciences Maths A)', '2ème Année Bac (Sciences Maths B)', '2ème Année Bac (Sciences Expérimentales)', 'Écoles Supérieures/Classes Préparatoires']
        
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
        
        st.radio(
            "Langue Préférée pour les Réponses",
            options=['fr', 'ar'],
            format_func=lambda x: 'Français' if x == 'fr' else 'Arabe',
            key="settings_lang",
            index=0 if st.session_state.user_lang == 'fr' else 1
        )
        
        response_options = {'answer': 'Réponse Finale Seulement', 'steps': 'Étapes Détaillées', 'explanation': 'Explication Conceptuelle'}
        response_keys = list(response_options.keys())
        
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
        st.text_input("Nouveau Mot de Passe", type="password", key="new_password")
        st.text_input("Confirmer le Nouveau Mot de Passe", type="password", key="confirm_new_password")
        st.form_submit_button("Changer le Mot de Passe", type="secondary", on_click=handle_change_password, use_container_width=True)
