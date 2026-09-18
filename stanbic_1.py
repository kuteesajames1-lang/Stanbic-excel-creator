import io
import re
import pandas as pd
import pdfplumber
import streamlit as st


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


st.set_page_config(page_title="PV Extractor", layout="centered")
st.title("PV Table Extractor")

# Web file uploader replacing Tkinter folder picker
uploaded_files = st.file_uploader(
    "Upload PDF files", type=["pdf"], accept_multiple_files=True
)

if st.button("Extract Tables to Excel", type="primary"):
    if not uploaded_files:
        st.warning("Please upload at least one PDF file.")
    else:
        all_extracted_data = []

        with st.spinner("Processing PDF files..."):
            for pdf_file in uploaded_files:
                with pdfplumber.open(pdf_file) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        if not tables:
                            tables = page.extract_tables(
                                {
                                    "vertical_strategy": "text",
                                    "horizontal_strategy": "text",
                                }
                            )

                        for table in tables:
                            previous_bank_spill = ""
                            pending_bank_prefix = ""

                            for row in table:
                                cells = [
                                    clean_text(c) for c in row if clean_text(c)
                                ]
                                if not cells:
                                    continue

                                combined_row = " ".join(cells).lower()
                                if re.search(
                                    r"(?i)(particulars|employer\s*name|attn:|member\s*name|amount|prepared\s*by|approved\s*by|witnessed\s*by|\btotal\b|protecting)",
                                    combined_row,
                                ):
                                    continue

                                if len(cells) == 1:
                                    if (
                                        "bank" in cells[0].lower()
                                        or "a/c" in cells[0].lower()
                                    ):
                                        pending_bank_prefix = cells[0]
                                    continue

                                if re.match(r"^\d+[\.\)]?$", cells[0]):
                                    cells.pop(0)

                                if len(cells) < 3:
                                    continue

                                member = cells[0]
                                payee = (
                                    cells[1] if len(cells) > 3 else cells[0]
                                )
                                amount = cells[-2]
                                bank = cells[-1]

                                amount_check = amount.replace(",", "").replace(
                                    ".", ""
                                )
                                if not amount_check.isdigit():
                                    continue

                                if pending_bank_prefix:
                                    bank = f"{pending_bank_prefix} {bank}"
                                    pending_bank_prefix = ""

                                if (
                                    re.match(r"^\d", bank)
                                    and previous_bank_spill
                                ):
                                    bank = f"{previous_bank_spill} {bank}"
                                    previous_bank_spill = ""

                                spill_match = re.search(
                                    r"([A-Za-z\s&]+Bank[\sA/CNo:]*)$",
                                    bank,
                                    re.IGNORECASE,
                                )
                                if spill_match:
                                    previous_bank_spill = spill_match.group(
                                        1
                                    ).strip()
                                    bank = bank.replace(
                                        spill_match.group(0), ""
                                    ).strip()
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
            target_cols = [
                "Member Name",
                "Payee Name",
                "Amount",
                "Bank details",
                "Source File",
            ]
            clean_df = df[target_cols].copy()
            clean_df["Amount"] = (
                clean_df["Amount"].astype(str).str.replace(",", "", regex=False)
            )
            clean_df["Amount"] = pd.to_numeric(
                clean_df["Amount"], errors="coerce"
            )

            # Export to Excel buffer for browser download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                clean_df.to_excel(writer, index=False)

            st.success(f"Successfully processed {len(uploaded_files)} file(s)!")
            st.download_button(
                label="Download Clean Bank Upload Excel",
                data=output.getvalue(),
                file_name="Clean_Bank_Upload.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.error("No valid payment rows were found in the uploaded PDFs.")