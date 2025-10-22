# -*- coding: utf-8 -*-

import streamlit as st
from supabase import create_client, Client
from datetime import date
import bcrypt # Nécessaire pour les fonctions partagées

# Constantes
ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL", "admin@example.com")
MAX_REQUESTS = 5
SUPABASE_TABLE_NAME = "users"

# --- 1. Initialisation Supabase Client ---
try:
    supabase_url: str = st.secrets["SUPABASE_URL"]
    
    # Pour les opérations admin, nous avons besoin de la clé de service
    try:
        service_key = st.secrets["SUPABASE_SERVICE_KEY"]
    except KeyError:
        st.error("Erreur: Clé de service Supabase (SUPABASE_SERVICE_KEY) manquante. Accès refusé.")
        st.stop()

    admin_client: Client = create_client(supabase_url, service_key)
    users_table = admin_client.table(SUPABASE_TABLE_NAME)

except Exception as e:
    st.error(f"Erreur d'initialisation Supabase pour l'Admin: {e}")
    st.stop()

# --- Fonctions de Traitement ---

def update_user_data(email, data: dict, client_to_use):
    """Met à jour les données utilisateur en utilisant le client Admin."""
    try:
        response = client_to_use.table(SUPABASE_TABLE_NAME).update(data).eq("email", email).execute()
        return response.data is not None
    except Exception as e:
        st.error(f"Erreur de mise à jour: {e}")
        return False

def toggle_unlimited_use(target_email, current_status):
    new_status = not current_status
    
    if update_user_data(target_email, {'is_unlimited': new_status}, admin_client):
        st.success(f"Utilisateur **{target_email}** mis à jour: Utilisation illimitée = {new_status}")
    else:
        st.error(f"Échec de la mise à jour de l'utilisateur {target_email}")


# --- UI de la Page ---

if st.session_state.auth_status != 'logged_in' or st.session_state.user_email != ADMIN_EMAIL:
    st.error("Accès Refusé. Cette page est réservée à l'administrateur.")
    st.stop()


st.title("👑 Tableau de Bord Administrateur")
st.markdown("---")

st.info("Vue globale des utilisateurs et gestion des privilèges (Requiert SUPABASE_SERVICE_KEY).")

# Récupération de tous les utilisateurs (sauf l'admin)
try:
    response = users_table.select("*").neq("email", ADMIN_EMAIL).execute()
    all_users = response.data
except Exception as e:
    st.error(f"Échec de la récupération de la liste des utilisateurs: {e}")
    all_users = []

# Statistiques globales
total_users = len(all_users) + 1 # +1 pour l'admin

total_bonus_requests = sum(user.get('bonus_questions', 0) for user in all_users)
successful_referrals = sum(1 for user in all_users if user.get('referred_by'))

col1, col2, col3 = st.columns(3)
col1.metric("Total Utilisateurs (Hors Admin)", len(all_users))
col2.metric("Total Requêtes Bonus Distribuées", total_bonus_requests)
col3.metric("Total Parrainages Réussis", successful_referrals)

st.markdown("---")

# Gestion des Utilisateurs et Privilèges
st.subheader("Gestion des Privilèges Utilisateur")

if not all_users:
    st.write("Aucun utilisateur enregistré (à part l'administrateur).")
else:
    
    # Affichage des utilisateurs sous forme de tableau interactif
    for user_data in all_users:
        email = user_data['email']
        is_unlimited = user_data.get('is_unlimited', False)
        bonus = user_data.get('bonus_questions', 0)
        requests_used = user_data.get('requests_today', 0)
        
        # Affichage du statut
        status_text = "ILLIMITÉ (VIP)" if is_unlimited else f"Limité ({requests_used}/{MAX_REQUESTS + bonus})"
        status_color = "#28a745" if is_unlimited else "#ffc107"
        
        with st.expander(f"**{email}** - {status_text}", expanded=False):
            st.markdown(f"**E-mail:** `{email}`")
            st.markdown(f"**Requêtes Bonus Gagnées:** {bonus}")
            st.markdown(f"**Parrainé Par:** `{user_data.get('referred_by', 'N/A')}`")
            st.markdown(f"**Statut Illimité:** {is_unlimited}")
            
            button_label = "Retirer Illimité" if is_unlimited else "Accorder Illimité"
            button_key = f"toggle_{email}"
            
            st.button(
                button_label,
                key=button_key,
                on_click=toggle_unlimited_use,
                args=(email, is_unlimited),
                type="primary",
                use_container_width=True
            )
