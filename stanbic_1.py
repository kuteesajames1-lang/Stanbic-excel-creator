import io
import os
import re
import zipfile
import base64
import smtplib
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter
import streamlit as st
from email.message import EmailMessage
from email.utils import make_msgid

# ==========================================
# CONFIGURATION & CSS (Background + Transitions)
# ==========================================
st.set_page_config(page_title="My Workspace", layout="wide")

def apply_custom_styles(image_file):
    try:
        with open(image_file, "rb") as f:
            encoded_string = base64.b64encode(f.read()).decode()
            bg_css = f"background-image: url(data:image/jpeg;base64,{encoded_string});"
    except FileNotFoundError:
        bg_css = "background-color: #f0f2f6;"

    st.markdown(
        f"""
        <style>
        .stApp {{
            {bg_css}
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        [data-testid="stHeader"] {{
            background-color: transparent !important;
        }}
        [data-testid="stMainBlockContainer"] {{
            background-color: rgba(0, 0, 0, 0.85);
            border-radius: 25px !important;
            padding: 40px !important;
            max-width: 85% !important;
            margin: 70px auto 50px auto !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.7);
        }}
        @keyframes slideFadeIn {{
            0% {{ opacity: 0; transform: translateY(15px); }}
            100% {{ opacity: 1; transform: translateY(0); }}
        }}
        [data-testid="stTabContent"], [data-testid="stMarkdownContainer"] {{
            animation: slideFadeIn 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            display: flex;
            width: 100%;
            gap: 10px;
        }}
        .stTabs [data-baseweb="tab"] {{
            flex: 1;
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 10px 10px 0px 0px;
            padding-top: 15px;
            padding-bottom: 15px;
            display: flex;
            justify-content: center;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

apply_custom_styles("background.jpg")

# ==========================================
# TOOL 1: STANBIC HELPERS
# ==========================================
SORT_CODES = {
    'ABC Capital Bank': 660147, 'Absa Bank': 13447, 'Bank of Africa': 130147,
    'Bank of Baroda': 20147, 'Bank of India': 340147, 'Bank of': 990147,
    'Cairo Bank': 180147, 'Centenary Bank': 163047, 'Citibank': 220147,
    'DFCU Bank': 50147, 'Diamond Trust Bank': 190147, 'Ecobank': 290147,
    'Equity Bank': 300147, 'Exim Bank': 320147, 'Finance Trust Bank': 370147,
    'Guaranty Trust Bank': 650147, 'Housing Finance Bank': 230147,
    'I and M Bank': 110147, 'KCB Bank Uganda': 253047, 'NCBA Uganda': 360147,
    'Opportunity Bank': 610147, 'Pearl Bank': 560147, 'Post Bank': 560147,
    'Salaam Bank': 620147, 'Stanbic Bank': 40147, 'Standard Chartered Bank': 80147,
    'Tropical Bank': 60147, 'United Bank for Africa': 260147, 'Pride Bank': 40147,
}

def clean_text(text):
    if text is None: return ""
    return re.sub(r"\s+", " ", str(text)).strip()

def generate_narrative(source_file, member_name):
    if pd.isna(source_file) or not isinstance(source_file, str): return ""
    prefix = re.split(r'(?i)\s*PF\b', source_file)[0].strip()
    return f"{prefix} {member_name}"

def extract_sort_code(bank_details):
    if pd.isna(bank_details): return ""
    match = re.split(r'(?i)A/C\s*No', str(bank_details))
    if not match: return ""
    bank_name = match[0].strip()
    bank_words = re.findall(r'\w+', bank_name.lower())
    if len(bank_words) > 0 and bank_words[0] == 'hfb': bank_words = ['housing', 'finance', 'bank']
    best_match, best_score = "", 0
    for key, code in SORT_CODES.items():
        key_words = re.findall(r'\w+', key.lower())
        match_count = sum(1 for i in range(min(len(bank_words), len(key_words))) if bank_words[i] == key_words[i])
        required_matches = min(2, len(key_words))
        if match_count >= required_matches and match_count > best_score:
            best_score, best_match = match_count, code
    return str(best_match).zfill(6) if best_match else ""

def extract_account_number(bank_details):
    if pd.isna(bank_details): return ""
    match = re.search(r'(?i)A/C\s*No[^\d]*(\d+)', str(bank_details))
    if match: return match.group(1)
    digits = re.findall(r'\d+', str(bank_details))
    if digits: return max(digits, key=len)
    return ""

# ==========================================
# TOOL 2: EMAIL HELPERS
# ==========================================
def decode_weird_pdf_font(text):
    decoded_text = ""
    for char in text:
        code = ord(char)
        if 61440 <= code <= 61695: decoded_text += chr(code - 61440)
        else: decoded_text += char
    return decoded_text

def extract_details_from_pdf_bytes(pdf_bytes, filename):
    email_found, prs_found, last_name_found = None, None, "Client"
    
    try:
        clean_name = filename.upper().replace(".PDF", "").replace("DOA", "").strip()
        name_parts = clean_name.split()
        if len(name_parts) > 1: last_name_found = name_parts[1].title() 
        elif name_parts: last_name_found = name_parts[0].title() 
    except: pass

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        raw_text = "".join(page.get_text() for page in doc)
        doc.close()
        
        translated_text = decode_weird_pdf_font(raw_text)
        squashed_text = re.sub(r"\s+", "", translated_text)
        
        prs_match = re.search(r"\d{3}[/\\-]PRS[/\\-]\d+", squashed_text, re.IGNORECASE)
        if prs_match:
            prs_found = prs_match.group(0).upper() 
            squashed_text = squashed_text.replace(prs_match.group(0), " ")
            
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", squashed_text)
        if email_match: email_found = email_match.group(0)
    except Exception as e:
        st.error(f"Error reading {filename}: {e}")
        
    return email_found, prs_found, last_name_found

def send_email_with_attachment_bytes(sender_email, app_password, recipient_email, pdf_bytes, filename, last_name):
    try:
        msg = EmailMessage()
        msg['Subject'] = f"Policy Document for Review and Signature - {last_name}"
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Cc'] = [
    "anne.naisiko@icea.co.ug",
    'pensions@icea.co.ug'
]
        
        # Extract the first name from the email
        sender_first_name = sender_email.split('.')[0].capitalize()
        image_cid = make_msgid()
        
        # 3. Build the HTML email body
        html_body = f"""
        <html>
        <body>
            <p>Dear {last_name},</p>
            <p>Thank you for Choosing ICEA LION Life Assurance (Uganda) as your preferred insurer.<br>
            Attached are your policy documents for your review and signature. Kindly sign and return a copy to us at your earliest convenience for our records.<br>
            We appreciate your prompt attention to this matter and look forward to your response.</p>
            <p>Kind regards,<br>
            {sender_first_name}<br>
            Pensions</p>
            <br>
            <img src="cid:{image_cid[1:-1]}" alt="Signature Animation" width="350">
        </body>
        </html>
        """
        
        # Set a plain text fallback, then add the HTML version
        msg.set_content(f"Dear {last_name},\n\nPlease view this email in an HTML-compatible client.")
        msg.add_alternative(html_body, subtype='html')
        
        # 4. Read the GIF file and embed it inline
        try:
            with open("signature.gif", "rb") as img:
                msg.get_payload()[1].add_related(img.read(), 'image', 'gif', cid=image_cid)
        except FileNotFoundError:
            st.warning("signature.gif was not found. Email will send without the image.")
            
        # 5. Attach the merged PDF file
        msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=filename)

        # 6. Dispatch the email
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login(sender_email, app_password)
            smtp.send_message(msg)
            
        return True
    except Exception as e:
        st.error(f"SMTP Error for {recipient_email}: {e}") 
        return False
# ==========================================
# APP RENDERING LOGIC
# ==========================================
def render_stanbic_tool():
    st.header("Stanbic bank Excel generator")
    step1, step2 = st.tabs(["Step 1: Extract PDFs", "Step 2: Format Upload"])
    
    with step1:
        st.write("Upload PDF files to extract payment data tables.")
        uploaded_pdfs = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True, key="stanbic_pdfs")
        if st.button("Extract Tables to Excel", type="primary"):
            if not uploaded_pdfs: st.warning("Please upload at least one PDF.")
            else:
                all_extracted_data = []
                with st.spinner("Processing PDF files..."):
                    for pdf_file in uploaded_pdfs:
                        with pdfplumber.open(pdf_file) as pdf:
                            for page in pdf.pages:
                                tables = page.extract_tables() or page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
                                for table in tables:
                                    prev_spill, pend_prefix = "", ""
                                    for row in table:
                                        cells = [clean_text(c) for c in row if clean_text(c)]
                                        if not cells: continue
                                        if re.search(r"(?i)(particulars|employer\s*name|attn:|member\s*name|amount|prepared\s*by|approved\s*by|witnessed\s*by|\btotal\b|protecting)", " ".join(cells).lower()): continue
                                        if len(cells) == 1:
                                            if "bank" in cells[0].lower() or "a/c" in cells[0].lower(): pend_prefix = cells[0]
                                            continue
                                        if re.match(r"^\d+[\.\)]?$", cells[0]): cells.pop(0)
                                        if len(cells) < 3: continue
                                        
                                        member = cells[0]
                                        payee = cells[1] if len(cells) > 3 else cells[0]
                                        amount, bank = cells[-2], cells[-1]
                                        
                                        if not amount.replace(",", "").replace(".", "").isdigit(): continue
                                        if pend_prefix: bank, pend_prefix = f"{pend_prefix} {bank}", ""
                                        if re.match(r"^\d", bank) and prev_spill: bank, prev_spill = f"{prev_spill} {bank}", ""
                                        
                                        spill_match = re.search(r"([A-Za-z\s&]+Bank[\sA/CNo:]*)$", bank, re.IGNORECASE)
                                        if spill_match:
                                            prev_spill = spill_match.group(1).strip()
                                            bank = bank.replace(spill_match.group(0), "").strip()
                                        else: prev_spill = ""
                                        all_extracted_data.append({"Member Name": member, "Payee Name": payee, "Amount": amount, "Bank details": bank, "Source File": pdf_file.name})

                if all_extracted_data:
                    df = pd.DataFrame(all_extracted_data)
                    clean_df = df[["Member Name", "Payee Name", "Amount", "Bank details", "Source File"]].copy()
                    clean_df["Amount"] = clean_df.apply(lambda row: round(float(str(row['Amount']).replace(',', '')), 2), axis=1)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer: clean_df.to_excel(writer, index=False)
                    st.success(f"Processed {len(uploaded_pdfs)} file(s)!")
                    st.download_button("Download extracted Excel for payments", data=output.getvalue(), file_name="Payments.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                else: st.error("No valid payment rows found.")

    with step2:
        st.write("Upload the verified Excel file from Step 1 to generate the final excel.")
        uploaded_excel = st.file_uploader("Upload cleaned Excel", type=["xlsx", "xls"], key="stanbic_excel")
        if st.button("Generate final bank upload Excel", type="primary", key="stanbic_btn_2"):
            if not uploaded_excel: st.warning("Please upload the Excel file.")
            else:
                with st.spinner("Formatting records..."):
                    df = pd.read_excel(uploaded_excel, dtype=str)
                    final_data = []
                    for _, row in df.iterrows():
                        if pd.isna(row.get('Member Name')) or str(row.get('Member Name')).strip() == "": continue
                        final_data.append({
                            "Beneficiary Name": row['Payee Name'],
                            "Narrative": generate_narrative(row['Source File'], row['Member Name']),
                            "Sort Code": extract_sort_code(row['Bank details']),
                            "Account Number": extract_account_number(row['Bank details']),
                            "Amount": round(float(str(row['Amount']).replace(',', '')), 2),
                            "Address": "Kampala"
                        })
                    final_df = pd.DataFrame(final_data)[['Beneficiary Name', 'Narrative', 'Sort Code', 'Account Number', 'Amount', 'Address']]
                    output_2 = io.BytesIO()
                    with pd.ExcelWriter(output_2, engine='openpyxl') as writer: final_df.to_excel(writer, index=False)
                    st.success(f"Formatted {len(final_data)} valid transactions!")
                    st.download_button("Download Final Bank Upload Excel", data=output_2.getvalue(), file_name="Ready_for_bank_upload.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def render_email_dispatch_tool():
    st.header("Merge, Zip, process and send PRS deeds ")
    step1, step2 = st.tabs(["Step 1: Merge PDFs", "Step 2: Dispatch Emails"])

    with step1:
        st.write("Upload a specific PDF to merge to each of the Deeds downloaded from ILMS.")
        specific_pdf = st.file_uploader("Upload the specific PDF to attach", type=["pdf"])
        target_pdfs = st.file_uploader("Upload target PDFs", type=["pdf"], accept_multiple_files=True)
        
        if st.button("Merge and generate ZIP", type="primary"):
            if not specific_pdf or not target_pdfs:
                st.warning("Please upload both the specific PDF and the PDF deeds downloaded from the system.")
            else:
                with st.spinner("Merging PDFs..."):
                    zip_buffer = io.BytesIO()
                    reader_specific = PdfReader(specific_pdf)
                    
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for target in target_pdfs:
                            writer = PdfWriter()
                            reader_target = PdfReader(target)
                            
                            if len(reader_target.pages) > 0:
                                writer.add_page(reader_target.pages[0])
                            else: continue
                                
                            for page in reader_specific.pages:
                                writer.add_page(page)
                                
                            output_stream = io.BytesIO()
                            writer.write(output_stream)
                            zipf.writestr(target.name, output_stream.getvalue())
                            
                    st.success("All PDFs merged successfully!")
                    st.download_button("Download Merged PDFs (ZIP)", data=zip_buffer.getvalue(), file_name="Merged_PDFs.zip", mime="application/zip")

    with step2:
        st.write("Extract details from merged PDFs and dispatch emails automatically.")
        
        col1, col2 = st.columns(2)
        with col1:
            sender_email = st.selectbox(
                "Select Sender Email", 
                ["james.kuteesa@icea.co.ug", "edgar.kalyango@icea.co.ug", "esther.nakatemwa@icea.co.ug", "fortunate.biira@icea.co.ug"]
            )
        with col2:
            app_password = st.text_input("App Password", type="password", help="Enter the 16-character Google App Password")
            
        merged_pdfs = st.file_uploader("Upload Merged PDFs to Send", type=["pdf"], accept_multiple_files=True, key="dispatch_pdfs")
        
        if st.button("Process & Send Emails", type="primary"):
            if not app_password: st.warning("Please enter the App Password.")
            elif not merged_pdfs: st.warning("Please upload at least one PDF to send.")
            else:
                excel_data = []
                progress_bar = st.progress(0)
                
                with st.spinner("Sending emails..."):
                    for i, pdf in enumerate(merged_pdfs):
                        pdf_bytes = pdf.read()
                        email, prs_number, last_name = extract_details_from_pdf_bytes(pdf_bytes, pdf.name)
                        status = "Failed"
                        
                        if email and prs_number:
                            if send_email_with_attachment_bytes(sender_email, app_password, email, pdf_bytes, pdf.name, last_name):
                                status = "Sent"
                            else: status = "Failed to Send (SMTP Error)"
                        else:
                            if not email: status = "Missing Email"
                            if not prs_number: status = "Missing PRS Number"
                            if not email and not prs_number: status = "Missing Both"
                            
                        excel_data.append({"Filename": pdf.name, "PRS Number": prs_number or "Not Found", "Last Name": last_name or "Not Found", "Email": email or "Not Found", "Status": status})
                        progress_bar.progress((i + 1) / len(merged_pdfs))
                        
                df = pd.DataFrame(excel_data)
                report_buffer = io.BytesIO()
                with pd.ExcelWriter(report_buffer, engine="openpyxl") as writer: df.to_excel(writer, index=False)
                
                st.success("Email processing complete!")
                st.dataframe(df)
                st.download_button("Download Dispatch Report", data=report_buffer.getvalue(), file_name="Email_Dispatch_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==========================================
# MASTER TABS
# ==========================================
st.title("My Workspace")
app_tabs = st.tabs(["🏦 Stanbic Generator", "📧 PRS Deeds", "⚙️ Future Tool"])

with app_tabs[0]: render_stanbic_tool()
with app_tabs[1]: render_email_dispatch_tool()
with app_tabs[2]:
    st.header("Future Tool 2")
    st.write("Your workspace is ready to grow.")
