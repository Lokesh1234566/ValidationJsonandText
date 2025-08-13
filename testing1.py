import os


def get_pdf_files(input_dir, prefix, extension=".pdf"):

    return [
        os.path.join(input_dir, item)
        for item in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, item))
        and item.lower().startswith(prefix.lower())
        and item.lower().endswith(extension.lower())
    ]
