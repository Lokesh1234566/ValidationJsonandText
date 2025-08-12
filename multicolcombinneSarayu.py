import fitz  # PyMuPDF
import os
import re
import json

# --- Dummy column_boxes fallback if missing ---
try:
    from multicolumn import column_boxes
except ImportError:

    def column_boxes(page, footer_margin=50, no_image_text=True):
        return [page.rect]  # Use full page as fallback


# Directories
input_dir = "./allinvoices"
output_dir_txt = "Sarayutextfile"
output_dir_json = "Sarayujsonfile"
validation_output_dir = "Sarayuvalidatejsontext"

# Create output directories if they don't exist
os.makedirs(output_dir_txt, exist_ok=True)
os.makedirs(output_dir_json, exist_ok=True)
os.makedirs(validation_output_dir, exist_ok=True)

# Get list of PDF files starting with "sar"
file_names = [
    os.path.join(input_dir, item)
    for item in os.listdir(input_dir)
    if os.path.isfile(os.path.join(input_dir, item))
    and item.lower().startswith("sar")
    and item.lower().endswith(".pdf")
]


# Helper extraction function
def extract(pattern, source, default="", group=1):
    match = re.search(pattern, source, re.IGNORECASE | re.MULTILINE)
    return match.group(group).strip() if match else default


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

        with open(txt_file_path, "r", encoding="utf-8") as f:
            text = f.read()

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # -------------------------
        # Supplier Details
        # -------------------------
        supplier_details = {
            "name": lines[0] if lines else "",
            "address": ", ".join(lines[1:4]) if len(lines) > 3 else "",
            "gstin_uin": extract(r"GSTIN/UIN:\s*(\S+)", text),
            "state_name": extract(r"State Name\s*:\s*(.+?),\s*Code", text),
            "state_code": extract(r"State Name\s*:\s*.+?,\s*Code\s*:\s*(\d+)", text),
            "email": extract(r"E[-\s]?Mail\s*:\s*(\S+)", text),
        }

        # -------------------------
        # Buyer Details
        # -------------------------
        buyer_details = {
            "name": "Irillic Pvt. Ltd.",
            "address": ", ".join(
                [
                    lines[lines.index("Buyer") + 1] if "Buyer" in lines else "",
                    lines[lines.index("Buyer") + 2] if "Buyer" in lines else "",
                ]
            ),
            "gstin_uin": extract(r"GSTIN/UIN\s*:\s*(\S+)", text),
            "state_name": extract(r"State Name\s*:\s*(.+?),\s*Code", text),
            "state_code": extract(r"State Name\s*:\s*.+?,\s*Code\s*:\s*(\d+)", text),
            "place_of_supply": extract(r"Place of Supply\s*:\s*(.+)", text),
            "contact_person": extract(r"Contact person\s*:\s*(.+)", text),
            "contact": extract(r"Contact\s*:\s*(\S+)", text),
        }

        # -------------------------
        # Invoice Details
        # -------------------------
        invoice_labels = [
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

        invoice_details = {
            label.replace(":", "").replace("’", "'").strip(): ""
            for label in invoice_labels
        }

        for i in range(len(lines) - 1):
            key = lines[i].strip().replace(":", "").replace("’", "'")
            val = lines[i + 1].strip()
            if (
                key in invoice_details
                and val not in invoice_labels
                and not val.startswith("Sl ")
            ):
                invoice_details[key] = val

        # -------------------------
        # Line Items
        # -------------------------
        line_items = []
        i = 0
        while i < len(lines):
            match = re.match(
                r"^(\d+)\s+([A-Za-z\s&()\-]+)\s+(\d{6,8})\s+(\d+)\s*%\s+(\d+)\s+([A-Za-z]+)\s+(\d+)\s+([A-Za-z]+)\s+([\d,]+\.\d{2})",
                lines[i],
            )
            if match:
                sl_no = match.group(1)
                desc = match.group(2).strip()
                hsn = match.group(3)
                gst_rate = match.group(4)
                qty = f"{match.group(5)} {match.group(6)}"
                rate = match.group(7)
                per = match.group(8)
                amount = match.group(9)

                if i + 1 < len(lines) and not lines[i + 1].startswith(
                    tuple("1234567890")
                ):
                    desc += " " + lines[i + 1].strip()
                    i += 1

                line_items.append(
                    {
                        "Sl No": sl_no,
                        "Description of Goods": desc,
                        "HSN/SAC": hsn,
                        "GST Rate": gst_rate,
                        "Quantity": qty,
                        "Rate": rate,
                        "per": per,
                        "Amount": amount,
                    }
                )
            i += 1

        # -------------------------
        # Tax Summary
        # -------------------------
        tax_summary = {
            "CGST Amount": extract(r"CGST\s+([\d,.]+)", text),
            "SGST Amount": extract(r"SGST\s+([\d,.]+)", text),
        }

        # -------------------------
        # HSN Summary
        # -------------------------
        hsn_summary = []
        hsn_pattern = re.compile(
            r"(\d{6,8})\s+([\d,.]+)\s+(\d+)%\s+([\d,.]+)\s+(\d+)%\s+([\d,.]+)\s+([\d,.]+)"
        )
        matches = hsn_pattern.findall(text)
        for match in matches:
            hsn_summary.append(
                {
                    "HSN/SAC": match[0],
                    "Taxable Value": match[1],
                    "Central Tax Rate": match[2] + "%",
                    "Central Tax Amount": match[3],
                    "State Tax Rate": match[4] + "%",
                    "State Tax Amount": match[5],
                    "Total Tax Amount": match[6],
                }
            )

        # -------------------------
        # Bank Details
        # -------------------------
        bank_details = {
            "Bank Name": extract(r"Bank Name\s*:\s*(.+)", text),
            "Account Number": extract(r"A/c No\.?\s*:\s*(\d+)", text),
            "Branch & IFSC": extract(r"Branch & IFS Code\s*:\s*(.+)", text),
        }

        # -------------------------
        # Final Output
        # -------------------------
        output_data = {
            "supplier_details": supplier_details,
            "buyer_details": buyer_details,
            "invoice_details": invoice_details,
            "line_items": line_items,
            "tax_summary": tax_summary,
            "hsn_summary": hsn_summary,
            "bank_details": bank_details,
        }

        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)

        print(f"JSON saved to: {json_file_path}\n")

        # --- Validation step ---
        validate_json_vs_text(json_file_path, txt_file_path, validation_output_dir)
        print()

    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}\n")
