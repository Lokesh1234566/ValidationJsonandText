import fitz  # PyMuPDF
import os
import re
import json

# --- Dummy column_boxes fallback if missing ---
try:
    from multicolumn import column_boxes
except ImportError:

    def column_boxes(page, footer_margin=50, no_image_text=True):
        return [page.rect]  # Use full page if no multicolumn logic


# Directories
input_dir = "./allinvoices"
output_dir_txt = "Nutextfile"
output_dir_json = "Nujsonfile"
validation_output_dir = "Nuvalidatejsontext"

# Create output directories if they don't exist
os.makedirs(output_dir_txt, exist_ok=True)
os.makedirs(output_dir_json, exist_ok=True)
os.makedirs(validation_output_dir, exist_ok=True)

# Get list of PDF files starting with "nu"
file_names = [
    os.path.join(input_dir, item)
    for item in os.listdir(input_dir)
    if os.path.isfile(os.path.join(input_dir, item))
    and item.lower().startswith("nu")
    and item.lower().endswith(".pdf")
]


# Helper extraction function
def extract(pattern, source, default=""):
    match = re.search(pattern, source, re.IGNORECASE | re.MULTILINE)
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


# MAIN LOOP FOR ALL PDFs
for pdf_path in file_names:
    base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    txt_file_path = os.path.join(output_dir_txt, f"{base_filename}.txt")
    json_file_path = os.path.join(output_dir_json, f"{base_filename}.json")

    try:
        print(f"Processing: {pdf_path}")
        doc = fitz.open(pdf_path)
        full_text = ""

        for page in doc:
            bboxes = column_boxes(page, footer_margin=50, no_image_text=True)
            for rect in bboxes:
                try:
                    text = page.get_text(clip=rect, sort=True)
                    full_text += text + "\n\n"
                except Exception as e:
                    print(f"Text extraction error on page {page.number + 1}: {e}")

        with open(txt_file_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"Text saved to: {txt_file_path}")

        # Reload text
        with open(txt_file_path, "r", encoding="utf-8") as f:
            text = f.read()
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # -------------------------
        # Supplier Details
        # -------------------------
        supplier_details = {
            "name": extract(r"TAX INVOICE\s+(.+)", text),
            "address": extract(r"TAX INVOICE\s+.+\n(.+)", text),
            "pan": extract(r"PAN\s*:\s*(\S+)", text),
            "gstin": extract(r"GSTIN\s*(?:No)?\s*[:\-]?\s*(\S+)", text),
            "state": extract(r"STATE\s*-\s*(\w+)", text),
            "month": extract(r"MONTH\s*-\s*(\w+\s+\d{4})", text),
        }

        # -------------------------
        # Buyer Details
        # -------------------------
        buyer_details = {
            "name": extract(r"NAME\s*:\s*(.+)", text),
            "address": extract(r"NAME\s*:.+\n(.+)", text),
            "gstin": extract(r"GSTIN NO[:\-]*\s*(\S+)", text),
        }

        # -------------------------
        # Invoice Details
        # -------------------------
        invoice_details = {
            "invoice_number": extract(r"INVOICE NUMBER\s*[:\-]*\s*(\d+)", text),
            "date": extract(r"DATE\s*[:\-]*\s*(\d{2}/\d{2}/\d{4})", text),
            "period": extract(r"Period\s*[:\-]*\s*([^\n]+)", text),
        }

        # -------------------------
        # Line Items
        # -------------------------
        line_items = []
        item_pattern = re.compile(
            r"(\d{2}\.\d{2}\.\d{4})\s+(\d+)\s+([\w\s]+?)\s+(?:\S+)?\s+(\d+kg|\d+gms|\d+)\s+(\d+)\s+([\d,]+\.\d{2})"
        )

        for match in item_pattern.finditer(text):
            date, awb, dest, weight, quantity, amount = match.groups()
            line_items.append(
                {
                    "Date": date,
                    "AWB No": awb,
                    "Destination": dest.strip(),
                    "Weight": weight,
                    "Quantity": quantity,
                    "Amount": amount,
                }
            )

        # -------------------------
        # Tax Summary
        # -------------------------
        tax_summary = {
            "SAC Code": extract(r"SAC\s*CODE\s*[:\-]*\s*(\d+)", text),
            "Taxable Amount": extract(r"TAXABLE AMOUNT\s+([\d,]+\.\d{2})", text),
            "CGST %": extract(r"CGST AMOUNT\s*(\d+)%", text),
            "CGST Amount": extract(r"CGST AMOUNT\s*\d+%\s*([\d,]+\.\d{2})", text),
            "SGST %": extract(r"SGST AMOUNT\s*(\d+)%", text),
            "SGST Amount": extract(r"SGST AMOUNT\s*\d+%\s*([\d,]+\.\d{2})", text),
            "IGST %": extract(r"IGST AMOUNT\s*(\d+)%", text),
            "IGST Amount": extract(r"IGST AMOUNT\s*\d+%\s*([\d,]+\.\d{2})", text),
            "Fuel Charges": extract(r"FUEL CHARGERS\s*\d+%\s*([\d,]+\.\d{2})", text),
            "Round Off": extract(r"ROUND OFF\s*([\d,]+\.\d{2})", text),
        }

        # -------------------------
        # Totals
        # -------------------------
        totals = {
            "Total Amount": extract(r"TOTAL AMOUNT\s*([\d,]+\.\d{2})", text),
            "Invoice Amount": extract(r"INVOICE AMOUNT\s*\n([\d,]+\.\d{2})", text),
            "Total Consignment": extract(r"Total Consignment\s*[:\-]*\s*(\d+)", text),
        }

        # -------------------------
        # Amount in Words
        # -------------------------
        amount_in_words = extract(r"Amount In words\s*[:-]\s*(.+)", text)

        # -------------------------
        # Final Output
        # -------------------------
        output_data = {
            "supplier_details": supplier_details,
            "buyer_details": buyer_details,
            "invoice_details": invoice_details,
            "line_items": line_items,
            "tax_summary": tax_summary,
            "totals": totals,
            "amount_in_words": amount_in_words,
        }

        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)

        print(f"JSON saved to: {json_file_path}\n")

        # --- Validation step ---
        validate_json_vs_text(json_file_path, txt_file_path, validation_output_dir)
        print()

    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}\n")
