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


# ------------------------------------------------

# Directories
input_dir = "E:\\Working_Docling_Project\\testingdocument\\allinvoices"
output_dir_txt = "Vimatextfile"
output_dir_json = "Vimajsonfile"
validation_output_dir = "Vimavalidatejsontext"

# Create output directories if they don't exist
os.makedirs(output_dir_txt, exist_ok=True)
os.makedirs(output_dir_json, exist_ok=True)
os.makedirs(validation_output_dir, exist_ok=True)

# Get list of PDF files starting with "Inf" or "inf"
file_names = [
    os.path.join(input_dir, item)
    for item in os.listdir(input_dir)
    if os.path.isfile(os.path.join(input_dir, item))
    and item.lower().startswith("vima")  # lowercase check
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


# -----------------------------
# MAIN LOOP FOR ALL PDFs
# -----------------------------
for pdf_path in file_names:
    base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    txt_file_path = os.path.join(output_dir_txt, f"{base_filename}.txt")
    json_file_path = os.path.join(output_dir_json, f"{base_filename}.json")

    try:
        print(f"Processing: {pdf_path}")
        doc = fitz.open(pdf_path)
        full_text = ""

        # Extracting text using column_boxes (or full page fallback)
        for page in doc:
            bboxes = column_boxes(page, footer_margin=50, no_image_text=True)
            for rect in bboxes:
                try:
                    text = page.get_text(clip=rect, sort=True)
                    print("*************************************8")
                    print(text)
                    print("********************************")
                    full_text += text + "\n\n"
                except Exception as e:
                    print(f"Text extraction error on page {page.number + 1}: {e}")

        # Save .txt file
        with open(txt_file_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"Text saved to: {txt_file_path}")

        # --- Begin Data Parsing ---
        with open(txt_file_path, "r", encoding="utf-8") as f:
            text = f.read()

        lines = [line.strip() for line in text.splitlines()]

        # -------------------------
        # Supplier Details
        # -------------------------
        supplier_details = {
            "name": lines[0].strip(),
            "address": ", ".join(lines[1:3]).strip(),
            "msme_reg_no": extract(r"MSME REG\.NO\.([A-Z0-9]+)", text),
            "gstin_uin": extract(r"GSTIN/UIN:\s*(\S+)", text),
            "state_name": extract(r"State Name\s*:\s*(.+?),", text),
            "state_code": extract(r"Code\s*:\s*(\d+)", text),
            "email": extract(r"E-Mail\s*:\s*(.+)", text),
            "contact": extract(r"Contact\s*:\s*(\S+)", text),
        }

        # -------------------------
        # Buyer & Consignee Details
        # -------------------------
        def extract_block(start_keyword):
            start = None
            for i, line in enumerate(lines):
                if start_keyword.lower() in line.lower():
                    start = i
                    break
            if start is not None:
                block = lines[start + 1 : start + 6]
                return block
            return []

        buyer_block = extract_block("Buyer (if other than consignee)")
        buyer_details = {
            "name": buyer_block[0] if len(buyer_block) > 0 else "",
            "address": ", ".join(buyer_block[1:3]) if len(buyer_block) > 2 else "",
            "gstin_uin": extract(r"GSTIN/UIN \s*:\s*([A-Z0-9]+)", text),
            "pan": extract(r"PAN/IT\s*No\s*:\s*([A-Z0-9]+)", text),
            "state_name": extract(r"State Name\s*:\s*(.*?),", text),
            "state_code": extract(r"Code\s*:\s*(\d+)", text),
            "place_of_supply": extract(r"Place of Supply\s*:\s*(.*)", text),
        }

        # -------------------------
        # Invoice Details
        # Define the expected invoice fields in order
        invoice_labels = [
            "Invoice No",
            "Delivery Note",
            "Supplier’s Ref",
            "Buyer's Order No",
            "Despatch Document No",
            "Despatched through",
            "Bill of Lading/LR-RR No",
            "Terms of Delivery",
            "Mode/Terms of Payment",
            "Other Reference(s)",
            "Dated",
            "Delivery Note Date",
            "Destination",
            "Motor Vehicle No",
        ]

        invoice_details = {
            label: "" for label in invoice_labels
        }  # initialize with blanks

        # Iterate through lines and fill values
        for i in range(len(lines) - 1):
            current_line = lines[i].strip().replace(":", "")
            next_line = lines[i + 1].strip()

            # If current line is a known label, take next line as value (unless it's also a label)
            if current_line in invoice_details:
                if next_line not in invoice_labels and next_line != "":
                    invoice_details[current_line] = next_line
                else:
                    invoice_details[current_line] = ""

        # -------------------------
        # Line Items (Updated)
        # -------------------------

        line_items = []
        item_pattern = re.compile(
            r"^(\d+)\s+(.*?)\s+(\d{6,8})\s+([\d,.]+)\s+([A-Za-z]+)\s+([\d,.]+)\s+([A-Za-z]+)\s+([\d,.]+)$"
        )

        for line in lines:
            match = item_pattern.match(line)
            if match:
                line_items.append(
                    {
                        "Sl No": match.group(1),
                        "Description of Goods": match.group(2).strip(),
                        "HSN/SAC": match.group(3),
                        "Quantity": match.group(4),
                        "Qty Unit": match.group(5),
                        "Rate": match.group(6),
                        "Rate Unit": match.group(7),
                        "Amount": match.group(8),
                    }
                )

        # -------------------------
        # Tax Summary
        # -------------------------
        tax_summary = {
            "CGST Rate (%)": "",
            "CGST Amount": "",
            "SGST Rate (%)": "",
            "SGST Amount": "",
        }
        for line in lines:
            if "Output CGST" in line:
                tax_summary["CGST Rate (%)"] = extract(r"CGST\s*@\s*(\d+)%", line)
                tax_summary["CGST Amount"] = extract(
                    r"(\d{1,3}(?:,\d{3})*\.\d{2})$", line
                )
            elif "Output SGST" in line:
                tax_summary["SGST Rate (%)"] = extract(r"SGST\s*@\s*(\d+)%", line)
                tax_summary["SGST Amount"] = extract(
                    r"(\d{1,3}(?:,\d{3})*\.\d{2})$", line
                )

        # -------------------------
        # HSN Summary
        # -------------------------
        hsn_summary = []
        for line in lines:
            match = re.search(
                r"(\d{6,8})\s+([\d,.]+)\s+(\d+%)\s+([\d,.]+)\s+(\d+%)\s+([\d,.]+)\s+([\d,.]+)",
                line,
            )
            if match:
                hsn_summary.append(
                    {
                        "HSN/SAC": match.group(1),
                        "Taxable Value": match.group(2),
                        "CGST Rate": match.group(3),
                        "CGST Amount": match.group(4),
                        "SGST Rate": match.group(5),
                        "SGST Amount": match.group(6),
                        "Total Tax Amount": match.group(7),
                    }
                )

        # -------------------------
        # Bank Details
        # -------------------------
        bank_details = {
            "Bank Name": extract(r"Bank Name\s*:\s*(.+?)(?=\s*A/c No)", text),
            "Account Number": extract(r"A/c No\.?\s*[:\-]?\s*(\d+)", text),
            "Branch": extract(r"Branch\s*&\s*IFS\s*Code\s*:\s*(.*)\s+&", text),
            "IFSC Code": extract(r"&\s*(VIJB\d+)", text),
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

        # -------------------------
        # Save Output
        # -------------------------
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4)
        print(f"JSON saved to: {json_file_path}\n")

        # --- Validation step ---
        validate_json_vs_text(json_file_path, txt_file_path, validation_output_dir)
        print()

    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}\n")
