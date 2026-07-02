import os
from pypdf import PdfWriter

async def capture_high_fidelity_pdf(page, output_path, title):
    """
    Standard high-fidelity PDF capture with headers, footers and backgrounds.
    """
    print(f"Capturing High-Fidelity PDF: {title}...")
    await page.pdf(
        path=output_path,
        format="A4",
        display_header_footer=True,
        print_background=True,
        margin={"top": "2cm", "right": "1cm", "bottom": "2cm", "left": "1cm"},
        header_template=f"""
            <div style="font-size:8px; width:100%; margin: 0 0.5cm; display: flex; justify-content: space-between; font-family: sans-serif; color: #333;">
                <span class="date"></span>
                <span>{title}</span>
            </div>
        """,
        footer_template="""
            <div style="font-size:8px; width:100%; margin: 0 0.5cm; display: flex; justify-content: space-between; font-family: sans-serif; color: #333;">
                <span class="url"></span>
                <span style="white-space: nowrap;">Page <span class="pageNumber"></span> / <span class="totalPages"></span></span>
            </div>
        """
    )

def merge_pdfs(pdf_list, output_path):
    """
    Merges a list of PDF files into one.
    """
    if not pdf_list:
        return False
    
    print(f"Merging {len(pdf_list)} PDF components into {output_path}...")
    merger = PdfWriter()
    for pdf in pdf_list:
        if os.path.exists(pdf):
            merger.append(pdf)
    
    with open(output_path, "wb") as f:
        merger.write(f)
    return True
