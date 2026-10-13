import hashlib
import re
from typing import ClassVar

from backend.app.ingestion.schemas import CanonicalDocument, ChunkPayload


class DeterministicEvidenceChunker:
    """Versioned, section-aware, deterministic evidence chunker.
    
    Generates ordered EvidenceChunks respecting document sections, calculating
    exact character offsets, deterministic token estimates, and SHA-256 chunk hashes.
    """

    VERSION: ClassVar[str] = "v1.0"
    DEFAULT_CHUNK_SIZE: ClassVar[int] = 600       # Target characters per chunk
    DEFAULT_CHUNK_OVERLAP: ClassVar[int] = 80     # Sliding overlap in characters

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        version: str = VERSION,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError(f"chunk_overlap must be in [0, chunk_size), got {chunk_overlap}")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.version = version

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Deterministic token-count estimate using standard word and punctuation tokenization."""
        tokens = re.findall(r"\w+|[^\w\s]", text)
        return max(1, len(tokens))

    @staticmethod
    def compute_hash(text: str) -> str:
        """Computes SHA-256 hash of chunk content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def chunk_document(self, doc: CanonicalDocument) -> list[ChunkPayload]:
        """Splits CanonicalDocument into an ordered list of ChunkPayloads."""
        if not doc.normalized_content:
            return []

        chunks: list[ChunkPayload] = []
        chunk_index = 0

        # If sections exist, chunk section by section
        if doc.sections:
            for sec in doc.sections:
                sec_text = sec.content.strip()
                if not sec_text:
                    continue

                sec_chunks = self._chunk_text(
                    text=sec_text,
                    base_offset=sec.start_char,
                    section_name=sec.title,
                    doc=doc,
                    start_index=chunk_index,
                )
                chunks.extend(sec_chunks)
                chunk_index += len(sec_chunks)
        else:
            # Fallback: chunk whole document
            chunks = self._chunk_text(
                text=doc.normalized_content,
                base_offset=0,
                section_name=None,
                doc=doc,
                start_index=0,
            )

        return chunks

    def _chunk_text(
        self,
        text: str,
        base_offset: int,
        section_name: str | None,
        doc: CanonicalDocument,
        start_index: int,
    ) -> list[ChunkPayload]:
        """Splits a block of text into overlapping chunks, attempting natural paragraph/sentence breaks."""
        results: list[ChunkPayload] = []
        total_len = len(text)

        if total_len <= self.chunk_size:
            # Entire block fits in one chunk
            token_count = self.estimate_tokens(text)
            text_hash = self.compute_hash(text)
            results.append(
                ChunkPayload(
                    source_id=doc.source_id,
                    source_type=doc.source_type,
                    evidentiary_role=doc.evidentiary_role,
                    patient_id=doc.patient_id,
                    encounter_id=doc.encounter_id,
                    payer_id=doc.payer_id,
                    payer_policy_version_id=doc.payer_policy_version_id,
                    claim_id=doc.claim_id,
                    denial_event_id=doc.denial_event_id,
                    dataset_build_id=doc.dataset_build_id,
                    section_name=section_name,
                    chunk_index=start_index,
                    content=text,
                    token_count=token_count,
                    char_count=total_len,
                    text_hash=text_hash,
                    chunker_version=self.version,
                    source_text_offset=base_offset,
                    source_text_length=total_len,
                    effective_date=doc.effective_date,
                    metadata=doc.metadata,
                )
            )
            return results

        # Multi-chunk splitting with overlap
        start = 0
        idx = start_index

        while start < total_len:
            end = min(start + self.chunk_size, total_len)

            # If not at the end of the text, try to find a natural break point (paragraph or sentence)
            if end < total_len:
                # Look for paragraph break (\n\n) or line break (\n) or sentence period (.\s)
                window = text[start:end]
                # Try double newline
                split_pos = window.rfind("\n\n")
                if split_pos > self.chunk_size // 2:
                    end = start + split_pos + 2
                else:
                    # Try single newline
                    split_pos = window.rfind("\n")
                    if split_pos > self.chunk_size // 2:
                        end = start + split_pos + 1
                    else:
                        # Try period followed by space
                        period_pos = max(window.rfind(". "), window.rfind("; "))
                        if period_pos > self.chunk_size // 2:
                            end = start + period_pos + 2

            chunk_content = text[start:end].strip()
            if chunk_content:
                chunk_len = len(chunk_content)
                token_count = self.estimate_tokens(chunk_content)
                text_hash = self.compute_hash(chunk_content)

                results.append(
                    ChunkPayload(
                        source_id=doc.source_id,
                        source_type=doc.source_type,
                        evidentiary_role=doc.evidentiary_role,
                        patient_id=doc.patient_id,
                        encounter_id=doc.encounter_id,
                        payer_id=doc.payer_id,
                        payer_policy_version_id=doc.payer_policy_version_id,
                        claim_id=doc.claim_id,
                        denial_event_id=doc.denial_event_id,
                        dataset_build_id=doc.dataset_build_id,
                        section_name=section_name,
                        chunk_index=idx,
                        content=chunk_content,
                        token_count=token_count,
                        char_count=chunk_len,
                        text_hash=text_hash,
                        chunker_version=self.version,
                        source_text_offset=base_offset + start,
                        source_text_length=chunk_len,
                        effective_date=doc.effective_date,
                        metadata=doc.metadata,
                    )
                )
                idx += 1

            if end >= total_len:
                break

            # Slide start forward by (chunk_size - chunk_overlap)
            step = max(1, (end - start) - self.chunk_overlap)
            start = start + step

        return results
