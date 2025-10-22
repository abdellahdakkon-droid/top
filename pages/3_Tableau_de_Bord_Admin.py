# -*- coding: utf-8 -*-
import streamlit as st
import time
from supabase import create_client, Client
from datetime import date

# --- 1. Importations و Constants (Doivent تكون هي نفسها في Accueil.py) ---
try:
    # يقرأ البريد الإلكتروني للمسؤول من st.secrets
    ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL")
    
    if not ADMIN_EMAIL:
        st.error("خطأ في الإعداد: متغيّر ADMIN_EMAIL مفقود في ملف .streamlit/secrets.toml. يرجى إضافته.")
        st.stop()
        
    MAX_REQUESTS = 5 
    SUPABASE_TABLE_NAME = "users"
    supabase_url: str = st.secrets["SUPABASE_URL"]
    service_key = st.secrets["SUPABASE_SERVICE_KEY"]
except KeyError:
    st.error("خطأ في الإعداد: مفاتيح Supabase (URL أو SERVICE_KEY) مفقودة.")
    st.stop()
except Exception as e:
    st.error(f"خطأ في تحميل الإعدادات: {e}")
    st.stop()

# --- 2. الإتصال بـ Supabase (بمفتاح الخدمة) ---
# هذا العميل يتمتع بامتيازات مطلقة
try:
    admin_client: Client = create_client(supabase_url, service_key)
    users_table = admin_client.table(SUPABASE_TABLE_NAME)
except Exception as e:
    st.error(f"فشل اتصال مسؤول Supabase: {e}")
    st.stop()

# --- 3. التحقق من المسؤولية ---
# التحقق من أن المستخدم مسجل الدخول وأن بريده الإلكتروني يطابق ADMIN_EMAIL
if st.session_state.get('auth_status') != 'logged_in' or st.session_state.get('user_email') != ADMIN_EMAIL:
    st.error("وصول محظور. هذه الصفحة مخصصة للمسؤول فقط.")
    st.info(f"يجب تسجيل الدخول بالبريد الإلكتروني للمسؤول: `{ADMIN_EMAIL}`")
    st.stop()

# --- 4. دالة تحديث بيانات المستخدم (باستخدام مفتاح الخدمة) ---

def update_user_data_admin(email, data: dict):
    """
    تحديث بيانات المستخدم باستخدام client المسؤول (Service Key).
    تتم إعادة تشغيل التطبيق بعد التحديث.
    """
    try:
        response = admin_client.table(SUPABASE_TABLE_NAME).update(data).eq("email", email).execute()
        if response.data:
            # مسح الذاكرة المؤقتة للوظيفة الرئيسية لتحميل البيانات الجديدة
            get_all_users_securely.clear()
            st.success(f"تم تحديث بيانات {email} بنجاح!")
            time.sleep(0.5)
            st.experimental_rerun()
            return True
        return False
    except Exception as e:
        st.error(f"خطأ في التحديث: {e}")
        return False

# --- 5. دالة قراءة جميع المستخدمين (للتخزين المؤقت) ---

@st.cache_data(ttl=60)
def get_all_users_securely():
    """قراءة جميع المستخدمين باستخدام مفتاح الخدمة."""
    try:
        # نحن نستخدم admin_client الذي تم إعداده بالفعل بمفتاح الخدمة
        response = admin_client.table(SUPABASE_TABLE_NAME).select("*").execute()
        return [user for user in response.data if user['email'] != ADMIN_EMAIL]
    except Exception as e:
        st.error(f"فشل في استرداد قائمة المستخدمين: {e}")
        return []

# --- 6. واجهة المستخدم (UI) ---

st.title("👑 لوحة تحكم المسؤول (Admin Dashboard)")
st.markdown("---")

st.info(f"أنت مسجل الدخول كمسؤول رئيسي: **{ADMIN_EMAIL}**")

all_users = get_all_users_securely()

# --- الإحصائيات العامة ---
total_users = len(all_users)
total_bonus_requests = sum(user.get('bonus_questions', 0) for user in all_users)
successful_referrals = sum(1 for user in all_users if user.get('referred_by'))

col1, col2, col3 = st.columns(3)
col1.metric("إجمالي المستخدمين", total_users)
col2.metric("إجمالي طلبات المكافآت الموزعة", total_bonus_requests)
col3.metric("إجمالي الإحالات الناجحة", successful_referrals)

st.markdown("---")

# --- إدارة الامتيازات لكل مستخدم ---
st.subheader("إدارة امتيازات المستخدم")

if not all_users:
    st.write("لا يوجد مستخدمون مسجلون بعد (باستثناء المسؤول).")
else:
    for user_data in all_users:
        email = user_data['email']
        is_unlimited = user_data.get('is_unlimited', False)
        bonus = user_data.get('bonus_questions', 0)
        requests_used = user_data.get('requests_today', 0)
        
        max_total = MAX_REQUESTS + bonus
        status_text = "✨ استخدام غير محدود (VIP)" if is_unlimited else f"محدود ({requests_used}/{max_total})"
        
        
        with st.expander(f"**{email}** | الحالة: {status_text}", expanded=False):
            
            # Form لإدارة الامتيازات
            with st.form(key=f"form_update_{email}", clear_on_submit=False):
                
                st.caption(f"تمت الإحالة بواسطة: {user_data.get('referred_by', 'غير متوفر')}")
                
                # 1. الأسئلة الإضافية
                new_bonus = st.number_input(
                    "💰 عدد الأسئلة الإضافية الممنوحة:",
                    min_value=0,
                    value=bonus,
                    step=10,
                    key=f"bonus_{email}"
                )

                # 2. الوصول غير المحدود
                new_unlimited = st.checkbox(
                    "🔥 منح وصول غير محدود (VIP)",
                    value=is_unlimited,
                    key=f"unlimited_{email}"
                )
                
                # زر الإرسال
                submitted = st.form_submit_button("حفظ التغييرات", type="primary")

                if submitted:
                    data_to_update = {
                        'bonus_questions': int(new_bonus),
                        'is_unlimited': bool(new_unlimited)
                    }
                    update_user_data_admin(email, data_to_update)

