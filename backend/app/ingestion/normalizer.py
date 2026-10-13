import hashlib
import re
import unicodedata


class SafeTextNormalizer:
    """Deterministic, clinical-safe text normalizer.
    
    Removes layout formatting noise and inconsistent newlines without altering
    clinical meaning, numbers, units, dosages, negation, or diagnosis/procedure codes.
    """

    @staticmethod
    def compute_hash(text: str) -> str:
        """Computes SHA-256 hash of text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @classmethod
    def normalize(cls, raw_text: str | None) -> tuple[str, str]:
        """Normalizes raw text safely and returns (normalized_text, content_hash).
        
        Raises ValueError if content is empty or contains only whitespace.
        """
        if raw_text is None:
            raise ValueError("Document content is None")

        # 1. Unicode normalization (NFKC)
        normalized = unicodedata.normalize("NFKC", raw_text)

        # 2. Convert Windows \r\n and old Mac \r to standard \n
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

        # 3. Strip trailing whitespace from each line while preserving indentation
        lines = [line.rstrip() for line in normalized.split("\n")]
        normalized = "\n".join(lines)

        # 4. Collapse 3 or more consecutive blank lines to standard paragraph separation (\n\n)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)

        # 5. Trim leading and trailing whitespace of entire document
        normalized = normalized.strip()

        if not normalized:
            raise ValueError("Document content is empty or whitespace-only")

        content_hash = cls.compute_hash(normalized)
        return normalized, content_hash
