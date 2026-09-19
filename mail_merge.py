import os
import io
import smtplib
import pandas as pd
import streamlit as st
from email.message import EmailMessage
from email.utils import make_msgid

def render_mail_merge_tool():
    st.header("Universal Mail Merge")
    st.write("Upload an Excel contact list, map your columns, and send mass emails with grouped attachments.")
    
    # 1. Downloadable Template Section
    try:
        with open("Template.xlsx", "rb") as template_file:
            st.download_button(
                label="📥 Download Excel Template",
                data=template_file,
                file_name="Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Download the standard Excel template for reference."
            )
    except FileNotFoundError:
        st.info("💡 Note: Upload 'Template.xlsx' to your GitHub repository to enable the download button.")

    st.divider()

    # 2. Data Upload & Mapping
    st.subheader("1. Data & Column Mapping")
    contacts_file = st.file_uploader("Upload Contacts (Excel)", type=["xlsx", "xls"])
    
    if contacts_file:
        df = pd.read_excel(contacts_file)
        columns = df.columns.tolist()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            email_col = st.selectbox("Column containing Email Addresses:", columns)
        with col2:
            match_col = st.selectbox("Column to match Attachment Names:", columns, help="The exact file name (without .pdf) must match this column.")
        with col3:
            scheme_col = st.selectbox("Column containing Scheme Name:", columns, help="This will be appended to the end of the subject line.")
            
        st.divider()
        
        # 3. Email Configuration
        st.subheader("2. Email Configuration")
        c1, c2 = st.columns(2)
        with c1:
            sender_email = st.text_input("Sender Email Address", placeholder="e.g., james.kuteesa@icea.co.ug")
        with c2:
            app_password = st.text_input("App Password", type="password")
            
        base_subject = st.text_input("Email Subject Base", placeholder="e.g., Interest Declaration 2023")
        email_body = st.text_area("Email Body (Plain Text)", height=150, placeholder="Type your email message here. The signature and GIF will be added automatically.")
        
        st.divider()
        
        # 4. Attachments Upload
        st.subheader("3. Upload Attachments")
        st.write("Upload groups of attachments. If files from different groups share the exact same name (matching the column selected above), they will be attached to the same email.")
        
        att_col1, att_col2, att_col3 = st.columns(3)
        with att_col1:
            group_1 = st.file_uploader("Attachment Group 1", accept_multiple_files=True)
        with att_col2:
            group_2 = st.file_uploader("Attachment Group 2", accept_multiple_files=True)
        with att_col3:
            group_3 = st.file_uploader("Attachment Group 3", accept_multiple_files=True)
            
        # Combine all uploaded files into one list
        all_attachments = (group_1 or []) + (group_2 or []) + (group_3 or [])
        
        st.divider()
        
        # 5. Dispatch Logic
        if st.button("🚀 Run Mail Merge", type="primary"):
            if not all([sender_email, app_password, base_subject, email_body]):
                st.warning("Please fill in the sender email, app password, subject, and body.")
            elif not all_attachments:
                st.warning("Please upload at least one attachment.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Extract first name for sign-off (e.g., james.kuteesa -> James)
                sender_first_name = sender_email.split('@')[0].split('.')[0].capitalize()
                
                success_count = 0
                error_count = 0
                
                with st.spinner("Dispatching emails..."):
                    for index, row in df.iterrows():
                        recipient_email = str(row[email_col]).strip()
                        match_identifier = str(row[match_col]).strip()
                        scheme_name = str(row[scheme_col]).strip()
                        
                        # Skip if no valid email
                        if pd.isna(recipient_email) or "@" not in recipient_email:
                            continue
                            
                        # Find all attachments that exactly match the identifier (ignoring file extension)
                        matched_files = []
                        for file in all_attachments:
                            file_base_name = os.path.splitext(file.name)[0].strip()
                            if file_base_name.lower() == match_identifier.lower():
                                matched_files.append(file)
                                
                        if not matched_files:
                            # Skip if no attachments are found for this user
                            error_count += 1
                            continue
                            
                        try:
                            msg = EmailMessage()
                            # Construct dynamic subject
                            msg['Subject'] = f"{base_subject} - {scheme_name}"
                            msg['From'] = sender_email
                            msg['To'] = recipient_email
                            
                            image_cid = make_msgid()
                            
                            # Format Body (Converting newlines to HTML breaks)
                            formatted_body_html = email_body.replace('\n', '<br>')
                            
                            html_content = f"""
                            <html>
                            <body>
                                <p>{formatted_body_html}</p>
                                <p>Kind regards,<br>
                                {sender_first_name}<br>
                                Pensions</p>
                                <br>
                                <img src="cid:{image_cid[1:-1]}" alt="Signature" width="350">
                            </body>
                            </html>
                            """
                            
                            msg.set_content("Please view this email in an HTML-compatible client.")
                            msg.add_alternative(html_content, subtype='html')
                            
                            # Embed GIF
                            try:
                                with open("signature.gif", "rb") as img:
                                    msg.get_payload()[1].add_related(img.read(), 'image', 'gif', cid=image_cid)
                            except FileNotFoundError:
                                pass # Sends without image if missing
                                
                            # Attach all matched files
                            for file in matched_files:
                                file.seek(0)
                                msg.add_attachment(
                                    file.read(), 
                                    maintype='application', 
                                    subtype='octet-stream', 
                                    filename=file.name
                                )
                                
                            # Send Email
                            with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
                                smtp.starttls()
                                smtp.login(sender_email, app_password)
                                smtp.send_message(msg)
                                
                            success_count += 1
                            
                        except Exception as e:
                            st.error(f"Failed to send to {recipient_email}: {str(e)}")
                            error_count += 1
                            
                        # Update progress bar
                        progress_bar.progress((index + 1) / len(df))
                        
                progress_bar.empty()
                st.success(f"Mail merge complete! Successfully sent: {success_count} | Skipped/Failed: {error_count}")
