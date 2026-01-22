"""
Duplicate detection for molecule uploads.

Provides:
1. Exact duplicate detection (by InChIKey)
2. Similarity-based duplicate detection (Tanimoto on Morgan fingerprints)

For MVP performance:
- Batch InChIKey lookups
- Candidate filtering by molecular formula for similarity search
- Configurable sample size for large databases
"""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.discovery import Molecule

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ExactDuplicate:
    """Result of exact duplicate detection."""

    inchi_key: str
    existing_molecule_id: uuid.UUID
    existing_molecule_name: str | None
    source: str  # "database" or "batch" (within same upload)


@dataclass
class SimilarDuplicate:
    """Result of similarity-based duplicate detection."""

    inchi_key: str  # InChIKey of the query molecule
    similar_molecule_id: uuid.UUID
    similar_molecule_inchi_key: str
    similar_molecule_name: str | None
    similarity_score: float
    molecular_formula: str | None  # Formula used for candidate filtering


@dataclass
class DuplicateCheckResult:
    """Combined result of duplicate checking."""

    # Input molecule info
    row_number: int
    inchi_key: str
    molecular_formula: str | None

    # Duplicate results
    is_exact_duplicate: bool
    exact_duplicate: ExactDuplicate | None
    is_similar_duplicate: bool
    similar_duplicates: list[SimilarDuplicate]

    @property
    def is_duplicate(self) -> bool:
        """Check if any type of duplicate was found."""
        return self.is_exact_duplicate or self.is_similar_duplicate


@dataclass
class BatchDuplicateResult:
    """Result of batch duplicate detection."""

    total_checked: int
    exact_duplicates: list[ExactDuplicate]
    similar_duplicates: list[SimilarDuplicate]
    duplicates_in_batch: list[str]  # InChIKeys that appeared multiple times in batch

    @property
    def exact_count(self) -> int:
        return len(self.exact_duplicates)

    @property
    def similar_count(self) -> int:
        return len(self.similar_duplicates)

    @property
    def batch_duplicate_count(self) -> int:
        return len(self.duplicates_in_batch)


# =============================================================================
# Exact Duplicate Detection
# =============================================================================


async def find_exact_duplicates(
    db: AsyncSession,
    organization_id: uuid.UUID,
    inchi_keys: list[str],
) -> dict[str, Molecule]:
    """
    Find exact duplicates by InChIKey in the database.

    Performs a batch lookup for efficiency.

    Args:
        db: Database session
        organization_id: Organization to search within
        inchi_keys: List of InChIKeys to check

    Returns:
        Dict mapping InChIKey -> existing Molecule
    """
    if not inchi_keys:
        return {}

    # Remove duplicates for query efficiency
    unique_keys = list(set(inchi_keys))

    stmt = select(Molecule).where(
        Molecule.organization_id == organization_id,
        Molecule.inchi_key.in_(unique_keys),
        Molecule.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    molecules = result.scalars().all()

    return {mol.inchi_key: mol for mol in molecules}


def find_duplicates_in_batch(inchi_keys: list[str]) -> dict[str, list[int]]:
    """
    Find InChIKeys that appear multiple times within a batch.

    Args:
        inchi_keys: List of InChIKeys (index = row number - 1)

    Returns:
        Dict mapping duplicate InChIKey -> list of row indices (0-based)
    """
    seen: dict[str, list[int]] = {}
    duplicates: dict[str, list[int]] = {}

    for idx, key in enumerate(inchi_keys):
        if not key:
            continue
        if key in seen:
            if key not in duplicates:
                duplicates[key] = seen[key].copy()
            duplicates[key].append(idx)
        else:
            seen[key] = [idx]

    return duplicates


# =============================================================================
# Similarity-Based Duplicate Detection
# =============================================================================


async def find_similar_duplicates(
    db: AsyncSession,
    organization_id: uuid.UUID,
    fingerprint_bytes: bytes,
    threshold: float = 0.95,
    molecular_formula: str | None = None,
    max_candidates: int = 1000,
    limit: int = 10,
) -> list[SimilarDuplicate]:
    """
    Find molecules similar to the given fingerprint.

    For MVP performance, uses candidate filtering:
    1. If molecular_formula provided, only compare against same formula
    2. Otherwise, sample up to max_candidates molecules
    3. Calculate Tanimoto similarity and return matches above threshold

    Args:
        db: Database session
        organization_id: Organization to search within
        fingerprint_bytes: Morgan fingerprint bytes of query molecule
        threshold: Tanimoto similarity threshold (default 0.95 for near-duplicates)
        molecular_formula: Optional formula for candidate filtering
        max_candidates: Maximum candidates to check (for performance)
        limit: Maximum results to return

    Returns:
        List of SimilarDuplicate results, sorted by similarity descending
    """
    from packages.chemistry import tanimoto_similarity_bytes

    # Build candidate query
    base_query = select(Molecule).where(
        Molecule.organization_id == organization_id,
        Molecule.fingerprint_morgan.isnot(None),
        Molecule.deleted_at.is_(None),
    )

    # Filter by molecular formula if provided (faster candidate set)
    if molecular_formula:
        base_query = base_query.where(
            Molecule.molecular_formula == molecular_formula
        )

    # Limit candidates for performance
    base_query = base_query.limit(max_candidates)

    result = await db.execute(base_query)
    candidates = result.scalars().all()

    if not candidates:
        return []

    # Calculate similarities
    similar: list[SimilarDuplicate] = []
    for mol in candidates:
        if not mol.fingerprint_morgan:
            continue

        try:
            similarity = tanimoto_similarity_bytes(
                fingerprint_bytes,
                mol.fingerprint_morgan,
            )
            if similarity >= threshold:
                similar.append(SimilarDuplicate(
                    inchi_key="",  # Will be set by caller
                    similar_molecule_id=mol.id,
                    similar_molecule_inchi_key=mol.inchi_key,
                    similar_molecule_name=mol.name,
                    similarity_score=similarity,
                    molecular_formula=molecular_formula,
                ))
        except Exception as e:
            logger.warning(f"Failed to calculate similarity for molecule {mol.id}: {e}")
            continue

    # Sort by similarity descending and limit
    similar.sort(key=lambda x: x.similarity_score, reverse=True)
    return similar[:limit]


async def find_similar_duplicates_batch(
    db: AsyncSession,
    organization_id: uuid.UUID,
    molecules: list[tuple[str, bytes, str | None]],  # (inchi_key, fingerprint, formula)
    threshold: float = 0.95,
    max_candidates_per_formula: int = 500,
) -> dict[str, list[SimilarDuplicate]]:
    """
    Find similar duplicates for a batch of molecules.

    Optimizes by grouping queries by molecular formula.

    Args:
        db: Database session
        organization_id: Organization to search within
        molecules: List of (inchi_key, fingerprint_bytes, molecular_formula) tuples
        threshold: Tanimoto similarity threshold
        max_candidates_per_formula: Max candidates per formula group

    Returns:
        Dict mapping InChIKey -> list of SimilarDuplicate
    """
    from packages.chemistry import tanimoto_similarity_bytes

    results: dict[str, list[SimilarDuplicate]] = {}

    # Group molecules by formula for efficient querying
    formula_groups: dict[str | None, list[tuple[str, bytes]]] = {}
    for inchi_key, fp_bytes, formula in molecules:
        if formula not in formula_groups:
            formula_groups[formula] = []
        formula_groups[formula].append((inchi_key, fp_bytes))

    # Process each formula group
    for formula, group_molecules in formula_groups.items():
        # Get candidates for this formula
        base_query = select(Molecule).where(
            Molecule.organization_id == organization_id,
            Molecule.fingerprint_morgan.isnot(None),
            Molecule.deleted_at.is_(None),
        )

        if formula:
            base_query = base_query.where(Molecule.molecular_formula == formula)

        base_query = base_query.limit(max_candidates_per_formula)

        result = await db.execute(base_query)
        candidates = result.scalars().all()

        if not candidates:
            continue

        # Check each molecule in group against candidates
        for inchi_key, fp_bytes in group_molecules:
            similar: list[SimilarDuplicate] = []

            for candidate in candidates:
                # Skip self-comparison
                if candidate.inchi_key == inchi_key:
                    continue

                if not candidate.fingerprint_morgan:
                    continue

                try:
                    similarity = tanimoto_similarity_bytes(fp_bytes, candidate.fingerprint_morgan)
                    if similarity >= threshold:
                        similar.append(SimilarDuplicate(
                            inchi_key=inchi_key,
                            similar_molecule_id=candidate.id,
                            similar_molecule_inchi_key=candidate.inchi_key,
                            similar_molecule_name=candidate.name,
                            similarity_score=similarity,
                            molecular_formula=formula,
                        ))
                except Exception:
                    continue

            if similar:
                similar.sort(key=lambda x: x.similarity_score, reverse=True)
                results[inchi_key] = similar[:10]  # Top 10 per molecule

    return results


# =============================================================================
# Combined Duplicate Check
# =============================================================================


async def check_duplicates(
    db: AsyncSession,
    organization_id: uuid.UUID,
    inchi_key: str,
    fingerprint_bytes: bytes | None = None,
    molecular_formula: str | None = None,
    seen_in_batch: set[str] | None = None,
    similarity_threshold: float = 0.95,
    check_similar: bool = True,
) -> DuplicateCheckResult:
    """
    Check for both exact and similar duplicates.

    Args:
        db: Database session
        organization_id: Organization to search within
        inchi_key: InChIKey of molecule to check
        fingerprint_bytes: Optional fingerprint for similarity check
        molecular_formula: Optional formula for candidate filtering
        seen_in_batch: Set of InChIKeys already seen in current batch
        similarity_threshold: Tanimoto threshold for similarity
        check_similar: Whether to check for similar duplicates

    Returns:
        DuplicateCheckResult with all duplicate information
    """
    result = DuplicateCheckResult(
        row_number=0,  # Set by caller
        inchi_key=inchi_key,
        molecular_formula=molecular_formula,
        is_exact_duplicate=False,
        exact_duplicate=None,
        is_similar_duplicate=False,
        similar_duplicates=[],
    )

    # Check for duplicate in batch
    if seen_in_batch and inchi_key in seen_in_batch:
        result.is_exact_duplicate = True
        result.exact_duplicate = ExactDuplicate(
            inchi_key=inchi_key,
            existing_molecule_id=uuid.UUID(int=0),  # Placeholder
            existing_molecule_name=None,
            source="batch",
        )
        return result

    # Check for exact duplicate in database
    exact_matches = await find_exact_duplicates(db, organization_id, [inchi_key])
    if inchi_key in exact_matches:
        mol = exact_matches[inchi_key]
        result.is_exact_duplicate = True
        result.exact_duplicate = ExactDuplicate(
            inchi_key=inchi_key,
            existing_molecule_id=mol.id,
            existing_molecule_name=mol.name,
            source="database",
        )
        return result

    # Check for similar duplicates (only if not exact match and fingerprint provided)
    if check_similar and fingerprint_bytes:
        similar = await find_similar_duplicates(
            db,
            organization_id,
            fingerprint_bytes,
            threshold=similarity_threshold,
            molecular_formula=molecular_formula,
            limit=5,
        )
        if similar:
            # Update inchi_key in results
            for s in similar:
                s.inchi_key = inchi_key
            result.is_similar_duplicate = True
            result.similar_duplicates = similar

    return result


# =============================================================================
# Batch Processing
# =============================================================================


async def check_duplicates_batch(
    db: AsyncSession,
    organization_id: uuid.UUID,
    molecules: list[dict],  # List of {inchi_key, fingerprint, formula, row_number}
    similarity_threshold: float = 0.95,
    check_similar: bool = True,
) -> BatchDuplicateResult:
    """
    Check for duplicates in a batch of molecules.

    Args:
        db: Database session
        organization_id: Organization to search within
        molecules: List of molecule dicts with inchi_key, fingerprint, formula, row_number
        similarity_threshold: Tanimoto threshold
        check_similar: Whether to check for similar duplicates

    Returns:
        BatchDuplicateResult with all duplicate information
    """
    if not molecules:
        return BatchDuplicateResult(
            total_checked=0,
            exact_duplicates=[],
            similar_duplicates=[],
            duplicates_in_batch=[],
        )

    # Extract InChIKeys
    inchi_keys = [m.get("inchi_key") for m in molecules if m.get("inchi_key")]

    # Find duplicates within batch
    batch_duplicates = find_duplicates_in_batch(inchi_keys)

    # Find exact duplicates in database
    db_duplicates = await find_exact_duplicates(db, organization_id, inchi_keys)

    # Build exact duplicate results
    exact_results: list[ExactDuplicate] = []

    for mol in molecules:
        inchi_key = mol.get("inchi_key")
        if not inchi_key:
            continue

        # Check batch duplicate
        if inchi_key in batch_duplicates:
            # Only record the first occurrence
            indices = batch_duplicates[inchi_key]
            if mol.get("row_number", 0) - 1 != indices[0]:
                exact_results.append(ExactDuplicate(
                    inchi_key=inchi_key,
                    existing_molecule_id=uuid.UUID(int=0),
                    existing_molecule_name=None,
                    source="batch",
                ))

        # Check database duplicate
        elif inchi_key in db_duplicates:
            existing = db_duplicates[inchi_key]
            exact_results.append(ExactDuplicate(
                inchi_key=inchi_key,
                existing_molecule_id=existing.id,
                existing_molecule_name=existing.name,
                source="database",
            ))

    # Find similar duplicates if requested
    similar_results: list[SimilarDuplicate] = []

    if check_similar:
        # Filter molecules that have fingerprints and are not exact duplicates
        exact_keys = {e.inchi_key for e in exact_results}
        fp_molecules = [
            (m["inchi_key"], m["fingerprint"], m.get("formula"))
            for m in molecules
            if m.get("fingerprint") and m.get("inchi_key") not in exact_keys
        ]

        if fp_molecules:
            similar_map = await find_similar_duplicates_batch(
                db,
                organization_id,
                fp_molecules,
                threshold=similarity_threshold,
            )
            for similar_list in similar_map.values():
                similar_results.extend(similar_list)

    return BatchDuplicateResult(
        total_checked=len(molecules),
        exact_duplicates=exact_results,
        similar_duplicates=similar_results,
        duplicates_in_batch=list(batch_duplicates.keys()),
    )


# =============================================================================
# Summary Statistics
# =============================================================================


@dataclass
class DuplicateSummary:
    """Summary statistics for duplicate detection."""

    total_rows: int
    unique_molecules: int
    exact_duplicates_db: int  # Duplicates found in database
    exact_duplicates_batch: int  # Duplicates within the batch
    similar_duplicates: int
    highest_similarity: float | None
    formulas_checked: int  # Number of distinct formulas for candidate filtering


def summarize_duplicates(
    exact_duplicates: list[ExactDuplicate],
    similar_duplicates: list[SimilarDuplicate],
    total_rows: int,
) -> DuplicateSummary:
    """
    Create summary statistics from duplicate detection results.

    Args:
        exact_duplicates: List of exact duplicates found
        similar_duplicates: List of similar duplicates found
        total_rows: Total rows processed

    Returns:
        DuplicateSummary with statistics
    """
    db_duplicates = sum(1 for d in exact_duplicates if d.source == "database")
    batch_duplicates = sum(1 for d in exact_duplicates if d.source == "batch")

    highest_sim = None
    formulas = set()

    if similar_duplicates:
        highest_sim = max(d.similarity_score for d in similar_duplicates)
        formulas = {d.molecular_formula for d in similar_duplicates if d.molecular_formula}

    unique = total_rows - len(exact_duplicates) - len(similar_duplicates)

    return DuplicateSummary(
        total_rows=total_rows,
        unique_molecules=max(0, unique),
        exact_duplicates_db=db_duplicates,
        exact_duplicates_batch=batch_duplicates,
        similar_duplicates=len(similar_duplicates),
        highest_similarity=highest_sim,
        formulas_checked=len(formulas),
    )
