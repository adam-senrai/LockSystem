import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from supabase import create_client, Client
import os
import tempfile
import requests 
 
# --------------------------------------------------------------------------  
# Supabase Credentials
# --------------------------------------------------------------------------
DATABASE_URL = (
    "postgresql://postgres:6Bmkar6YMx@Q63C@db.nnaobjdfyzurnxbthfnb.supabase.co:5432/postgres" 
)

# Supabase credentials
SUPABASE_URL = "https://nnaobjdfyzurnxbthfnb.supabase.co"  # Replace with your project URL
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5uYW9iamRmeXp1cm54YnRoZm5iIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY1NTU5ODgsImV4cCI6MjA1MjEzMTk4OH0.QjepJKeumWt4gBpRxq97XwVm0TN1uN6GNt_AN3nhUWM"

# Initialize the Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --------------------------------------------------------------------------
# PostgreSQL Connection URL
# --------------------------------------------------------------------------
DATABASE_URL = (
    "postgresql://postgres.nnaobjdfyzurnxbthfnb:"
    "kuWHyHAJ1P3LrFmY@aws-0-us-west-1.pooler."
    "supabase.com:6543/postgres"
)

# --------------------------------------------------------------------------
# Database Connection
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
                        # Auto-unlock in DB, but do NOT display the image automatically
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
                        # Still locked
                        st.error("You are currently locked. Ask your master to unlock you.")
                        if wearer["expiration_date"]:
                            st.info(f"Your unlock date is: {wearer['expiration_date']}")
                        st.session_state["wearer_status"] = "locked"

                else:
                    # Unlocked in DB, but do NOT display the image yet
                    st.warning("This ID exists and is currently unlocked.")
                    st.session_state["wearer_status"] = "unlocked"

                # Store record in session state
                st.session_state["wearer_data"] = wearer

    wearer_status = st.session_state.get("wearer_status", None)
    wearer_data = st.session_state.get("wearer_data", {})

    # ----------------------------------------------------------------------
    # NEW -> Create a new lock session (Sub sets sub_pass)
    # ----------------------------------------------------------------------
    if wearer_status == "new":
        image_file = st.file_uploader("Upload your picture", type=["png", "jpg", "jpeg"])
        cashapp_tag = st.text_input(
            "Enter your CashApp Tag or a payment handle if you want Keyholders to confirm they know you."
        )
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

    # ----------------------------------------------------------------------
    # UNLOCKED -> Must confirm sub password before viewing or deleting
    # ----------------------------------------------------------------------
    elif wearer_status == "unlocked":
        # If we haven't already verified sub password, do it now
        if not st.session_state.get("sub_pass_verified", False):
            st.write("Please enter your sub password to see your image:")
            sub_pass_for_view = st.text_input("Sub Password", type="password", key="sub_pass_for_view")

            if st.button("Verify Password"):
                if sub_pass_for_view == wearer_data.get("sub_pass", ""):
                    st.session_state["sub_pass_verified"] = True
                    st.success("Password correct! You can now view your image and optionally delete your data.")
                else:
                    st.error("Invalid sub password.")

        # If sub password is verified, show the image (if any) and allow data deletion
        if st.session_state.get("sub_pass_verified", False):
            if wearer_data.get("image_url"):
                # ----------------------------
                # Add a cache-busting parameter
                # ----------------------------
                busted_url = f"{wearer_data['image_url']}?cachebuster={datetime.now().timestamp()}"  # <-- changed line
                st.image(busted_url, caption="Your Image")                                         # <-- changed line

            st.write("Enter your Sub Password again if you want to delete your data:")
            sub_pass_input = st.text_input("Sub Password", type="password", key="sub_pass_input_del")

            if st.button("Delete Existing Data"):
                if sub_pass_input == wearer_data.get("sub_pass", ""):
                    # Correct password -> proceed with deletion
                    conn = get_connection()
                    if conn:
                        bucket_name = "wearer-images"
                        file_path = f"{wearer_data['id']}.png"
                        try:
                            delete_response = supabase.storage.from_(bucket_name).remove([file_path])
                            if delete_response:
                                st.success("Image deleted from Supabase storage. Refresh to begin anew.")
                            else:
                                st.warning("Image may not have been deleted. Check Supabase storage.")
                        except Exception as e:
                            st.error(f"Error deleting image from Supabase: {e}")

                        # Delete from DB
                        try:
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM wearers WHERE id = %s", (wearer_data["id"],))
                                conn.commit()
                            st.success("Wearer data deleted from the database.")
                            st.session_state["wearer_status"] = None
                            st.session_state["wearer_data"] = {}
                            st.session_state["sub_pass_verified"] = False
                        except Exception as e:
                            st.error(f"Error deleting wearer data: {e}")
                        finally:
                            conn.close()
                else:
                    st.error("Invalid Sub Password. Data deletion not allowed.")

# --------------------------------------------------------------------------
# KEYHOLDER/MASTER PORTAL
# --------------------------------------------------------------------------
elif role == "Keyholder/Master":
    st.header("Keyholder/Master Portal")

    # Fetch all existing IDs for convenience
    all_ids = []
    conn = get_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM wearers ORDER BY id ASC")
            results = cur.fetchall()
            all_ids = [row["id"] for row in results]
        conn.close()

    # Provide a dropdown for existing Wearer IDs
    wearer_id_master = st.selectbox(
        "Select or type the Sub's ID you'd like to lock/manage:",
        options=[""] + all_ids,
        key="wearer_id_master"
    )

    if st.button("Lock/Manage Sub"):
        if not wearer_id_master:
            st.warning("Please select or type a valid Wearer/Sub ID.")
        else:
            conn = get_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT locked, keyholder_pass, expiration_date, cashapp_tag
                        FROM wearers
                        WHERE id = %s
                    """, (wearer_id_master,))
                    wearer = cur.fetchone()
                conn.close()

                if not wearer:
                    st.error("Wearer not found.")
                    st.session_state["keyholder_status"] = None
                else:
                    st.session_state["keyholder_status"] = wearer
                    st.session_state["newly_locked"] = False

    wearer = st.session_state.get("keyholder_status", None)

    if wearer:
        # If locked, skip cashapp confirmation, ask keyholder pass
        if wearer["locked"]:
            st.write("This wearer is already locked by a Master. Please enter the Keyholder password to manage them.")

            if not st.session_state.get("valid_keyholder_pass", False):
                keyholder_pass_input = st.text_input(
                    "Enter the Keyholder Pass you created when you locked the sub.",
                    type="password",
                    key="keyholder_pass_input"
                )

                if st.button("Submit Keyholder Pass"):
                    if keyholder_pass_input == wearer["keyholder_pass"]:
                        st.success("Access granted.")
                        st.session_state["valid_keyholder_pass"] = True
                    else:
                        st.error("Invalid keyholder pass. Access denied.")

            # If valid pass, show management
            if st.session_state.get("valid_keyholder_pass", False):
                st.subheader("Manage Wearer/Sub")
                st.info(f"Current Unlock Date: {wearer['expiration_date']}")

                add_time = st.number_input("Add time (in hours)", step=1, min_value=0, key="add_time")
                remove_time = st.number_input("Remove time (in hours)", step=1, min_value=0, key="remove_time")

                if st.button("Update Unlock Date"):
                    new_date = wearer["expiration_date"] or datetime.now()
                    new_date += timedelta(hours=add_time)
                    new_date -= timedelta(hours=remove_time)

                    conn = get_connection()
                    if conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE wearers
                                SET expiration_date = %s
                                WHERE id = %s
                            """, (new_date, wearer_id_master))
                            conn.commit()
                        conn.close()

                    st.success(f"Unlock date updated to: {new_date}")
                    wearer["expiration_date"] = new_date
                    st.session_state["keyholder_status"] = wearer

                if st.button("Unlock Wearer/Sub"):
                    conn = get_connection()
                    if conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE wearers
                                SET locked = FALSE,
                                    keyholder_pass = NULL,
                                    expiration_date = NULL
                                WHERE id = %s
                            """, (wearer_id_master,))
                            conn.commit()
                        conn.close()

                    st.success("Wearer unlocked successfully!")
                    wearer["locked"] = False
                    wearer["expiration_date"] = None
                    wearer["keyholder_pass"] = None
                    st.session_state["keyholder_status"] = wearer

        # If not locked, confirm CashApp tag and lock
            else:
                st.write("**Confirm the Sub's CashApp tag to proceed (if applicable).**")
                entered_cashapp_tag = st.text_input(
                    "Enter the Wearer's CashApp tag to confirm identity (or leave blank if not set).",
                    key="confirm_cashapp_tag"
                )
            
                if st.button("Confirm Sub Identity"):
                    if not wearer["cashapp_tag"]:  # If no CashApp tag was set by the sub
                        if entered_cashapp_tag.strip() == "":
                            st.success("No CashApp tag was set, identity confirmed.")
                            st.session_state["cashapp_confirmed"] = True
                        else:
                            st.warning("This wearer has no CashApp tag on file, and the entered tag is ignored.")
                            st.session_state["cashapp_confirmed"] = True
                    else:  # If a CashApp tag exists, validate it
                        if entered_cashapp_tag.strip().lower() == wearer["cashapp_tag"].strip().lower():
                            st.success("CashApp tag matched! You can proceed.")
                            st.session_state["cashapp_confirmed"] = True
                        else:
                            st.error("CashApp tag mismatch. You cannot lock this sub.")
                            st.session_state["cashapp_confirmed"] = False
            
                if st.session_state.get("cashapp_confirmed", False):
                    st.warning("This wearer/sub is currently not locked.")
                    new_pass = st.text_input("Enter a password to lock the sub.", type="password")
                    confirm_pass = st.text_input("Confirm the password", type="password")
            
                    if st.button("Lock Wearer/Sub"):
                        if not new_pass or not confirm_pass:
                            st.error("Please enter and confirm the password.")
                        elif new_pass != confirm_pass:
                            st.error("Passwords do not match. Try again.")
                        else:
                            future_date = datetime.now() + timedelta(days=1)
                            conn = get_connection()
                            if conn:
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        UPDATE wearers
                                        SET locked = TRUE,
                                            keyholder_pass = %s,
                                            expiration_date = %s
                                        WHERE id = %s
                                    """, (new_pass, future_date, wearer_id_master))
                                    conn.commit()
                                conn.close()
            
                            st.success(f"Wearer locked successfully! Keyholder pass: {new_pass}")
                            st.warning("Please screenshot or copy this pass as it won't be shown again.")
                            wearer["locked"] = True
                            wearer["keyholder_pass"] = new_pass
                            wearer["expiration_date"] = future_date
                            st.session_state["keyholder_status"] = wearer
                            # Immediately allow management
                            st.session_state["valid_keyholder_pass"] = True
                     if wearer["locked"] and st.session_state.get("valid_keyholder_pass", False):
                         st.subheader("Manage Wearer/Sub")
                         st.info(f"Current Unlock Date: {wearer['expiration_date']}")
     
                         add_time = st.number_input("Add time (in hours)", step=1, min_value=0, key="add_time2")
                         remove_time = st.number_input("Remove time (in hours)", step=1, min_value=0, key="remove_time2")
     
                         if st.button("Update Unlock Date", key="update_unlock_date_newly_locked"):
                             new_date = wearer["expiration_date"] or datetime.now()
                             new_date += timedelta(hours=add_time)
                             new_date -= timedelta(hours=remove_time)
     
                             conn = get_connection()
                             if conn:
                                 with conn.cursor() as cur:
                                     cur.execute("""
                                         UPDATE wearers
                                         SET expiration_date = %s
                                         WHERE id = %s
                                     """, (new_date, wearer_id_master))
                                     conn.commit()
                                 conn.close()
     
                             st.success(f"Unlock date updated to: {new_date}")
                             wearer["expiration_date"] = new_date
                             st.session_state["keyholder_status"] = wearer

                    if st.button("Unlock Wearer/Sub", key="unlock_newly_locked"):
                        conn = get_connection()
                        if conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE wearers
                                    SET locked = FALSE,
                                        keyholder_pass = NULL,
                                        expiration_date = NULL
                                    WHERE id = %s
                                """, (wearer_id_master,))
                                conn.commit()
                            conn.close()

                        st.success("Wearer unlocked successfully!")
                        wearer["locked"] = False
                        wearer["expiration_date"] = None
                        wearer["keyholder_pass"] = None
                        st.session_state["keyholder_status"] = wearer
