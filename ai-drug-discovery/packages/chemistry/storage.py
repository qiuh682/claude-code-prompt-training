"""
Molecular data storage interface.

Provides:
- Molecule storage to PostgreSQL
- Duplicate detection by InChIKey
- Fingerprint indexing strategy
- Batch storage operations
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.chemistry.exceptions import ChemistryErrorCode, RowError, StorageError
from packages.chemistry.schemas import (
    FingerprintData,
    FingerprintType,
    MolecularDescriptors,
    MoleculeIdentifiers,
    StorageResult,
)


@dataclass
class MoleculeStorageData:
    """Data to store for a molecule."""

    identifiers: MoleculeIdentifiers
    descriptors: MolecularDescriptors | None = None
    fingerprints: dict[FingerprintType, FingerprintData] | None = None
    name: str | None = None
    metadata: dict | None = None


class MoleculeStorage:
    """Storage interface for molecules."""

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID):
        """
        Initialize storage.

        Args:
            session: SQLAlchemy async session.
            organization_id: Organization ID for multi-tenant isolation.
        """
        self.session = session
        self.organization_id = organization_id

    async def store(
        self,
        data: MoleculeStorageData,
        created_by: uuid.UUID,
        skip_if_exists: bool = True,
    ) -> StorageResult:
        """
        Store a molecule in the database.

        Args:
            data: Molecule data to store.
            created_by: User ID creating the molecule.
            skip_if_exists: If True, return existing molecule; if False, raise error.

        Returns:
            StorageResult with molecule ID and status.

        Raises:
            StorageError: If storage fails.
        """
        # Import model here to avoid circular imports
        from db.models.discovery import Molecule

        try:
            # Check for existing molecule by InChIKey
            existing = await self._find_by_inchikey(data.identifiers.inchi_key)

            if existing:
                if skip_if_exists:
                    return StorageResult(
                        molecule_id=str(existing.id),
                        inchi_key=data.identifiers.inchi_key,
                        is_new=False,
                        message="Molecule already exists",
                    )
                else:
                    raise StorageError(
                        message=f"Molecule with InChIKey {data.identifiers.inchi_key} already exists",
                        code=ChemistryErrorCode.DUPLICATE_MOLECULE,
                        details={"existing_id": str(existing.id)},
                    )

            # Build molecule record
            molecule = Molecule(
                id=uuid.uuid4(),
                organization_id=self.organization_id,
                canonical_smiles=data.identifiers.canonical_smiles,
                inchi=data.identifiers.inchi,
                inchi_key=data.identifiers.inchi_key,
                smiles_hash=data.identifiers.smiles_hash,
                name=data.name,
                created_by=created_by,
                updated_by=created_by,
            )

            # Add descriptors if available
            if data.descriptors:
                molecule.molecular_formula = data.descriptors.molecular_formula
                molecule.molecular_weight = data.descriptors.molecular_weight
                molecule.exact_mass = data.descriptors.exact_mass
                molecule.logp = data.descriptors.logp
                molecule.hbd = data.descriptors.hbd
                molecule.hba = data.descriptors.hba
                molecule.tpsa = data.descriptors.tpsa
                molecule.rotatable_bonds = data.descriptors.rotatable_bonds

            # Add fingerprints if available
            if data.fingerprints:
                if FingerprintType.MORGAN in data.fingerprints:
                    molecule.fingerprint_morgan = data.fingerprints[
                        FingerprintType.MORGAN
                    ].bits
                if FingerprintType.MACCS in data.fingerprints:
                    molecule.fingerprint_maccs = data.fingerprints[
                        FingerprintType.MACCS
                    ].bits

            # Add metadata
            if data.metadata:
                molecule.metadata_ = data.metadata

            self.session.add(molecule)
            await self.session.flush()

            return StorageResult(
                molecule_id=str(molecule.id),
                inchi_key=data.identifiers.inchi_key,
                is_new=True,
                message="Molecule created successfully",
            )

        except StorageError:
            raise
        except Exception as e:
            raise StorageError(
                message=f"Failed to store molecule: {e}",
                code=ChemistryErrorCode.STORAGE_FAILED,
                details={"error": str(e)},
            )

    async def store_batch(
        self,
        molecules: list[MoleculeStorageData],
        created_by: uuid.UUID,
        skip_if_exists: bool = True,
    ) -> tuple[list[StorageResult], list[RowError]]:
        """
        Store multiple molecules.

        Args:
            molecules: List of molecule data to store.
            created_by: User ID creating the molecules.
            skip_if_exists: If True, skip existing molecules.

        Returns:
            Tuple of (successful results, errors).
        """
        results = []
        errors = []

        for idx, data in enumerate(molecules):
            try:
                result = await self.store(data, created_by, skip_if_exists)
                results.append(result)
            except StorageError as e:
                errors.append(
                    RowError(
                        row_index=idx,
                        input_value=data.identifiers.canonical_smiles,
                        error_code=e.code,
                        error_message=e.message,
                        details=e.details,
                    )
                )
            except Exception as e:
                errors.append(
                    RowError(
                        row_index=idx,
                        input_value=data.identifiers.canonical_smiles,
                        error_code=ChemistryErrorCode.STORAGE_FAILED,
                        error_message=str(e),
                    )
                )

        return results, errors

    async def _find_by_inchikey(self, inchi_key: str):
        """Find molecule by InChIKey within organization."""
        from db.models.discovery import Molecule

        stmt = select(Molecule).where(
            Molecule.organization_id == self.organization_id,
            Molecule.inchi_key == inchi_key,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_smiles_hash(self, smiles_hash: str):
        """Find molecule by SMILES hash within organization."""
        from db.models.discovery import Molecule

        stmt = select(Molecule).where(
            Molecule.organization_id == self.organization_id,
            Molecule.smiles_hash == smiles_hash,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_id(self, molecule_id: uuid.UUID):
        """Find molecule by ID."""
        from db.models.discovery import Molecule

        stmt = select(Molecule).where(
            Molecule.id == molecule_id,
            Molecule.organization_id == self.organization_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_fingerprints(
        self,
        molecule_id: uuid.UUID,
        fingerprints: dict[FingerprintType, FingerprintData],
        updated_by: uuid.UUID,
    ) -> bool:
        """
        Update fingerprints for an existing molecule.

        Args:
            molecule_id: Molecule ID.
            fingerprints: Fingerprints to update.
            updated_by: User ID making the update.

        Returns:
            True if updated, False if molecule not found.
        """
        from db.models.discovery import Molecule

        molecule = await self.find_by_id(molecule_id)
        if not molecule:
            return False

        if FingerprintType.MORGAN in fingerprints:
            molecule.fingerprint_morgan = fingerprints[FingerprintType.MORGAN].bits
        if FingerprintType.MACCS in fingerprints:
            molecule.fingerprint_maccs = fingerprints[FingerprintType.MACCS].bits

        molecule.updated_by = updated_by
        await self.session.flush()
        return True


# Fingerprint indexing strategy documentation
"""
Fingerprint Indexing Strategy for Similarity Search
====================================================

The Molecule table stores fingerprints as LargeBinary (BYTEA in PostgreSQL).
For efficient similarity search, consider these indexing strategies:

1. RDKit PostgreSQL Extension (Recommended for production)
   ----------------------------------------------------------
   If using the RDKit PostgreSQL extension (rdkit), you can:
   - Store fingerprints as native mol/bfp types
   - Use GiST indexes for efficient Tanimoto similarity search

   Example:
   ```sql
   -- Create extension
   CREATE EXTENSION IF NOT EXISTS rdkit;

   -- Add native fingerprint column
   ALTER TABLE molecules ADD COLUMN fp_morgan bfp;

   -- Create GiST index
   CREATE INDEX idx_molecules_fp_morgan ON molecules USING gist(fp_morgan);

   -- Query similar molecules (Tanimoto > 0.7)
   SELECT * FROM molecules
   WHERE fp_morgan % morganbv_fp('CCO'::mol)
   AND tanimoto_sml(fp_morgan, morganbv_fp('CCO'::mol)) > 0.7;
   ```

2. Application-level Similarity (Current approach)
   -------------------------------------------------
   Without RDKit extension, compute similarity in Python:

   ```python
   from rdkit import DataStructs

   def tanimoto_similarity(fp1_bytes: bytes, fp2_bytes: bytes) -> float:
       # Convert bytes back to fingerprints
       fp1 = DataStructs.CreateFromBinaryText(fp1_bytes)
       fp2 = DataStructs.CreateFromBinaryText(fp2_bytes)
       return DataStructs.TanimotoSimilarity(fp1, fp2)
   ```

   For screening:
   - First filter by bit count (num_on_bits) to reduce candidates
   - Then compute exact Tanimoto on filtered set

3. pgvector for Approximate Nearest Neighbor
   ------------------------------------------
   Convert fingerprints to vectors and use pgvector:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;

   ALTER TABLE molecules ADD COLUMN fp_morgan_vec vector(2048);
   CREATE INDEX ON molecules USING ivfflat (fp_morgan_vec vector_cosine_ops);
   ```

   Note: Cosine similarity on binary vectors approximates Tanimoto.

4. Bit Count Pre-filtering
   -------------------------
   Store on-bit count for quick pre-filtering:

   ```sql
   ALTER TABLE molecules ADD COLUMN fp_morgan_bits INT;
   CREATE INDEX ON molecules (fp_morgan_bits);

   -- Pre-filter: Tanimoto > 0.7 requires bit count within range
   -- If query has N bits, target must have between N*0.7 and N/0.7 bits
   ```

Recommendation:
- For < 1M molecules: Application-level similarity with pre-filtering
- For > 1M molecules: RDKit PostgreSQL extension or pgvector
"""
