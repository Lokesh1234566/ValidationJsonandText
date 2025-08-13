import fitz  # PyMuPDF
import os
import re
import json
from utils import (
    get_pdf_files,
    extract_and_read_pdf_text,
    extract,
    validate_json_vs_text,
)

# --- Dummy column_boxes fallback if missing ---
try:
    from multicolumn import column_boxes
except ImportError:

    def column_boxes(page, footer_margin=50, no_image_text=True):
        return [page.rect]  # Use full page as fallback


# Directories
input_dir = "./allinvoices"
output_dir_txt = "infinititextfile"
output_dir_json = "infinitijsonfile"
validation_output_dir = "infinitivalidatejsontext"
file_prefix = "inf"
file_names = get_pdf_files(input_dir, file_prefix)

# Create output directories if they don't exist
os.makedirs(output_dir_txt, exist_ok=True)
os.makedirs(output_dir_json, exist_ok=True)
os.makedirs(validation_output_dir, exist_ok=True)


# -----------------------------
# MAIN LOOP FOR ALL PDFs
# -----------------------------
for pdf_path in file_names:
    base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    txt_file_path = os.path.join(output_dir_txt, f"{base_filename}.txt")
    json_file_path = os.path.join(output_dir_json, f"{base_filename}.json")

    try:
        text = extract_and_read_pdf_text(pdf_path, txt_file_path, column_boxes)

        lines = [line.strip() for line in text.splitlines()]

        # Supplier Details
        supplier_details = {
            "name": extract(r"^(INFINITI ENGINEERS PRIVATE LIMITED)", text),
            "address": extract(
                r"INFINITI ENGINEERS PRIVATE LIMITED\n(.+?\n.+?\n.+?)\n", text
            ).replace("\n", ", "),
            "phone": extract(r"PH:\s*(.+)", text),
            "pan": extract(r"PAN NO:\s*(\S+)", text),
            "gstin_uin": extract(r"GSTIN/UIN:\s*(\S+)", text),
            "state_name": extract(r"State Name\s*:\s*(.+?),\s*Code\s*:\s*\d+", text),
            "state_code": extract(r"State Name\s*:\s*.+?,\s*Code\s*:\s*(\d+)", text),
            "email": extract(r"E-Mail\s*:\s*(.+)", text),
        }

        # Buyer Details
        buyer_name = extract(r"Buyer\s*\n([^\n]+)", text)
        buyer_address = extract(
            rf"Buyer\s*\n{re.escape(buyer_name)}\n(.+\n.+\n.+)", text, ""
        ).replace("\n", ", ")
        buyer_details = {
            "name": buyer_name,
            "address": buyer_address,
            "gstin_uin": extract(r"GSTIN/UIN\s*:\s*(\S+)", text),
            "state_name": extract(r"State Name\s*:\s*(.+?), Code\s*:\s*\d+", text),
            "state_code": extract(r"State Name\s*:\s*.+?, Code\s*:\s*(\d+)", text),
        }

        # Invoice Details
        invoice_keys = [
            "Invoice No.",
            "Delivery Note",
            "Supplier’s Ref.",
            "Buyer’s Order No.",
            "Despatch Document No.",
            "Despatched through",
            "Dated",
            "Mode/Terms of Payment",
            "Other Reference(s)",
            "Delivery Note Date",
            "Destination",
            "Terms of Delivery",
        ]

        invoice_details = {}
        for i, line in enumerate(lines):
            if line in invoice_keys:
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if next_line.strip() in invoice_keys or not next_line.strip():
                    invoice_details[line.rstrip(".")] = ""
                else:
                    invoice_details[line.rstrip(".")] = next_line.strip()

        # Line Items
        line_items = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if "RENTAL OF LAPTOP" in line:
                try:
                    header = lines[i]

                    hsn = re.search(r"(\d{8})", header)
                    qty = re.search(r"(\d+)\s+NOS", header)
                    rate = re.search(r"NOS\.\s+([\d,]+\.\d{2})", header)
                    amount = re.findall(r"([\d,]+\.\d{2})", header)
                    per = re.search(r"\b(NOS)\b", header)

                    desc_block_lines = []
                    for offset in range(1, 6):
                        if i + offset < len(lines):
                            desc_block_lines.append(lines[i + offset].strip())
                    full_desc = " ".join(desc_block_lines).strip()

                    line_items.append(
                        {
                            "Description of Goods": full_desc,
                            "HSN/SAC": hsn.group(1) if hsn else "",
                            "Quantity": qty.group(1) if qty else "",
                            "Rate": rate.group(1) if rate else "",
                            "per": per.group(1) if per else "",
                            "Disc. %": "",
                            "Amount": amount[-1] if amount else "",
                        }
                    )

                    i += 6
                except Exception as e:
                    print(f"Item parsing error at line {i}: {e}")
                    i += 1
            else:
                i += 1

        # Tax Summary
        tax_summary = {
            "SGST Rate (%)": extract(r"SGST\s*@\s*(\d+)%", text),
            "SGST Amount": extract(
                r"SGST\s*@\s*\d+%\s*\d+\s*%\s*([\d,]+\.\d{2})", text
            ),
            "CGST Rate (%)": extract(r"CGST\s*@\s*(\d+)%", text),
            "CGST Amount": extract(
                r"CGST\s*@\s*\d+%\s*\d+\s*%\s*([\d,]+\.\d{2})", text
            ),
        }

        # Totals
        totals = {
            "Total Quantity": extract(r"Total\s+(\d+)\s+NOS", text),
            "Total Amount": extract(
                r"Total\s+\d+\s+NOS\.\s+[^\d]*([\d,]+\.\d{2})", text
            ),
        }

        # Amount in words
        amount_chargeable_words = ""
        for i, line in enumerate(lines):
            if "Amount Chargeable (in words)" in line:
                amount_chargeable_words = (
                    lines[i + 1].strip() if i + 1 < len(lines) else ""
                )
                break

        # HSN Summary
        hsn_summary = []
        hsn_blocks = re.findall(
            r"(\d{6,8})\s+([\d,]+\.\d{2})\s+([\d.]+)%\s+([\d,]+\.\d{2})\s+([\d.]+)%\s+([\d,]+\.\d{2})",
            text,
        )
        for hsn, taxable_val, cgst_rate, cgst_amt, sgst_rate, sgst_amt in hsn_blocks:
            total_tax_amt = f"{(float(cgst_amt.replace(',', '')) + float(sgst_amt.replace(',', ''))):,.2f}"
            hsn_summary.append(
                {
                    "HSN/SAC": hsn,
                    "Taxable Value": taxable_val,
                    "Central Tax Rate": f"{cgst_rate}%",
                    "Central Tax Amount": cgst_amt,
                    "State Tax Rate": f"{sgst_rate}%",
                    "State Tax Amount": sgst_amt,
                    "Total Tax Amount": total_tax_amt,
                }
            )

        # Bank details
        bank_line = extract(r"Bank Name\s*:\s*(.+)", text)
        bank_name, account_number = "", ""
        if bank_line:
            match = re.match(r"(.+?)\s*\((\d{10,20})\)", bank_line)
            if match:
                bank_name, account_number = match.groups()
            else:
                bank_name = bank_line

        branch_ifsc = extract(r"Branch\s*&\s*IFS\s*Code\s*:\s*(.+)", text)
        if not branch_ifsc:
            branch = extract(r"Branch\s*:\s*(.+)", text)
            ifsc = extract(r"IFSC\s*:\s*(\S+)", text)
            branch_ifsc = f"{branch}, {ifsc}" if branch and ifsc else ifsc

        bank_details = {
            "Bank Name": bank_name,
            "Account Number": account_number,
            "Branch_IFSC": branch_ifsc,
        }

        # Final Output
        output_data = {
            "supplier_details": supplier_details,
            "buyer_details": buyer_details,
            "invoice_details": invoice_details,
            "line_items": line_items,
            "tax_summary": tax_summary,
            "totals": totals,
            "amount_chargeable_in_words": amount_chargeable_words,
            "hsn_summary": hsn_summary,
            "bank_details": bank_details,
        }

        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)

        print(f"JSON saved to: {json_file_path}")

        # --- Validation step ---
        validate_json_vs_text(json_file_path, txt_file_path, validation_output_dir)
        print()

    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}\n")
