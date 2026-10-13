"""FAISS vector index manager for dense semantic similarity search with atomic persistence and validation."""

import hashlib
from pathlib import Path
from uuid import UUID

import faiss
import numpy as np

from backend.app.retrieval.schemas import IndexBuildManifest


class FAISSVectorIndex:
    """CPU-based FAISS Inner Product (Cosine Similarity) index with canonical chunk ID mapping."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)
        self.chunk_ids: list[UUID] = []
        self._id_to_pos: dict[UUID, int] = {}

    @property
    def total_vectors(self) -> int:
        return self.index.ntotal

    def add_vectors(self, vectors: np.ndarray, chunk_ids: list[UUID]) -> None:
        """Add normalized vectors and link to ordered canonical chunk UUIDs."""
        if len(vectors) != len(chunk_ids):
            raise ValueError(f"Vector count ({len(vectors)}) must match chunk_ids count ({len(chunk_ids)})")

        if len(vectors) == 0:
            return

        if vectors.shape[1] != self.dimension:
            raise ValueError(f"Vector dimension {vectors.shape[1]} does not match index dimension {self.dimension}")

        start_pos = len(self.chunk_ids)
        self.index.add(vectors.astype(np.float32))

        for idx, cid in enumerate(chunk_ids):
            self.chunk_ids.append(cid)
            self._id_to_pos[cid] = start_pos + idx

    def search(self, query_vector: np.ndarray, top_k: int = 50) -> list[tuple[UUID, float, int]]:
        """Search top_k nearest neighbors by cosine similarity.
        
        Returns:
            list of (chunk_id, similarity_score, rank_1_based)
        """
        if self.index.ntotal == 0:
            return []

        top_k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vector.astype(np.float32), top_k)

        results: list[tuple[UUID, float, int]] = []
        for rank_idx, (score, vec_idx) in enumerate(zip(scores[0], indices[0], strict=False)):
            if vec_idx < 0 or vec_idx >= len(self.chunk_ids):
                continue
            chunk_id = self.chunk_ids[vec_idx]
            results.append((chunk_id, float(score), rank_idx + 1))

        return results

    def save(self, index_dir: Path, index_id: str, dataset_build_id: str, chunker_version: str, corpus_hashes: list[str]) -> IndexBuildManifest:
        """Atomically persist FAISS binary index and build manifest."""
        index_dir.mkdir(parents=True, exist_ok=True)
        target_faiss = index_dir / f"{index_id}.faiss"
        target_manifest = index_dir / f"{index_id}_manifest.json"

        tmp_faiss = index_dir / f"{index_id}.faiss.tmp"
        tmp_manifest = index_dir / f"{index_id}_manifest.json.tmp"

        # 1. Write binary index to tmp
        faiss.write_index(self.index, str(tmp_faiss))

        # 2. Calculate index file hash
        hasher = hashlib.sha256()
        with open(tmp_faiss, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        faiss_hash = hasher.hexdigest()

        # 3. Calculate corpus fingerprint
        corpus_fingerprint = self.compute_corpus_fingerprint(corpus_hashes)

        # 4. Construct manifest
        from datetime import UTC, datetime
        manifest = IndexBuildManifest(
            index_id=index_id,
            dataset_build_id=dataset_build_id,
            embedding_model="BAAI/bge-small-en-v1.5",
            embedding_dimension=self.dimension,
            metric="INNER_PRODUCT",
            normalized=True,
            chunker_version=chunker_version,
            chunk_count=self.index.ntotal,
            chunk_ids=[str(cid) for cid in self.chunk_ids],
            corpus_fingerprint=corpus_fingerprint,
            faiss_index_hash=faiss_hash,
            status="READY",
            created_at=datetime.now(UTC).isoformat(),
        )

        with open(tmp_manifest, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        # 5. Atomic rename
        tmp_faiss.replace(target_faiss)
        tmp_manifest.replace(target_manifest)

        return manifest

    @classmethod
    def load(cls, index_dir: Path, index_id: str) -> tuple["FAISSVectorIndex", IndexBuildManifest]:
        """Load and validate FAISS index and manifest."""
        faiss_path = index_dir / f"{index_id}.faiss"
        manifest_path = index_dir / f"{index_id}_manifest.json"

        if not faiss_path.exists():
            raise FileNotFoundError(f"FAISS index file not found at {faiss_path}")
        if not manifest_path.exists():
            raise FileNotFoundError(f"Index manifest file not found at {manifest_path}")

        # 1. Load manifest
        with open(manifest_path, encoding="utf-8") as f:
            manifest = IndexBuildManifest.model_validate_json(f.read())

        # 2. Verify faiss hash
        hasher = hashlib.sha256()
        with open(faiss_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        calculated_hash = hasher.hexdigest()

        if calculated_hash != manifest.faiss_index_hash:
            raise ValueError(
                f"FAISS index integrity violation: expected hash {manifest.faiss_index_hash}, "
                f"calculated {calculated_hash}"
            )

        # 3. Read index
        index = faiss.read_index(str(faiss_path))
        if index.ntotal != manifest.chunk_count:
            raise ValueError(f"Vector count mismatch: manifest says {manifest.chunk_count}, index has {index.ntotal}")
        if index.d != manifest.embedding_dimension:
            raise ValueError(f"Dimension mismatch: expected {manifest.embedding_dimension}, index has {index.d}")

        instance = cls(dimension=manifest.embedding_dimension)
        instance.index = index
        instance.chunk_ids = [UUID(cid) for cid in manifest.chunk_ids]
        instance._id_to_pos = {cid: idx for idx, cid in enumerate(instance.chunk_ids)}

        return instance, manifest

    @staticmethod
    def compute_corpus_fingerprint(chunk_hashes: list[str]) -> str:
        """Compute SHA-256 fingerprint from sorted active chunk content hashes."""
        sorted_hashes = sorted(chunk_hashes)
        return hashlib.sha256("".join(sorted_hashes).encode("utf-8")).hexdigest()
