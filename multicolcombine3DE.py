import fitz  # PyMuPDF
import os
import re
import json
from multicolumn import column_boxes  # Ensure this exists and works
from utils import (
    get_pdf_files,
    extract_and_read_pdf_text,
    extract,
    validate_json_vs_text,
)

# Directories
input_dir = "./allinvoices"
output_dir_txt = "3detxtfile"
output_dir_json = "3dejsonfile"
validation_output_dir = "3devalidatejsontext"
file_prefix = "3de"
file_names = get_pdf_files(input_dir, file_prefix)


# Create output directories if they don't exist
os.makedirs(output_dir_txt, exist_ok=True)
os.makedirs(output_dir_json, exist_ok=True)
os.makedirs(validation_output_dir, exist_ok=True)

# Main processing loop
for pdf_path in file_names:
    base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    txt_file_path = os.path.join(output_dir_txt, f"{base_filename}.txt")
    json_file_path = os.path.join(output_dir_json, f"{base_filename}.json")

    try:
        text = extract_and_read_pdf_text(pdf_path, txt_file_path, column_boxes)

        with open(txt_file_path, "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file.readlines()]

        # Supplier Details
        supplier_details = {
            "name": lines[0].strip(),
            "address": ", ".join(lines[1:6]).strip(),
            "gstin_uin": extract(r"GSTIN/UIN:\s*(\S+)", text),
            "state_name": extract(r"State Name\s*:\s*(.+?),\s*Code\s*:\s*\d+", text),
            "state_code": extract(r"State Name\s*:\s*.+?,\s*Code\s*:\s*(\d+)", text),
            "email": extract(r"E-Mail\s*:\s*(.+)", text),
        }

        # Buyer Details
        buyer_details = {
            "name": extract(r"Buyer\s*\n([^\n]+)", text),
            "address": extract(r"Buyer\s*\n[^\n]+\n(.+\n.+\n.+)", text).replace(
                "\n", ", "
            ),
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
            if line.strip() in invoice_keys:
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                invoice_details[line.rstrip(".")] = (
                    next_line.strip() if next_line.strip() not in invoice_keys else ""
                )

        # Line Items
        line_items = []
        sl_counter = 1

        for i in range(len(lines)):
            if re.match(r"^\d+\s+Supply of Prototype Parts", lines[i]):
                header_line = lines[i]
                desc_line = lines[i + 1] if i + 1 < len(lines) else ""

                hsn = extract(r"(\d{8})", header_line)
                qty = extract(r"(\d+)\s+Nos", header_line)
                rate = extract(r"Nos\.\s+([\d,]+\.\d{2})", header_line)
                amount = extract(r"([\d,]+\.\d{2})$", header_line)
                gst_rate = extract(r"(\d{1,2})\s*%", header_line)

                full_desc = "Supply of Prototype Parts " + desc_line.strip()

                line_items.append(
                    {
                        "Sl No": str(sl_counter),
                        "Description of Goods": full_desc,
                        "HSN/SAC": hsn,
                        "Quantity": qty,
                        "Rate": rate,
                        "per": "Nos",
                        "Disc. %": "",
                        "Amount": amount,
                        "GST Rate": f"{gst_rate}%" if gst_rate else "",
                    }
                )

                sl_counter += 1

        # Totals and Tax
        totals = {
            "Total Quantity": extract(r"Total\s+(\d+)\s+Nos", text),
            "Total Amount": extract(
                r"Total\s+\d+\s+Nos\.\s+[^\d]*([\d,]+\.\d{2})", text
            ),
        }

        tax_summary = {
            "IGST Rate (%)": extract(r"(\d+)%\s+([\d,]+\.\d{2})", text),
            "IGST Amount": extract(r"\d+%\s+([\d,]+\.\d{2})", text),
        }

        # HSN Summary
        hsn_summary = []
        hsn_blocks = re.findall(
            r"(\d{6,8})\s+([\d,]+\.\d{2})\s+(\d+)%\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
            text,
        )
        for hsn, taxable_val, rate, amount, total in hsn_blocks:
            hsn_summary.append(
                {
                    "HSN/SAC": hsn,
                    "Taxable Value": taxable_val,
                    "Integrated Tax Rate": f"{rate}%",
                    "Integrated Tax Amount": amount,
                    "Total Tax Amount": total,
                }
            )

        # Amount in Words
        amount_chargeable_words = ""
        for i, line in enumerate(lines):
            if "Amount Chargeable (in words)" in line:
                amount_chargeable_words = (
                    lines[i + 1].strip() if i + 1 < len(lines) else ""
                )
                break

        # Bank Details
        bank_details = {
            "Bank Name": extract(r"Bank Name\s*:\s*(.+)", text),
            "Account Number": extract(r"A/c\s*No\.?\s*:\s*(\d+)", text),
            "Branch_IFSC": extract(r"Branch\s*&\s*IFS\s*Code\s*:\s*(.+)", text),
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

        with open(json_file_path, "w", encoding="utf-8") as json_file:
            json.dump(output_data, json_file, indent=4)

        print(f"JSON saved to: {json_file_path}\n")

        # --- Validation step ---
        validate_json_vs_text(json_file_path, txt_file_path, validation_output_dir)
        print("------------------------------------------")

    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}\n")
