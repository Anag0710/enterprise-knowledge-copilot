"""
Document versioning system to track changes in knowledge base.
"""
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import json
import hashlib


@dataclass
class DocumentVersion:
    """Single version of a document."""
    document_name: str
    version: int
    fingerprint: str  # SHA256 hash
    timestamp: str
    size_bytes: int
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None


@dataclass
class VersionHistory:
    """Complete version history for a document."""
    document_name: str
    versions: List[DocumentVersion]
    current_version: int
    
    def get_version(self, version: int) -> Optional[DocumentVersion]:
        """Get specific version."""
        for v in self.versions:
            if v.version == version:
                return v
        return None
    
    def get_latest(self) -> Optional[DocumentVersion]:
        """Get latest version."""
        return self.get_version(self.current_version)
    
    def get_changes(self) -> List[Dict]:
        """Get list of changes between versions."""
        changes = []
        for i in range(1, len(self.versions)):
            prev = self.versions[i-1]
            curr = self.versions[i]
            changes.append({
                "from_version": prev.version,
                "to_version": curr.version,
                "timestamp": curr.timestamp,
                "fingerprint_changed": prev.fingerprint != curr.fingerprint,
                "size_changed": prev.size_bytes != curr.size_bytes,
                "size_delta": curr.size_bytes - prev.size_bytes
            })
        return changes


class DocumentVersionManager:
    """
    Manages document versioning and change tracking.
    
    Features:
    - Track document changes over time
    - Store version history in JSON
    - Compare versions
    - Rollback support
    """
    
    def __init__(self, version_db_path: Path):
        """
        Initialize version manager.
        
        Args:
            version_db_path: Path to version database (JSON file)
        """
        self.version_db_path = version_db_path
        self.version_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing version database
        self.version_db = self._load_db()
    
    def _load_db(self) -> Dict[str, VersionHistory]:
        """Load version database from disk."""
        if not self.version_db_path.exists():
            return {}
        
        try:
            with open(self.version_db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Deserialize
            db = {}
            for doc_name, history_data in data.items():
                versions = [DocumentVersion(**v) for v in history_data['versions']]
                db[doc_name] = VersionHistory(
                    document_name=history_data['document_name'],
                    versions=versions,
                    current_version=history_data['current_version']
                )
            return db
        
        except Exception as e:
            print(f"Warning: Failed to load version DB: {e}")
            return {}
    
    def _save_db(self):
        """Save version database to disk."""
        data = {}
        for doc_name, history in self.version_db.items():
            data[doc_name] = {
                'document_name': history.document_name,
                'versions': [asdict(v) for v in history.versions],
                'current_version': history.current_version
            }
        
        with open(self.version_db_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def add_version(
        self,
        document_path: Path,
        fingerprint: str,
        page_count: Optional[int] = None,
        chunk_count: Optional[int] = None
    ) -> DocumentVersion:
        """
        Add a new version of a document.
        
        Args:
            document_path: Path to the document file
            fingerprint: SHA256 hash of the document
            page_count: Number of pages (if applicable)
            chunk_count: Number of chunks created
            
        Returns:
            DocumentVersion object
        """
        doc_name = document_path.name
        
        # Get or create history
        if doc_name not in self.version_db:
            self.version_db[doc_name] = VersionHistory(
                document_name=doc_name,
                versions=[],
                current_version=0
            )
        
        history = self.version_db[doc_name]
        
        # Check if this is actually a new version
        if history.versions:
            latest = history.get_latest()
            if latest and latest.fingerprint == fingerprint:
                # No changes, return existing version
                return latest
        
        # Create new version
        new_version = DocumentVersion(
            document_name=doc_name,
            version=history.current_version + 1,
            fingerprint=fingerprint,
            timestamp=datetime.now().isoformat(),
            size_bytes=document_path.stat().st_size if document_path.exists() else 0,
            page_count=page_count,
            chunk_count=chunk_count
        )
        
        # Update history
        history.versions.append(new_version)
        history.current_version = new_version.version
        
        # Save to disk
        self._save_db()
        
        return new_version
    
    def get_history(self, document_name: str) -> Optional[VersionHistory]:
        """Get version history for a document."""
        return self.version_db.get(document_name)
    
    def get_all_histories(self) -> Dict[str, VersionHistory]:
        """Get all version histories."""
        return self.version_db.copy()
    
    def has_changed(self, document_name: str, current_fingerprint: str) -> bool:
        """
        Check if document has changed since last version.
        
        Args:
            document_name: Name of the document
            current_fingerprint: Current SHA256 hash
            
        Returns:
            True if document changed, False otherwise
        """
        history = self.get_history(document_name)
        if not history:
            return True  # New document
        
        latest = history.get_latest()
        if not latest:
            return True
        
        return latest.fingerprint != current_fingerprint
    
    def get_changed_documents(self, current_manifest: Dict) -> List[str]:
        """
        Get list of documents that have changed.
        
        Args:
            current_manifest: Current manifest with document fingerprints
            
        Returns:
            List of document names that changed
        """
        changed = []
        
        for doc_info in current_manifest.get('documents', []):
            doc_name = doc_info['path']
            fingerprint = doc_info['fingerprint']
            
            if self.has_changed(doc_name, fingerprint):
                changed.append(doc_name)
        
        return changed
    
    def get_summary(self) -> Dict:
        """Get summary of all document versions."""
        total_docs = len(self.version_db)
        total_versions = sum(len(h.versions) for h in self.version_db.values())
        
        recently_updated = []
        for history in self.version_db.values():
            latest = history.get_latest()
            if latest:
                recently_updated.append({
                    'document': history.document_name,
                    'version': latest.version,
                    'timestamp': latest.timestamp
                })
        
        # Sort by timestamp descending
        recently_updated.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return {
            'total_documents': total_docs,
            'total_versions': total_versions,
            'average_versions_per_doc': total_versions / total_docs if total_docs > 0 else 0,
            'recently_updated': recently_updated[:10]  # Top 10
        }
