import io
import re
import pandas as pd
import pdfplumber
import base64
import streamlit as st

# ==========================================
# CONFIGURATION & DICTIONARIES
# ==========================================
st.set_page_config(page_title="PV & Bank Upload Extractor", layout="centered")
def set_background(image_file):
    image_file="background.jpg"
    with open(image_file, "rb") as f:
        encoded_string = base64.b64encode(f.read()).decode()
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url(data:image/jpeg;base64,{encoded_string});
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
set_background("background.jpg")
st.title("Stanbic Bank Upload Generator")

# Sort codes ported from stan2.py
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
    'DTB Bank': 190147
}

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def clean_text(text):
    if text is None: return ""
    return re.sub(r"\s+", " ", str(text)).strip()

def generate_narrative(source_file, member_name):
    if pd.isna(source_file) or not isinstance(source_file, str):
        return ""
    prefix = re.split(r'(?i)\s*PF\b', source_file)[0].strip()
    return f"{prefix}_{member_name}"

def extract_sort_code(bank_details):
    if pd.isna(bank_details): return ""
    match = re.split(r'(?i)A/C\s*No', str(bank_details))
    if not match: return ""
        
    bank_name = match[0].strip()
    bank_words = re.findall(r'\w+', bank_name.lower())
    
    if len(bank_words) > 0 and bank_words[0] == 'hfb':
        bank_words = ['housing', 'finance', 'bank']
        
    best_match = ""
    best_score = 0
    
    for key, code in SORT_CODES.items():
        key_words = re.findall(r'\w+', key.lower())
        match_count = 0
        for i in range(min(len(bank_words), len(key_words))):
            if bank_words[i] == key_words[i]:
                match_count += 1
            else:
                break
                
        required_matches = min(2, len(key_words))
        if match_count >= required_matches and match_count > best_score:
            best_score = match_count
            best_match = code
            
    return str(best_match).zfill(6) if best_match else ""

def extract_account_number(bank_details):
    if pd.isna(bank_details): return ""
    match = re.search(r'(?i)A/C\s*No[^\d]*(\d+)', str(bank_details))
    if match: return match.group(1)
    digits = re.findall(r'\d+', str(bank_details))
    if digits: return max(digits, key=len)
    return ""

# ==========================================
# APP LAYOUT (TABS)
# ==========================================
tab1, tab2 = st.tabs(["Step 1: Extract PDFs to Excel", "Step 2: Format for Bank Upload"])

# --- TAB 1: PDF EXTRACTION ---
with tab1:
    st.header("1. Extract Payment Vouchers")
    st.write("Upload PDF files to extract raw payment data into an Excel sheet. You must download and verify this sheet before moving to Step 2.")
    
    uploaded_pdfs = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Extract Tables to Excel", type="primary"):
        if not uploaded_pdfs:
            st.warning("Please upload at least one PDF file.")
        else:
            all_extracted_data = []
            with st.spinner("Processing PDF files..."):
                for pdf_file in uploaded_pdfs:
                    with pdfplumber.open(pdf_file) as pdf:
                        for page in pdf.pages:
                            tables = page.extract_tables()
                            if not tables:
                                tables = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
                            
                            for table in tables:
                                previous_bank_spill = ""
                                pending_bank_prefix = ""

                                for row in table:
                                    cells = [clean_text(c) for c in row if clean_text(c)]
                                    if not cells: continue

                                    combined_row = " ".join(cells).lower()
                                    if re.search(r"(?i)(particulars|employer\s*name|attn:|member\s*name|amount|prepared\s*by|approved\s*by|witnessed\s*by|\btotal\b|protecting)", combined_row):
                                        continue

                                    if len(cells) == 1:
                                        if "bank" in cells[0].lower() or "a/c" in cells[0].lower():
                                            pending_bank_prefix = cells[0]
                                        continue

                                    if re.match(r"^\d+[\.\)]?$", cells[0]): cells.pop(0)
                                    if len(cells) < 3: continue

                                    member = cells[0]
                                    payee = cells[1] if len(cells) > 3 else cells[0]
                                    amount = cells[-2]
                                    bank = cells[-1]

                                    amount_check = amount.replace(",", "").replace(".", "")
                                    if not amount_check.isdigit(): continue

                                    if pending_bank_prefix:
                                        bank = f"{pending_bank_prefix} {bank}"
                                        pending_bank_prefix = ""

                                    if re.match(r"^\d", bank) and previous_bank_spill:
                                        bank = f"{previous_bank_spill} {bank}"
                                        previous_bank_spill = ""

                                    spill_match = re.search(r"([A-Za-z\s&]+Bank[\sA/CNo:]*)$", bank, re.IGNORECASE)
                                    if spill_match:
                                        previous_bank_spill = spill_match.group(1).strip()
                                        bank = bank.replace(spill_match.group(0), "").strip()
                                    else:
                                        previous_bank_spill = ""

                                    all_extracted_data.append({
                                        "Member Name": member,
                                        "Payee Name": payee,
                                        "Amount": amount,
                                        "Bank details": bank,
                                        "Source File": pdf_file.name,
                                    })

            if all_extracted_data:
                df = pd.DataFrame(all_extracted_data)
                target_cols = ["Member Name", "Payee Name", "Amount", "Bank details", "Source File"]
                clean_df = df[target_cols].copy()
                clean_df["Amount"] = clean_df["Amount"].astype(str).str.replace(",", "", regex=False)
                clean_df["Amount"] = pd.to_numeric(clean_df["Amount"], errors="coerce")

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    clean_df.to_excel(writer, index=False)

                st.success(f"Successfully processed {len(uploaded_pdfs)} file(s)!")
                st.download_button(
                    label="Download Raw Extracted Excel",
                    data=output.getvalue(),
                    file_name="Clean_Bank_Upload.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.error("No valid payment rows were found.")

# --- TAB 2: EXCEL FORMATTING ---
with tab2:
    st.header("2. Format For Stanbic Bank")
    st.write("Upload the verified Excel file downloaded from Step 1. The system will format account numbers, map bank sort codes, and generate narratives.")
    
    uploaded_excel = st.file_uploader("Upload Cleaned Excel", type=["xlsx", "xls"])
    
    if st.button("Generate Final Bank Upload", type="primary"):
        if not uploaded_excel:
            st.warning("Please upload the Excel file from Step 1.")
        else:
            try:
                with st.spinner("Formatting records..."):
                    df = pd.read_excel(uploaded_excel, dtype=str)
                    
                    required_cols = ['Member Name', 'Payee Name', 'Amount', 'Bank details', 'Source File']
                    for col in required_cols:
                        if col not in df.columns:
                            st.error(f"Missing required column: '{col}'[cite: 4]")
                            st.stop()

                    final_data = []

                    for index, row in df.iterrows():
                        if pd.isna(row['Member Name']) or str(row['Member Name']).strip() == "":
                            continue

                        final_data.append({
                            "Beneficiary Name": row['Payee Name'],
                            "Narrative": generate_narrative(row['Source File'], row['Member Name']),
                            "Sort Code": extract_sort_code(row['Bank details']),
                            "Account Number": extract_account_number(row['Bank details']),
                            "Amount": row['Amount'],
                            "Address": "Kampala" 
                        })

                    final_df = pd.DataFrame(final_data)
                    output_columns = ['Beneficiary Name', 'Narrative', 'Sort Code', 'Account Number', 'Amount', 'Address']
                    final_df = final_df[output_columns]

                    output_2 = io.BytesIO()
                    with pd.ExcelWriter(output_2, engine='openpyxl') as writer:
                        final_df.to_excel(writer, index=False)

                    st.success(f"Successfully formatted {len(final_data)} valid transactions!")
                    st.download_button(
                        label="Download Final Bank Upload Excel",
                        data=output_2.getvalue(),
                        file_name="Ready_For_Bank_Upload.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
