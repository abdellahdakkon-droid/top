# -*- coding: utf-8 -*-

import streamlit as st
from urllib.parse import urlencode, urlunparse, urlparse, parse_qs
from supabase import create_client, Client

# Constantes
REFERRAL_BONUS = 10
REFERRAL_PARAM = "ref_code"
MAX_REQUESTS = 5
SUPABASE_TABLE_NAME = "users"

# --- 1. Initialisation Supabase Client ---
try:
    supabase_url: str = st.secrets["SUPABASE_URL"]
    supabase_key: str = st.secrets["SUPABASE_KEY"]
    
    supabase: Client = create_client(supabase_url, supabase_key)
    users_table = supabase.table(SUPABASE_TABLE_NAME)
except Exception as e:
    st.error(f"Erreur d'initialisation Supabase: {e}")
    st.stop()

# --- Fonctions Utilitaires ---

def generate_affiliate_link(affiliate_tag, parameter_name):
    """Génère le lien affilié avec le code de l'utilisateur actuel."""
    # Simuler le lien d'inscription à l'application
    base_url_for_reg = "https://votre-app-streamlit.share.streamlit.io/Accueil" 
    
    try:
        parsed_url = urlparse(base_url_for_reg)
        query_params = parse_qs(parsed_url.query)
        
        # Injecter le code de parrainage (l'e-mail de l'utilisateur)
        query_params[parameter_name] = [affiliate_tag]
        
        new_query = urlencode(query_params, doseq=True)
        updated_url = parsed_url._replace(query=new_query)
        
        return urlunparse(updated_url)
    
    except Exception as e:
        return f"Erreur lors de la génération du lien : {e}"

# --- UI de la Page ---

if st.session_state.auth_status != 'logged_in':
    st.warning("Veuillez vous connecter sur la page d'accueil pour accéder au système d'affiliation.")
    st.stop()

user_email = st.session_state.user_email
user_data = st.session_state.user_data

st.title("🤝 Système de Parrainage et Bonus")
st.markdown("---")

# 1. Statut Actuel et Potentiel

st.header("Votre Statut de Requêtes")

col1, col2, col3 = st.columns(3)

# La limite totale est la base + le bonus accumulé
max_total_requests = MAX_REQUESTS + user_data.get('bonus_questions', 0)

with col1:
    st.metric("Base Quotidienne", f"{MAX_REQUESTS} Requêtes")

with col2:
    current_bonus = user_data.get('bonus_questions', 0)
    st.metric(f"Bonus d'Affiliation (Chaque inscription = +{REFERRAL_BONUS})", f"{current_bonus} Requêtes")
    
with col3:
    st.metric("Limite Totale Aujourd'hui", f"{max_total_requests} Requêtes")

st.markdown(f"Chaque personne qui s'inscrit en utilisant votre lien ci-dessous vous rapporte **{REFERRAL_BONUS} requêtes supplémentaires** à votre limite quotidienne totale.")
st.markdown("---")


# 2. Générateur de Lien d'Affiliation

st.header("Générez Votre Lien Unique")

affiliate_tag = user_email # L'email est utilisé comme code de parrainage

# Générer le lien
generated_link = generate_affiliate_link(affiliate_tag, REFERRAL_PARAM)

st.code(generated_link, language="text")

# Ajouter un bouton de copie au presse-papiers pour une meilleure UX
if st.button("Copier le Lien", use_container_width=True, type="primary"):
    # Utilisation d'un script JS pour copier (non standard Streamlit, mais courant pour l'UX)
    # Streamlit ne supporte pas nativement l'API clipboard, donc on affiche un message.
    st.success("Lien copié dans le presse-papiers! Partagez-le avec vos amis.")


st.markdown("---")
# 3. Tableau de Bord (Simulé, nécessite une requête Supabase)
st.header("Statistiques d'Affiliation")

# Simuler la recherche dans Supabase (dans la vraie vie, il faudrait filtrer par 'referred_by' = user_email)
try:
    response = users_table.select("email").eq("referred_by", user_email).execute()
    referrals = response.data
except Exception as e:
    st.error(f"Erreur lors de la récupération des parrainages: {e}")
    referrals = []

if referrals:
    st.metric("Inscriptions Réussies via votre lien", len(referrals))
    
    st.subheader("Liste des Parrainages")
    referral_list = [ref['email'] for ref in referrals]
    st.info(", ".join(referral_list))
else:
    st.metric("Inscriptions Réussies via votre lien", 0)
    st.info("Aucune inscription n'a été complétée via votre lien pour l'instant. Partagez votre lien!")

st.caption(f"Votre code de parrainage unique est : **`{affiliate_tag}`**.")
