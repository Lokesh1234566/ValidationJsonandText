import fitz  # PyMuPDF
import os
import re
import json
from multicolumn import column_boxes  # Ensure this exists and works

# Directories
input_dir = "./allinvoices"
output_dir_txt = "3detxtfile"
output_dir_json = "3dejsonfile"
validation_output_dir = "3devalidatejsontext"

# Create output directories if they don't exist
os.makedirs(output_dir_txt, exist_ok=True)
os.makedirs(output_dir_json, exist_ok=True)
os.makedirs(validation_output_dir, exist_ok=True)

# Get list of PDF files starting with "3de"
file_names = [
    os.path.join(input_dir, item)
    for item in os.listdir(input_dir)
    if os.path.isfile(os.path.join(input_dir, item))
    and item.lower().startswith("3de")
    and item.lower().endswith(".pdf")
]


# Helper extraction function
def extract(pattern, source, default=""):
    match = re.search(pattern, source, re.MULTILINE)
    return match.group(1).strip() if match else default


def validate_json_vs_text(json_path, txt_path, output_dir):
    with open(json_path, "r", encoding="utf-8") as jf:
        data = json.load(jf)

    with open(txt_path, "r", encoding="utf-8") as tf:
        text = tf.read()

    validation_results = []

    def check_value_in_text(key, value, parent_key=""):
        if isinstance(value, dict):
            for k, v in value.items():
                check_value_in_text(
                    k, v, parent_key=f"{parent_key}.{key}" if parent_key else key
                )
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    for k, v in item.items():
                        check_value_in_text(
                            k,
                            v,
                            parent_key=(
                                f"{parent_key}.{key}[{i}]"
                                if parent_key
                                else f"{key}[{i}]"
                            ),
                        )
                else:
                    val = str(item)
                    idx = text.find(val)
                    full_key = (
                        f"{parent_key}.{key}[{i}]" if parent_key else f"{key}[{i}]"
                    )
                    validation_results.append(
                        f"{full_key} : '{val}' found at index {idx}"
                    )
        else:
            val = str(value).strip()
            if val:
                idx = text.find(val)
                full_key = f"{parent_key}.{key}" if parent_key else key
                validation_results.append(f"{full_key} : '{val}' found at index {idx}")

    check_value_in_text("", data)

    # Separate found and not found entries
    found_entries = [
        line for line in validation_results if not line.endswith("index -1")
    ]
    not_found_entries = [
        line for line in validation_results if line.endswith("index -1")
    ]

    base_name = os.path.splitext(os.path.basename(json_path))[0]
    validation_txt_path = os.path.join(output_dir, f"{base_name}.txt")

    with open(validation_txt_path, "w", encoding="utf-8") as vf:
        vf.write("\n".join(validation_results))
        if not_found_entries:
            vf.write("\n\n--- NOT FOUND VALUES ---\n")
            vf.write("\n".join(not_found_entries))

    print(f"Validation file saved: {validation_txt_path}")


# Main processing loop
for pdf_path in file_names:
    base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    txt_file_path = os.path.join(output_dir_txt, f"{base_filename}.txt")
    json_file_path = os.path.join(output_dir_json, f"{base_filename}.json")

    try:
        print(f"Processing PDF: {pdf_path}")
        doc = fitz.open(pdf_path)
        full_text = ""

        for page in doc:
            bboxes = column_boxes(page, footer_margin=50, no_image_text=True)
            for rect in bboxes:
                try:
                    text = page.get_text(clip=rect, sort=True)
                    full_text += text + "\n\n"
                except Exception as e:
                    print(
                        f"Error extracting text from rectangle on page {page.number + 1}: {e}"
                    )

        with open(txt_file_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"Text saved to: {txt_file_path}")

        # --- Begin JSON Extraction ---
        with open(txt_file_path, "r", encoding="utf-8") as file:
            text = file.read()

        with open(txt_file_path, "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file.readlines()]

        # def extract(pattern, source, default=''):
        #     match = re.search(pattern, source, re.MULTILINE)
        #     return match.group(1).strip() if match else default

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
        print()

    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}\n")
