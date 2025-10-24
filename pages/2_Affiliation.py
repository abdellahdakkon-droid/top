# -*- coding: utf-8 -*-

import streamlit as st
from urllib.parse import urlencode, urlunparse, urlparse, parse_qs
from supabase import create_client, Client 

# 🚨 التعديل الضروري 🚨: رابط التطبيق الحقيقي مع تحديد مسار الصفحة
# إذا كانت صفحة الاستقبال لديك هي الصفحة الرئيسية (index.py)، فاستخدم:
# APP_LIVE_URL = "https://topmath.streamlit.app" 
#
# إذا كانت صفحة الاستقبال (التي بها التسجيل/الدخول) اسمها Accueil.py (أو أي اسم آخر)، يجب أن تحدد المسار.
# سنفترض أن صفحة الهبوط هي الصفحة الرئيسية (الافتراضية).
# إذا لم يعمل هذا، قم بتبديله إلى الخيار الثاني (مثلاً: "https://topmath.streamlit.app/Accueil")
APP_LIVE_URL = "https://topmath.streamlit.app" 


# Constantes
REFERRAL_BONUS = 10
REFERRAL_PARAM = "ref_code"
MAX_REQUESTS = 5
SUPABASE_TABLE_NAME = "users"

# --- 1. Initialisation Supabase Client ---
try:
    # ... (Supabase initialization code remains the same) ...
    supabase_url: str = st.secrets["SUPABASE_URL"]
    supabase_key: str = st.secrets["SUPABASE_KEY"]
    
    supabase: Client = create_client(supabase_url, supabase_key)
    users_table = supabase.table(SUPABASE_TABLE_NAME)
except Exception as e:
    st.error(f"Erreur d'initialisation Supabase: {e}")
    st.warning("تعذر الاتصال بـ Supabase. سيتم عرض البيانات الافتراضية.")

# --- Fonctions Utilitارية ---

def generate_affiliate_link(affiliate_tag, parameter_name, base_url):
    """Génère le lien affilié مع كود المستخدم الحالي."""
    
    # تأكد من أن الـ base_url يحتوي على المسار الصحيح إذا كان تطبيقك متعدد الصفحات
    base_url_for_reg = base_url 
    
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

if 'auth_status' not in st.session_state or st.session_state.auth_status != 'logged_in':
    st.warning("الرجاء تسجيل الدخول للوصول إلى نظام الإحالة.")
    st.stop()

user_email = st.session_state.get('user_email', 'default@example.com')
user_data = st.session_state.get('user_data', {'bonus_questions': 0})

st.title("🤝 نظام الإحالة والمكافآت")
st.markdown("---")

# 1. Statut Actuel et Potentiel

st.header("حالة طلباتك الحالية")

col1, col2, col3 = st.columns(3)

max_total_requests = MAX_REQUESTS + user_data.get('bonus_questions', 0)

with col1:
    st.metric("الحصة الأساسية اليومية", f"{MAX_REQUESTS} طلبات")

with col2:
    current_bonus = user_data.get('bonus_questions', 0)
    st.metric(f"مكافآت الإحالة (كل اشتراك = +{REFERRAL_BONUS})", f"{current_bonus} طلبات")
    
with col3:
    st.metric("الحد الإجمالي اليومي", f"{max_total_requests} طلبات")

st.markdown(f"كل شخص يسجل باستخدام رابطك يحصل على **{REFERRAL_BONUS} طلبات إضافية** إلى حدك اليومي.")
st.markdown("---")


# 2. Générateur de Lien d'Affiliation

st.header("أنشئ رابطك الفريد")

affiliate_tag = user_email # البريد الإلكتروني هو كود الإحالة

# توليد الرابط باستخدام الرابط الفعلي
generated_link = generate_affiliate_link(affiliate_tag, REFERRAL_PARAM, APP_LIVE_URL)

st.code(generated_link, language="text")

# استخدام طريقة أبسط للنسخ اليدوي
if st.button("انسخ الرابط وشاركه", use_container_width=True, type="primary"):
    st.info("الرابط جاهز للنسخ! (Ctrl+C أو Command+C).")


st.markdown("---")
# 3. Tableau de Bord (Statistiques)
st.header("إحصائيات الإحالة")

# محاولة جلب الإحالات من Supabase
referrals = []
try:
    response = users_table.select("email").eq("referred_by", user_email).execute()
    referrals = response.data
except Exception as e:
    st.error("تعذر جلب إحصائيات الإحالة. تأكد من أن الاتصال بـ Supabase فعال.")


if referrals:
    st.metric("اشتراكات ناجحة عبر رابطك", len(referrals))
    
    st.subheader("قائمة الإحالات")
    referral_list = [ref['email'] for ref in referrals]
    st.info(", ".join(referral_list))
else:
    st.metric("اشتراكات ناجحة عبر رابطك", 0)
    st.info("لم يتم إكمال أي اشتراك عبر رابطك بعد. ابدأ بالمشاركة!")

st.caption(f"كود الإحالة الفريد الخاص بك هو: **`{affiliate_tag}`**.")

