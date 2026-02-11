"""
Export conversation history to various formats.
"""
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import json

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class ConversationExporter:
    """
    Export conversation history to different formats:
    - JSON (structured data)
    - PDF (formatted report)
    - Text (plain text transcript)
    """
    
    def __init__(self):
        self.pdf_available = PDF_AVAILABLE
        if not PDF_AVAILABLE:
            print("Warning: reportlab not available. PDF export disabled.")
    
    def export_to_json(
        self,
        conversation: List[Dict],
        output_path: Path,
        metadata: Dict | None = None
    ):
        """
        Export conversation to JSON file.
        
        Args:
            conversation: List of Q&A dicts with 'question', 'answer', 'sources', etc.
            output_path: Where to save the JSON file
            metadata: Optional metadata (user, session_id, etc.)
        """
        export_data = {
            "metadata": metadata or {
                "exported_at": datetime.now().isoformat(),
                "format": "json",
                "version": "1.0"
            },
            "conversation": conversation
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    def export_to_text(
        self,
        conversation: List[Dict],
        output_path: Path,
        include_sources: bool = True,
        include_confidence: bool = True
    ):
        """
        Export conversation to plain text file.
        
        Args:
            conversation: List of Q&A dicts
            output_path: Where to save the text file
            include_sources: Whether to include source citations
            include_confidence: Whether to include confidence scores
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("CONVERSATION TRANSCRIPT\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            for i, turn in enumerate(conversation, 1):
                f.write(f"Question #{i}:\n")
                f.write(f"{turn.get('question', 'N/A')}\n\n")
                
                f.write(f"Answer:\n")
                f.write(f"{turn.get('answer', 'N/A')}\n\n")
                
                if include_confidence and 'confidence' in turn:
                    confidence_pct = turn['confidence'] * 100
                    f.write(f"Confidence: {confidence_pct:.1f}%\n\n")
                
                if include_sources and 'sources' in turn and turn['sources']:
                    f.write("Sources:\n")
                    for source in turn['sources']:
                        if isinstance(source, dict):
                            src_name = source.get('source', 'Unknown')
                            src_page = source.get('page', '?')
                            f.write(f"  - {src_name} (page {src_page})\n")
                        else:
                            f.write(f"  - {source}\n")
                    f.write("\n")
                
                f.write("-" * 60 + "\n\n")
    
    def export_to_pdf(
        self,
        conversation: List[Dict],
        output_path: Path,
        title: str = "Conversation Report",
        include_sources: bool = True,
        include_confidence: bool = True
    ):
        """
        Export conversation to formatted PDF report.
        
        Args:
            conversation: List of Q&A dicts
            output_path: Where to save the PDF file
            title: Report title
            include_sources: Whether to include source citations
            include_confidence: Whether to include confidence scores
        """
        if not self.pdf_available:
            raise ImportError("reportlab not available. Run: pip install reportlab")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create PDF document
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=inch,
            bottomMargin=inch
        )
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='darkblue',
            spaceAfter=30,
            alignment=TA_CENTER
        )
        question_style = ParagraphStyle(
            'Question',
            parent=styles['Heading2'],
            fontSize=12,
            textColor='darkgreen',
            spaceAfter=10
        )
        answer_style = styles['BodyText']
        meta_style = ParagraphStyle(
            'Meta',
            parent=styles['Italic'],
            fontSize=9,
            textColor='gray'
        )
        
        # Build content
        story = []
        
        # Title
        story.append(Paragraph(title, title_style))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            meta_style
        ))
        story.append(Spacer(1, 0.3 * inch))
        
        # Conversation turns
        for i, turn in enumerate(conversation, 1):
            # Question
            question_text = turn.get('question', 'N/A')
            story.append(Paragraph(f"<b>Question {i}:</b>", question_style))
            story.append(Paragraph(question_text, answer_style))
            story.append(Spacer(1, 0.1 * inch))
            
            # Answer
            answer_text = turn.get('answer', 'N/A')
            story.append(Paragraph("<b>Answer:</b>", styles['Heading3']))
            story.append(Paragraph(answer_text, answer_style))
            story.append(Spacer(1, 0.1 * inch))
            
            # Confidence
            if include_confidence and 'confidence' in turn:
                confidence_pct = turn['confidence'] * 100
                story.append(Paragraph(
                    f"<i>Confidence: {confidence_pct:.1f}%</i>",
                    meta_style
                ))
                story.append(Spacer(1, 0.05 * inch))
            
            # Sources
            if include_sources and 'sources' in turn and turn['sources']:
                story.append(Paragraph("<b>Sources:</b>", styles['Heading4']))
                for source in turn['sources']:
                    if isinstance(source, dict):
                        src_name = source.get('source', 'Unknown')
                        src_page = source.get('page', '?')
                        story.append(Paragraph(
                            f"• {src_name} (page {src_page})",
                            meta_style
                        ))
                    else:
                        story.append(Paragraph(f"• {source}", meta_style))
                story.append(Spacer(1, 0.1 * inch))
            
            story.append(Spacer(1, 0.2 * inch))
        
        # Build PDF
        doc.build(story)
