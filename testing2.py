from testing1 import get_pdf_files

input_dir = "./allinvoices"
file_prefix = "vee"

file_names = get_pdf_files(input_dir, file_prefix)

print(file_names)
