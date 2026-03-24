import os
import json
from typing import Any, Optional, Dict


# ------------------------------------------------------------
# ---------------------- File Manager ---------------------
# ------------------------------------------------------------

class FileManager:
    """Handles file I/O operations."""
    
    @staticmethod
    def ensure_directory(path: str) -> None:
        """Create directory if it doesn't exist."""
        os.makedirs(path, exist_ok=True)
    
    @staticmethod
    def save_json(data: Any, filepath: str, atomic: bool = False) -> None:
        """Save data as JSON to file.

        Args:
            data: Data to serialize as JSON.
            filepath: Destination file path.
            atomic: When True, write to a temporary file first then rename,
                    preventing corruption if the process is interrupted mid-write.
        """
        if atomic:
            import tempfile
            dir_name = os.path.dirname(filepath) or "."
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=4)
                os.replace(tmp_path, filepath)
            except BaseException:
                # Clean up temp file on any failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        else:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
    
    @staticmethod
    def load_json(filepath: str) -> Optional[Dict[str, Any]]:
        """Load JSON from file, return None if file doesn't exist."""
        if not os.path.exists(filepath):
            return None
        
        with open(filepath, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def save_text(content: str, filepath: str) -> None:
        """Save text content to file."""
        with open(filepath, 'w') as f:
            f.write(content)
    
    @staticmethod
    def load_text(filepath: str) -> str:
        """Load text content from file."""
        with open(filepath, 'r') as f:
            return f.read()

file_manager = FileManager()
