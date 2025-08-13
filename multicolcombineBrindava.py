import fitz  # PyMuPDF
import os
import re
import json

# Fallback in case multicolumn is missing
try:
    from multicolumn import column_boxes
except ImportError:

    def column_boxes(page, footer_margin=50, no_image_text=True):
        return [page.rect]


# Directories
input_dir = "E:\\Working_Docling_Project\\testingdocument\\allinvoices"
output_dir_txt = "Brindavantxtfile"
output_dir_json = "Brindavanjsonfile"
validation_output_dir = "Brindavanvalidatejsontext"

os.makedirs(output_dir_txt, exist_ok=True)
os.makedirs(output_dir_json, exist_ok=True)
os.makedirs(validation_output_dir, exist_ok=True)

# Get list of PDF files starting with "bri"
file_names = [
    os.path.join(input_dir, item)
    for item in os.listdir(input_dir)
    if os.path.isfile(os.path.join(input_dir, item))
    and item.lower().startswith("bri")
    and item.lower().endswith(".pdf")
]


# Helper extraction function with optional regex flags
def extract(pattern, source, default="", flags=re.MULTILINE):
    match = re.search(pattern, source, flags)
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
                    print(f"Error extracting text from page {page.number + 1}: {e}")

        with open(txt_file_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"Text saved to: {txt_file_path}")

        # Read text
        with open(txt_file_path, "r", encoding="utf-8") as file:
            text = file.read()
            lines = [line.strip() for line in text.splitlines() if line.strip()]

        # ---------------------
        # Supplier Details
        # ---------------------
        supplier_details = {
            "name": lines[0],
            "address": ", ".join(lines[1:5]),
            "gstin_uin": extract(r"GSTIN/UIN:\s*(\S+)", text),
            "state_name": extract(r"State Name\s*:\s*(.+?),", text),
            "state_code": extract(r"Code\s*:\s*(\d+)", text),
            "contact": extract(r"Contact\s*:\s*(.+)", text),
            "email": extract(r"E-Mail\s*:\s*(.+)", text),
        }

        # ---------------------
        # Buyer Details
        # ---------------------
        buyer_block = extract(
            r"Buyer\s*(.*?)GSTIN/UIN", text, default="", flags=re.DOTALL
        )
        buyer_lines = buyer_block.splitlines()

        buyer_details = {
            "name": buyer_lines[0].strip() if buyer_lines else "",
            "address": " ".join(line.strip() for line in buyer_lines if line.strip()),
            "gstin_uin": extract(r"GSTIN/UIN \s*:\s*(\S+)", text),
        }

        # ---------------------
        # Invoice Details
        # ---------------------
        invoice_labels = [
            "BRINDAVAN\\13102",
            "Delivery Note",
            "Supplier's Ref.",
            "Buyer's Order No.",
            "Despatch Document No.",
            "Despatched through",
            "Terms of Delivery",
            "Mode/Terms of Payment",
            "Other Reference(s)",
            "Dated",
            "Delivery Note Date",
            "Destination",
        ]

        clean_keys = [
            label.replace(":", "").replace("\\", "").strip() for label in invoice_labels
        ]
        invoice_details = {label: "" for label in clean_keys}

        excluded_values = [
            "",
            "Sl                Description of Goods            HSN/SAC   Part No.    Quantity     Rate     per     Amount",
        ]

        for i in range(len(lines) - 1):
            key = lines[i].strip().replace(":", "").replace("\\", "")
            val = lines[i + 1].strip()
            if key in invoice_details:
                if val not in clean_keys and val not in excluded_values:
                    invoice_details[key] = val
                else:
                    invoice_details[key] = ""

        # Rename key
        invoice_details["Invoice No"] = invoice_details.pop("BRINDAVAN13102", "")

        # ---------------------
        # Line Items
        # ---------------------
        line_items = []
        item_pattern = re.compile(
            r"^(.+?)\s{2,}(\d{6,8})\s+(\d+)\s+([A-Za-z]+)\s+([\d,]+\.\d{2})\s+([A-Za-z]+)\s+([\d,]+\.\d{2})$"
        )

        for line in lines:
            match = item_pattern.match(line)
            if match:
                description = match.group(1).strip()
                hsn = match.group(2)
                part_no = match.group(3)
                quantity = f"{match.group(3)} {match.group(4)}"
                rate = match.group(5)
                per = match.group(6)
                amount = match.group(7)

                line_items.append(
                    {
                        "Description of Goods": description,
                        "HSN/SAC": hsn,
                        "Part No": part_no,
                        "Quantity": quantity,
                        "Rate": rate,
                        "per": per,
                        "Amount": amount,
                    }
                )

        # ---------------------
        # Tax Summary
        # ---------------------
        tax_summary = {
            "CGST Rate (%)": extract(r"Output CGST @\s*(\d+)%", text),
            "CGST Amount": extract(r"Output CGST @\s*\d+%\s+\d+ %\s+([\d,.]+)", text),
            "SGST Rate (%)": extract(r"Output SGST @\s*(\d+)%", text),
            "SGST Amount": extract(r"Output SGST @\s*\d+%\s+\d+ %\s+([\d,.]+)", text),
        }

        # ---------------------
        # HSN Summary
        # ---------------------
        hsn_summary = []
        hsn_match = re.search(
            r"(\d{6,8})\s+([\d,.]+)\s+(\d+)%\s+([\d,.]+)\s+(\d+)%\s+([\d,.]+)\s+([\d,.]+)",
            text,
        )
        if hsn_match:
            hsn_summary.append(
                {
                    "HSN/SAC": hsn_match.group(1),
                    "Taxable Value": hsn_match.group(2),
                    "CGST Rate": hsn_match.group(3) + "%",
                    "CGST Amount": hsn_match.group(4),
                    "SGST Rate": hsn_match.group(5) + "%",
                    "SGST Amount": hsn_match.group(6),
                    "Total Tax Amount": hsn_match.group(7),
                }
            )

        # ---------------------
        # Bank Details
        # ---------------------
        bank_details = {
            "Bank Name": extract(r"Bank Name\s*:\s*(.+)", text),
            "Account Number": extract(r"A/c No\.\s*:\s*(\d+)", text),
            "Branch & IFS Code": extract(r"Branch\s*&\s*IFS\s*Code\s*:\s*(.+)", text),
        }

        # ---------------------
        # Final Output
        # ---------------------
        output = {
            "supplier_details": supplier_details,
            "buyer_details": buyer_details,
            "invoice_details": invoice_details,
            "line_items": line_items,
            "tax_summary": tax_summary,
            "hsn_summary": hsn_summary,
            "bank_details": bank_details,
        }

        with open(json_file_path, "w", encoding="utf-8") as json_file:
            json.dump(output, json_file, indent=4)

        print(f"JSON saved to: {json_file_path}\n")

        # --- Validation step ---
        validate_json_vs_text(json_file_path, txt_file_path, validation_output_dir)
        print()

    except Exception as e:
        print(f"Failed to process {pdf_path}: {e}\n")
