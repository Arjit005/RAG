import sys
import uuid
# Mock uuid_utils to bypass Windows AppLocker/WDAC DLL block
class CompatMock:
    @staticmethod
    def uuid7():
        return uuid.uuid4()
class UUIDUtilsMock:
    compat = CompatMock()
sys.modules['uuid_utils'] = UUIDUtilsMock()
sys.modules['uuid_utils.compat'] = CompatMock()

import os
import base64
import uuid
from pathlib import Path
from typing import List, Any
import pymupdf  # PyMuPDF
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.document_loaders import TextLoader, CSVLoader, Docx2txtLoader, JSONLoader
from langchain_community.document_loaders.excel import UnstructuredExcelLoader

def list_to_markdown_table(rows: list) -> str:
    if not rows:
        return ""
    rows = [r for r in rows if any(val is not None and str(val).strip() != "" for val in r)]
    if not rows:
        return ""
    headers = [str(h or "").strip() for h in rows[0]]
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in rows[1:]:
        row_cells = [str(row[i] or "").strip() if i < len(row) else "" for i in range(len(headers))]
        md += "| " + " | ".join(row_cells) + " |\n"
    return md

def generate_image_summary(image_path: str, api_key: str) -> str:
    if not api_key:
        return "Image extracted from document. (Summarization skipped: GEMINI_API_KEY not configured)"
    try:
        with open(image_path, "rb") as image_file:
            img_b64 = base64.b64encode(image_file.read()).decode("utf-8")
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=api_key,
            temperature=0.0
        )
        
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": "Describe this image in detail. Focus on any charts, graphs, tables, data points, or text content present in the image. The description should be comprehensive enough to be used for search retrieval in a RAG system."
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                }
            ]
        )
        response = llm.invoke([message])
        return response.content
    except Exception as e:
        print(f"[ERROR] Failed to generate image summary: {e}")
        return "Image extracted from document. (Error generating summary)"

def generate_table_summary(table_markdown: str, api_key: str) -> str:
    if not api_key:
        return "Table extracted from document. (Summarization skipped: GEMINI_API_KEY not configured)"
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=api_key,
            temperature=0.0
        )
        prompt = f"Analyze this table data and provide a concise summary of what it shows, including key trends, data points, or structures:\n\n{table_markdown}"
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        print(f"[ERROR] Failed to generate table summary: {e}")
        return "Table extracted from document. (Error generating summary)"

def parse_pdf_multimodal(pdf_path: Path, extract_images_dir: Path, api_key: str = None) -> List[Document]:
    documents = []
    print(f"[DEBUG] Multimodal parsing for PDF: {pdf_path}")
    
    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        print(f"[ERROR] Failed to open PDF {pdf_path}: {e}")
        return documents

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_index = page_num + 1
        
        # 1. Extract Text Chunks
        text = page.get_text()
        if text.strip():
            # Add standard text doc
            documents.append(Document(
                page_content=text,
                metadata={
                    "type": "text",
                    "filename": pdf_path.name,
                    "source": pdf_path.name,
                    "page": page_index
                }
            ))
            
        # 2. Extract Tables
        try:
            tables = page.find_tables()
            for tab_idx, table in enumerate(tables):
                table_data = table.extract()
                table_md = list_to_markdown_table(table_data)
                if table_md.strip():
                    print(f"[DEBUG] Found table on page {page_index}")
                    summary = generate_table_summary(table_md, api_key)
                    documents.append(Document(
                        page_content=table_md,
                        metadata={
                            "type": "table",
                            "summary": summary,
                            "filename": pdf_path.name,
                            "source": pdf_path.name,
                            "page": page_index
                        }
                    ))
        except Exception as e:
            print(f"[WARNING] Failed to extract tables on page {page_index}: {e}")

        # 3. Extract Images
        try:
            image_list = page.get_images(full=True)
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Save to disk
                img_name = f"{pdf_path.stem}_p{page_index}_img{img_idx}_{uuid.uuid4().hex[:6]}.{image_ext}"
                img_path = extract_images_dir / img_name
                
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                
                print(f"[DEBUG] Saved image {img_name} from page {page_index}")
                
                # Generate summary and add to documents
                summary = generate_image_summary(str(img_path), api_key)
                documents.append(Document(
                    page_content=summary,
                    metadata={
                        "type": "image",
                        "image_path": str(img_path),
                        "filename": pdf_path.name,
                        "source": pdf_path.name,
                        "page": page_index
                    }
                ))
        except Exception as e:
            print(f"[WARNING] Failed to extract images on page {page_index}: {e}")
            
    doc.close()
    return documents

def load_all_documents(data_dir: str, gemini_api_key: str = None) -> List[Document]:
    data_path = Path(data_dir).resolve()
    print(f"[DEBUG] Loading documents from: {data_path}")
    
    # Directory to extract images to
    extract_images_dir = data_path / "extracted_images"
    extract_images_dir.mkdir(parents=True, exist_ok=True)
    
    documents = []
    
    # Fallback to env if API key not supplied
    api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")

    # PDF files (Advanced Multimodal parsing)
    pdf_files = list(data_path.glob('**/*.pdf'))
    print(f"[DEBUG] Found {len(pdf_files)} PDF files")
    for pdf_file in pdf_files:
        if "extracted_images" in pdf_file.parts:
            continue
        try:
            pdf_docs = parse_pdf_multimodal(pdf_file, extract_images_dir, api_key)
            documents.extend(pdf_docs)
            print(f"[DEBUG] Loaded {len(pdf_docs)} elements from {pdf_file}")
        except Exception as e:
            print(f"[ERROR] Failed to parse multimodal PDF {pdf_file}: {e}")

    # Helper function for text/files (adding standard type="text" metadata)
    def add_standard_docs(loaded_docs, source_file, file_type):
        for doc in loaded_docs:
            doc.metadata["type"] = "text"
            doc.metadata["filename"] = source_file.name
            doc.metadata["source"] = source_file.name
            doc.metadata["page"] = doc.metadata.get("page", 1)
        documents.extend(loaded_docs)

    # TXT files
    txt_files = list(data_path.glob('**/*.txt'))
    for txt_file in txt_files:
        try:
            loader = TextLoader(str(txt_file), encoding="utf-8")
            add_standard_docs(loader.load(), txt_file, "TXT")
        except Exception as e:
            print(f"[ERROR] Failed to load TXT {txt_file}: {e}")

    # CSV files
    csv_files = list(data_path.glob('**/*.csv'))
    for csv_file in csv_files:
        try:
            loader = CSVLoader(str(csv_file))
            add_standard_docs(loader.load(), csv_file, "CSV")
        except Exception as e:
            print(f"[ERROR] Failed to load CSV {csv_file}: {e}")

    # Excel files
    xlsx_files = list(data_path.glob('**/*.xlsx'))
    for xlsx_file in xlsx_files:
        try:
            loader = UnstructuredExcelLoader(str(xlsx_file))
            add_standard_docs(loader.load(), xlsx_file, "Excel")
        except Exception as e:
            print(f"[ERROR] Failed to load Excel {xlsx_file}: {e}")

    # Word files
    docx_files = list(data_path.glob('**/*.docx'))
    for docx_file in docx_files:
        try:
            loader = Docx2txtLoader(str(docx_file))
            add_standard_docs(loader.load(), docx_file, "Word")
        except Exception as e:
            print(f"[ERROR] Failed to load Word {docx_file}: {e}")

    # JSON files
    json_files = list(data_path.glob('**/*.json'))
    for json_file in json_files:
        try:
            loader = JSONLoader(str(json_file))
            add_standard_docs(loader.load(), json_file, "JSON")
        except Exception as e:
            print(f"[ERROR] Failed to load JSON {json_file}: {e}")

    print(f"[DEBUG] Total loaded documents: {len(documents)}")
    return documents

if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()
    docs = load_all_documents("data")
    print(f"Loaded {len(docs)} documents.")
    if docs:
        print("Example document:", docs[0])