import re
import os
import json
import fitz  # PyMuPDF


def read_line_and_next_if_found(filename, search_text):

    results = []
    with open(filename, "r") as file:
        lines = file.readlines()  # Read all lines into a list
        for i, line in enumerate(lines):
            if search_text in line:
                found_line = (
                    line.strip()
                )  # Remove leading/trailing whitespace and newline
                if i + 1 < len(lines):  # Check if a next line exists
                    next_line = lines[i + 1].strip()
                    results.append((found_line, next_line))
                else:
                    results.append((found_line, "No next line available"))
    return results


# Helper extraction function
def extract(pattern, source, default=""):
    match = re.search(pattern, source, re.MULTILINE)
    return match.group(1).strip() if match else default


# Input file path
def get_pdf_files(input_dir, prefix, extension=".pdf"):

    return [
        os.path.join(input_dir, item)
        for item in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, item))
        and item.lower().startswith(prefix.lower())
        and item.lower().endswith(extension.lower())
    ]


# pdf text extracted and save in file and also read text file to get json


def extract_and_read_pdf_text(
    pdf_path, txt_file_path, column_boxes_func, footer_margin=50, no_image_text=True
):

    print(f"Processing: {pdf_path}")
    doc = fitz.open(pdf_path)
    full_text = ""

    for page in doc:
        bboxes = column_boxes_func(
            page, footer_margin=footer_margin, no_image_text=no_image_text
        )
        for rect in bboxes:
            try:
                text = page.get_text(clip=rect, sort=True)
                full_text += text + "\n\n"
            except Exception as e:
                print(f"Text extraction error on page {page.number + 1}: {e}")

    # Write to file
    with open(txt_file_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"Text saved to: {txt_file_path}")

    # Read back from file
    with open(txt_file_path, "r", encoding="utf-8") as f:
        text = f.read()

    return text


# validation
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
