import io
import re
import base64
import pandas as pd
import pdfplumber
import streamlit as st

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
        /* 1. Background Image */
        .stApp {{
            {bg_css}
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        
        /* 2. Make the top Streamlit header completely transparent */
        [data-testid="stHeader"] {{
            background-color: transparent !important;
        }}
        
        /* 3. Floating, detached Content Box */
        [data-testid="stMainBlockContainer"] {{
            background-color: rgba(0, 0, 0, 0.85);
            border-radius: 25px !important;
            padding: 40px !important;
            max-width: 85% !important; /* Detaches the box from the left and right edges */
            margin: 70px auto 50px auto !important; /* Detaches from the top bar and centers it */
            box-shadow: 0 10px 25px rgba(0,0,0,0.7);
        }}

        /* 4. Sleek Tab Transition Animation */
        @keyframes slideFadeIn {{
            0% {{ opacity: 0; transform: translateY(15px); }}
            100% {{ opacity: 1; transform: translateY(0); }}
        }}
        
        [data-testid="stTabContent"], [data-testid="stMarkdownContainer"] {{
            animation: slideFadeIn 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
        }}
        
        /* 5. Style the top main tabs to spread across the screen */
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
# DICTIONARIES & HELPER FUNCTIONS
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
    if len(bank_words) > 0 and bank_words[0] == 'hfb':
        bank_words = ['housing', 'finance', 'bank']
    best_match, best_score = "", 0
    for key, code in SORT_CODES.items():
        key_words = re.findall(r'\w+', key.lower())
        match_count = 0
        for i in range(min(len(bank_words), len(key_words))):
            if bank_words[i] == key_words[i]: match_count += 1
            else: break
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
# TOOL 1: STANBIC GENERATOR LOGIC
# ==========================================
def render_stanbic_tool():
    st.header("Stanbic Excel upload generator")
    
    # Nested tabs for the specific steps of this tool
    step1, step2 = st.tabs(["Step 1: Extract PDFs", "Step 2: Format Upload"])
    
    with step1:
        st.write("Upload PDF files to extract payment data to excel. Download and verify this Excel before Step 2.")
        uploaded_pdfs = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)
        if st.button("Extract tables to Excel", type="primary"):
            if not uploaded_pdfs:
                st.warning("Please upload at least one PDF.")
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
                    clean_df["Amount"] = pd.to_numeric(clean_df["Amount"].astype(str).str.replace(",", "", regex=False), errors="coerce")
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer: clean_df.to_excel(writer, index=False)
                    st.success(f"Processed {len(uploaded_pdfs)} file(s)!")
                    st.download_button("Download extracted tables' Excel file", data=output.getvalue(), file_name="Payments.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                else:
                    st.error("No valid payment rows found.")

    with step2:
        st.write("Upload the verified Excel file from Step 1 to generate final Excel")
        uploaded_excel = st.file_uploader("Upload cleaned Excel", type=["xlsx", "xls"])
        if st.button("Generate final bank upload Excel", type="primary"):
            if not uploaded_excel:
                st.warning("Please upload the Excel file.")
            else:
                try:
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
                        st.download_button("Download Final Bank Upload Excel", data=output_2.getvalue(), file_name="Ready_For_Bank_Upload.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")

# ==========================================
# MAIN APP LAYOUT (MASTER TABS)
# ==========================================
st.title("My Workspace")

# navigation tabs
app_tabs = st.tabs(["🏦 Stanbic Generator", "📊 Future Tool 1", "⚙️ Future Tool 2"])

# Tab1: Stan app
with app_tabs[0]:
    render_stanbic_tool()

# Tab 2: Placeholder for the next tab
with app_tabs[1]:
    st.header("Future Tool 1")
    st.info("This space is reserved for your next awesome Python script.")
    st.write("You can drop in an invoice generator, payroll calculator, or anything else right here.")

# Tab 3: Another Placeholder
with app_tabs[2]:
    st.header("Future Tool 2")
    st.write("Your workspace is ready to grow.")
