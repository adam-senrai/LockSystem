import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from supabase import create_client, Client
import os
import tempfile

# --------------------------------------------------------------------------
# Supabase Credentials
# --------------------------------------------------------------------------
DATABASE_URL = (
    "postgresql://postgres:6Bmkar6YMx@Q63C@db.nnaobjdfyzurnxbthfnb.supabase.co:5432/postgres"
)

# Supabase credentials
SUPABASE_URL = "https://nnaobjdfyzurnxbthfnb.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5u"
    "YW9iamRmeXp1cm54YnRoZm5iIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY1NTU5ODgsImV4"
    "cCI6MjA1MjEzMTk4OH0.QjepJKeumWt4gBpRxq97XwVm0TN1uN6GNt_AN3nhUWM"
)

# Initialize the Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --------------------------------------------------------------------------
# PostgreSQL Connection URL
# --------------------------------------------------------------------------
def get_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

# --------------------------------------------------------------------------
# Upload to Supabase
# --------------------------------------------------------------------------
def upload_to_supabase(image_file, wearer_id):
    try:
        bucket_name = "wearer-images"
        file_path = f"{wearer_id}.png"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            tmp_file.write(image_file.read())
            tmp_file_path = tmp_file.name

        supabase.storage.from_(bucket_name).upload(file_path, tmp_file_path)
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
        return public_url
    except Exception as e:
        st.error(f"Error during Supabase upload: {e}")
        return None
    finally:
        try:
            os.remove(tmp_file_path)
        except Exception as cleanup_error:
            st.warning(f"Error cleaning up temporary file: {cleanup_error}")

# --------------------------------------------------------------------------
# Streamlit App Title
# --------------------------------------------------------------------------
st.title("Remote Chastity Cage Control")

# --------------------------------------------------------------------------
# Role Selection
# --------------------------------------------------------------------------
role = st.radio("Select your role", ["Keyholder/Master", "Wearer/Sub"])

# --------------------------------------------------------------------------
# WEARER/SUB PORTAL
# --------------------------------------------------------------------------
if role == "Wearer/Sub":
    st.header("Wearer/Sub Portal")
    wearer_id = st.text_input("Enter your wearer ID", key="wearer_id")

    if st.button("Check Wearer ID"):
        conn = get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, locked, image_url, cashapp_tag,
                           expiration_date, keyholder_pass, sub_pass
                    FROM wearers
                    WHERE id = %s
                """, (wearer_id,))
                wearer = cur.fetchone()
            conn.close()

            if not wearer:
                st.info("This ID does not exist. You can create a new lock session.")
                st.session_state["wearer_status"] = "new"
                st.session_state["wearer_data"] = {}
            else:
                if wearer["locked"]:
                    now = datetime.now()
                    if wearer["expiration_date"] and now > wearer["expiration_date"]:
                        conn = get_connection()
                        if conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE wearers
                                    SET locked = FALSE,
                                        keyholder_pass = NULL,
                                        expiration_date = NULL
                                    WHERE id = %s
                                """, (wearer_id,))
                                conn.commit()
                            conn.close()

                        st.success("Your lock has expired. You are now unlocked.")
                        st.session_state["wearer_status"] = "unlocked"
                    else:
                        st.error("You are currently locked. Ask your master to unlock you.")
                        if wearer["expiration_date"]:
                            st.info(f"Your unlock date is: {wearer['expiration_date']}")
                        st.session_state["wearer_status"] = "locked"
                else:
                    st.warning("This ID exists and is currently unlocked.")
                    st.session_state["wearer_status"] = "unlocked"

                st.session_state["wearer_data"] = wearer

    wearer_status = st.session_state.get("wearer_status", None)
    wearer_data = st.session_state.get("wearer_data", {})

    if wearer_status == "new":
        image_file = st.file_uploader("Upload your picture", type=["png", "jpg", "jpeg"])
        cashapp_tag = st.text_input("Enter your CashApp Tag (optional):")
        sub_pass = st.text_input("Set a Sub Password", type="password")
        sub_pass_confirm = st.text_input("Confirm Sub Password", type="password")

        if image_file and st.button("Create Lock Session"):
            if not sub_pass or not sub_pass_confirm:
                st.error("Please enter and confirm your Sub Password.")
            elif sub_pass != sub_pass_confirm:
                st.error("Sub Passwords do not match. Please try again.")
            else:
                image_url = upload_to_supabase(image_file, wearer_id)
                if image_url:
                    conn = get_connection()
                    if conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO wearers (id, image_url, cashapp_tag, sub_pass)
                                VALUES (%s, %s, %s, %s)
                            """, (wearer_id, image_url, cashapp_tag, sub_pass))
                            conn.commit()
                        conn.close()
                    st.success("Lock session created successfully!")
                else:
                    st.error("Failed to upload image.")

    elif wearer_status == "unlocked":
        if not st.session_state.get("sub_pass_verified", False):
            sub_pass_for_view = st.text_input("Enter your Sub Password to view data:", type="password")
            if st.button("Verify Password"):
                if sub_pass_for_view == wearer_data.get("sub_pass", ""):
                    st.session_state["sub_pass_verified"] = True
                    st.success("Password verified! You can now view your data.")
                else:
                    st.error("Invalid password.")
        if st.session_state.get("sub_pass_verified", False):
            st.image(wearer_data.get("image_url"), caption="Uploaded Image")
