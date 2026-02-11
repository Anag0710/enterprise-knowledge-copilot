"""
Rich media extraction from documents (tables, images).
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class TableData:
    """Extracted table data."""
    page: int
    table_index: int
    headers: List[str]
    rows: List[List[str]]
    bbox: Optional[tuple] = None  # (x0, y0, x1, y1)
    
    def to_markdown(self) -> str:
        """Convert table to markdown format."""
        lines = []
        
        # Header
        lines.append("| " + " | ".join(self.headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(self.headers)) + " |")
        
        # Rows
        for row in self.rows:
            lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ImageData:
    """Extracted image data."""
    page: int
    image_index: int
    width: int
    height: int
    format: str  # PNG, JPEG, etc.
    bbox: Optional[tuple] = None
    file_path: Optional[str] = None  # Saved image path
    size_bytes: int = 0


class RichMediaExtractor:
    """
    Extract tables and images from PDF documents.
    
    Features:
    - Table extraction with pdfplumber
    - Image extraction with PyMuPDF
    - Metadata preservation
    - Export to JSON/Markdown
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize rich media extractor.
        
        Args:
            output_dir: Directory to save extracted images (default: data/media)
        """
        self.output_dir = output_dir or Path("data/media")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if not PDFPLUMBER_AVAILABLE:
            logger.warning(
                "pdfplumber not available for table extraction. "
                "Install with: pip install pdfplumber"
            )
        
        if not PYMUPDF_AVAILABLE:
            logger.warning(
                "PyMuPDF not available for image extraction. "
                "Install with: pip install PyMuPDF"
            )
    
    def extract_tables(self, pdf_path: Path) -> List[TableData]:
        """
        Extract all tables from PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of TableData objects
        """
        if not PDFPLUMBER_AVAILABLE:
            logger.error("pdfplumber required for table extraction")
            return []
        
        tables = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_tables = page.extract_tables()
                    
                    for table_idx, table in enumerate(page_tables):
                        if not table or len(table) < 2:
                            continue
                        
                        # First row as headers
                        headers = [str(cell) if cell else "" for cell in table[0]]
                        
                        # Remaining rows
                        rows = []
                        for row in table[1:]:
                            rows.append([str(cell) if cell else "" for cell in row])
                        
                        tables.append(TableData(
                            page=page_num,
                            table_index=table_idx,
                            headers=headers,
                            rows=rows
                        ))
            
            logger.info(f"Extracted {len(tables)} tables from {pdf_path.name}")
        except Exception as e:
            logger.error(f"Failed to extract tables from {pdf_path}: {e}")
        
        return tables
    
    def extract_images(self, pdf_path: Path, save_images: bool = True) -> List[ImageData]:
        """
        Extract all images from PDF.
        
        Args:
            pdf_path: Path to PDF file
            save_images: Save images to disk
            
        Returns:
            List of ImageData objects
        """
        if not PYMUPDF_AVAILABLE:
            logger.error("PyMuPDF required for image extraction")
            return []
        
        images = []
        doc_name = pdf_path.stem
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                for img_idx, img in enumerate(image_list):
                    xref = img[0]
                    
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # Save image if requested
                        image_path = None
                        if save_images:
                            image_filename = f"{doc_name}_p{page_num + 1}_img{img_idx}.{image_ext}"
                            image_path = self.output_dir / image_filename
                            
                            with open(image_path, "wb") as img_file:
                                img_file.write(image_bytes)
                        
                        images.append(ImageData(
                            page=page_num + 1,
                            image_index=img_idx,
                            width=base_image.get("width", 0),
                            height=base_image.get("height", 0),
                            format=image_ext.upper(),
                            file_path=str(image_path) if image_path else None,
                            size_bytes=len(image_bytes)
                        ))
                    
                    except Exception as e:
                        logger.warning(f"Failed to extract image {img_idx} from page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            logger.info(f"Extracted {len(images)} images from {pdf_path.name}")
        
        except Exception as e:
            logger.error(f"Failed to extract images from {pdf_path}: {e}")
        
        return images
    
    def extract_all(
        self,
        pdf_path: Path,
        save_images: bool = True
    ) -> Dict[str, Any]:
        """
        Extract both tables and images from PDF.
        
        Args:
            pdf_path: Path to PDF file
            save_images: Save images to disk
            
        Returns:
            Dictionary with tables and images
        """
        tables = self.extract_tables(pdf_path)
        images = self.extract_images(pdf_path, save_images)
        
        return {
            "document": str(pdf_path),
            "tables": [t.to_dict() for t in tables],
            "images": [asdict(img) for img in images],
            "summary": {
                "total_tables": len(tables),
                "total_images": len(images),
                "pages_with_tables": len(set(t.page for t in tables)),
                "pages_with_images": len(set(i.page for i in images))
            }
        }
    
    def save_tables_as_markdown(
        self,
        tables: List[TableData],
        output_path: Path
    ):
        """Save extracted tables as markdown file."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# Extracted Tables\n\n")
            
            for table in tables:
                f.write(f"## Table {table.table_index + 1} (Page {table.page})\n\n")
                f.write(table.to_markdown())
                f.write("\n\n")
    
    def save_media_manifest(
        self,
        media_data: Dict[str, Any],
        output_path: Path
    ):
        """Save media extraction manifest as JSON."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(media_data, f, indent=2)


# Global instance
_media_extractor: Optional[RichMediaExtractor] = None


def get_media_extractor(output_dir: Optional[Path] = None) -> RichMediaExtractor:
    """Get or create global media extractor instance."""
    global _media_extractor
    if _media_extractor is None:
        _media_extractor = RichMediaExtractor(output_dir)
    return _media_extractor


def is_media_extraction_available() -> bool:
    """Check if media extraction dependencies are available."""
    return PDFPLUMBER_AVAILABLE and PYMUPDF_AVAILABLE
