# -*- coding: utf-8 -*-

import streamlit as st
from urllib.parse import urlencode, urlunparse, urlparse, parse_qs
# يجب التأكد من استخدامك لمكتبة supabase الصحيحة (عادةً ما تكون supabase-py)
from supabase import create_client, Client 

# 🚨 التعديل الضروري 🚨: تم وضع رابط تطبيقك الحقيقي هنا
# استخدم رابط تطبيقك الفعلي المنشور على Streamlit Cloud
APP_LIVE_URL = "https://topmath.streamlit.app" 
# ملاحظة: إذا كانت صفحة الاستقبال هي الصفحة الرئيسية index، استخدم الرابط كما هو.
# إذا كانت صفحة فرعية اسمها "Accueil" داخل تطبيقك، سيكون الرابط:
# APP_LIVE_URL = "https://topmath.streamlit.app/Accueil"

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
    # إذا فشل الاتصال بقاعدة البيانات، يجب عدم إيقاف التطبيق ولكن عرض رسالة تحذير 
    # st.stop() # تم التعليق على هذا السطر لمنع توقف التطبيق بالكامل
    st.warning("تعذر الاتصال بـ Supabase. سيتم عرض البيانات الافتراضية.")

# --- Fonctions Utilitارية ---

def generate_affiliate_link(affiliate_tag, parameter_name, base_url):
    """Génère le lien affilié avec le code de l'utilisateur actuel."""
    # الرابط الأساسي أصبح متغيراً بدلاً من قيمة ثابتة وهمية
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

# يجب التأكد من وجود هذه المفاتيح في st.session_state 
if 'auth_status' not in st.session_state or st.session_state.auth_status != 'logged_in':
    st.warning("الرجاء تسجيل الدخول للوصول إلى نظام الإحالة.")
    st.stop()

# يجب أن تكون هذه القيم موجودة في st.session_state بعد تسجيل الدخول
user_email = st.session_state.get('user_email', 'default@example.com')
user_data = st.session_state.get('user_data', {'bonus_questions': 0})

st.title("🤝 نظام الإحالة والمكافآت")
st.markdown("---")

# 1. Statut Actuel et Potentiel

st.header("حالة طلباتك الحالية")

col1, col2, col3 = st.columns(3)

# La limite totale est la base + le bonus accumulé
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

# تم حذف زر النسخ غير المدعوم في Streamlit واستبداله بزر تعليمي
if st.button("انسخ الرابط وشاركه", use_container_width=True, type="primary"):
    st.info("تم إنشاء الرابط بنجاح! انسخه يدوياً وشاركه مع أصدقائك.")


st.markdown("---")
# 3. Tableau de Bord (Statistiques)
st.header("إحصائيات الإحالة")

# محاولة جلب الإحالات من Supabase
referrals = []
try:
    # يجب أن يكون حقل 'referred_by' موجوداً في جدول المستخدمين
    response = users_table.select("email").eq("referred_by", user_email).execute()
    referrals = response.data
except Exception as e:
    # عرض خطأ لطيف بدلاً من التوقف
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
