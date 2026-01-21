"""
Molecule Repository for database operations.

Provides high-level operations for storing and retrieving molecules with
computed properties and fingerprints, with upsert support based on InChIKey.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Sequence
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class MoleculeData:
    """Input data for creating/updating a molecule."""

    # Required identifiers
    canonical_smiles: str
    inchi_key: str

    # Optional identifiers
    inchi: str | None = None
    name: str | None = None
    synonyms: list[str] | None = None

    # Descriptors (computed from RDKit)
    molecular_formula: str | None = None
    molecular_weight: Decimal | None = None
    exact_mass: Decimal | None = None
    logp: Decimal | None = None
    tpsa: Decimal | None = None
    hbd: int | None = None
    hba: int | None = None
    rotatable_bonds: int | None = None
    num_rings: int | None = None
    num_aromatic_rings: int | None = None
    num_heavy_atoms: int | None = None
    fraction_sp3: Decimal | None = None
    lipinski_violations: int | None = None

    # Fingerprints (as bytes)
    fingerprint_morgan: bytes | None = None
    fingerprint_maccs: bytes | None = None
    fingerprint_rdkit: bytes | None = None

    # Metadata
    metadata: dict[str, Any] | None = None


@dataclass
class UpsertResult:
    """Result of an upsert operation."""

    molecule_id: UUID
    created: bool  # True if new, False if updated
    inchi_key: str


@dataclass
class BulkUpsertResult:
    """Result of a bulk upsert operation."""

    total: int
    created: int
    updated: int
    failed: int
    errors: list[tuple[str, str]]  # (inchi_key, error_message)
    molecule_ids: list[UUID]


class MoleculeRepository:
    """
    Repository for molecule CRUD operations with upsert by InChIKey.

    The upsert strategy:
    - InChIKey is unique per organization
    - If molecule with same InChIKey exists, update its properties
    - If not, create new molecule

    Usage:
        repo = MoleculeRepository(session, organization_id, user_id)

        # Single upsert
        result = await repo.upsert(molecule_data)

        # Bulk upsert
        results = await repo.bulk_upsert([mol1, mol2, mol3])

        # Find by InChIKey
        molecule = await repo.find_by_inchikey("XLYOFNOQVPJJNP-UHFFFAOYSA-N")
    """

    def __init__(
        self,
        session: "AsyncSession",
        organization_id: UUID,
        user_id: UUID,
    ):
        self.session = session
        self.organization_id = organization_id
        self.user_id = user_id

    @staticmethod
    def _compute_smiles_hash(canonical_smiles: str) -> str:
        """Compute SHA-256 hash of canonical SMILES."""
        return hashlib.sha256(canonical_smiles.encode("utf-8")).hexdigest()

    async def find_by_inchikey(self, inchi_key: str) -> "Molecule | None":
        """
        Find a molecule by InChIKey within the organization.

        Args:
            inchi_key: InChIKey to search for

        Returns:
            Molecule if found, None otherwise
        """
        from sqlalchemy import select

        from db.models import Molecule

        stmt = (
            select(Molecule)
            .where(
                Molecule.organization_id == self.organization_id,
                Molecule.inchi_key == inchi_key,
                Molecule.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_smiles_hash(self, smiles_hash: str) -> "Molecule | None":
        """
        Find a molecule by SMILES hash within the organization.

        Args:
            smiles_hash: SHA-256 hash of canonical SMILES

        Returns:
            Molecule if found, None otherwise
        """
        from sqlalchemy import select

        from db.models import Molecule

        stmt = (
            select(Molecule)
            .where(
                Molecule.organization_id == self.organization_id,
                Molecule.smiles_hash == smiles_hash,
                Molecule.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, data: MoleculeData) -> UpsertResult:
        """
        Insert or update a molecule by InChIKey.

        If a molecule with the same InChIKey exists in the organization,
        update its properties. Otherwise, create a new molecule.

        Args:
            data: Molecule data to upsert

        Returns:
            UpsertResult with molecule_id and whether it was created
        """
        from db.models import Molecule

        # Check if molecule exists
        existing = await self.find_by_inchikey(data.inchi_key)

        if existing:
            # Update existing molecule
            self._update_molecule(existing, data)
            existing.updated_by = self.user_id
            await self.session.flush()
            return UpsertResult(
                molecule_id=existing.id,
                created=False,
                inchi_key=data.inchi_key,
            )
        else:
            # Create new molecule
            molecule = Molecule(
                organization_id=self.organization_id,
                canonical_smiles=data.canonical_smiles,
                inchi=data.inchi,
                inchi_key=data.inchi_key,
                smiles_hash=self._compute_smiles_hash(data.canonical_smiles),
                molecular_formula=data.molecular_formula,
                molecular_weight=data.molecular_weight,
                exact_mass=data.exact_mass,
                logp=data.logp,
                tpsa=data.tpsa,
                hbd=data.hbd,
                hba=data.hba,
                rotatable_bonds=data.rotatable_bonds,
                num_rings=data.num_rings,
                num_aromatic_rings=data.num_aromatic_rings,
                num_heavy_atoms=data.num_heavy_atoms,
                fraction_sp3=data.fraction_sp3,
                lipinski_violations=data.lipinski_violations,
                fingerprint_morgan=data.fingerprint_morgan,
                fingerprint_maccs=data.fingerprint_maccs,
                fingerprint_rdkit=data.fingerprint_rdkit,
                name=data.name,
                synonyms=data.synonyms,
                metadata_=data.metadata or {},
                created_by=self.user_id,
            )
            self.session.add(molecule)
            await self.session.flush()
            return UpsertResult(
                molecule_id=molecule.id,
                created=True,
                inchi_key=data.inchi_key,
            )

    def _update_molecule(self, molecule: "Molecule", data: MoleculeData) -> None:
        """Update molecule fields from data."""
        # Update identifiers (SMILES might be different canonicalization)
        molecule.canonical_smiles = data.canonical_smiles
        molecule.smiles_hash = self._compute_smiles_hash(data.canonical_smiles)
        if data.inchi:
            molecule.inchi = data.inchi

        # Update descriptors
        if data.molecular_formula:
            molecule.molecular_formula = data.molecular_formula
        if data.molecular_weight is not None:
            molecule.molecular_weight = data.molecular_weight
        if data.exact_mass is not None:
            molecule.exact_mass = data.exact_mass
        if data.logp is not None:
            molecule.logp = data.logp
        if data.tpsa is not None:
            molecule.tpsa = data.tpsa
        if data.hbd is not None:
            molecule.hbd = data.hbd
        if data.hba is not None:
            molecule.hba = data.hba
        if data.rotatable_bonds is not None:
            molecule.rotatable_bonds = data.rotatable_bonds
        if data.num_rings is not None:
            molecule.num_rings = data.num_rings
        if data.num_aromatic_rings is not None:
            molecule.num_aromatic_rings = data.num_aromatic_rings
        if data.num_heavy_atoms is not None:
            molecule.num_heavy_atoms = data.num_heavy_atoms
        if data.fraction_sp3 is not None:
            molecule.fraction_sp3 = data.fraction_sp3
        if data.lipinski_violations is not None:
            molecule.lipinski_violations = data.lipinski_violations

        # Update fingerprints
        if data.fingerprint_morgan:
            molecule.fingerprint_morgan = data.fingerprint_morgan
        if data.fingerprint_maccs:
            molecule.fingerprint_maccs = data.fingerprint_maccs
        if data.fingerprint_rdkit:
            molecule.fingerprint_rdkit = data.fingerprint_rdkit

        # Update naming
        if data.name:
            molecule.name = data.name
        if data.synonyms:
            molecule.synonyms = data.synonyms

        # Merge metadata
        if data.metadata:
            current_meta = molecule.metadata_ or {}
            current_meta.update(data.metadata)
            molecule.metadata_ = current_meta

    async def bulk_upsert(
        self,
        molecules: Sequence[MoleculeData],
        stop_on_error: bool = False,
    ) -> BulkUpsertResult:
        """
        Bulk upsert molecules.

        Args:
            molecules: Sequence of molecule data to upsert
            stop_on_error: If True, stop on first error; otherwise continue

        Returns:
            BulkUpsertResult with statistics
        """
        created = 0
        updated = 0
        failed = 0
        errors = []
        molecule_ids = []

        for mol_data in molecules:
            try:
                result = await self.upsert(mol_data)
                molecule_ids.append(result.molecule_id)
                if result.created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                failed += 1
                errors.append((mol_data.inchi_key, str(e)))
                if stop_on_error:
                    break

        return BulkUpsertResult(
            total=len(molecules),
            created=created,
            updated=updated,
            failed=failed,
            errors=errors,
            molecule_ids=molecule_ids,
        )

    async def store_fingerprints(
        self,
        molecule_id: UUID,
        fingerprints: dict[str, tuple[bytes, dict[str, Any]]],
    ) -> int:
        """
        Store fingerprints in the molecule_fingerprints table.

        Args:
            molecule_id: Molecule ID
            fingerprints: Dict mapping fingerprint_type to (bytes, metadata)
                         e.g., {"morgan": (fp_bytes, {"radius": 2, "num_bits": 2048})}

        Returns:
            Number of fingerprints stored
        """
        import base64

        from sqlalchemy.dialects.postgresql import insert

        from db.models import MoleculeFingerprint

        values = []
        for fp_type, (fp_bytes, meta) in fingerprints.items():
            values.append({
                "molecule_id": molecule_id,
                "fingerprint_type": fp_type,
                "fingerprint_bytes": fp_bytes,
                "fingerprint_base64": base64.b64encode(fp_bytes).decode("ascii"),
                "fingerprint_hex": fp_bytes.hex(),
                "num_bits": meta.get("num_bits", len(fp_bytes) * 8),
                "radius": meta.get("radius"),
                "use_features": meta.get("use_features", False),
                "num_on_bits": sum(bin(b).count("1") for b in fp_bytes),
            })

        if not values:
            return 0

        stmt = insert(MoleculeFingerprint).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_molecule_fingerprint_type",
            set_={
                "fingerprint_bytes": stmt.excluded.fingerprint_bytes,
                "fingerprint_base64": stmt.excluded.fingerprint_base64,
                "fingerprint_hex": stmt.excluded.fingerprint_hex,
                "num_on_bits": stmt.excluded.num_on_bits,
                "updated_at": datetime.utcnow(),
            },
        )
        await self.session.execute(stmt)
        return len(values)

    async def get_molecule_with_fingerprints(
        self,
        molecule_id: UUID,
    ) -> tuple["Molecule | None", list["MoleculeFingerprint"]]:
        """
        Get molecule with all its fingerprints.

        Args:
            molecule_id: Molecule ID

        Returns:
            Tuple of (Molecule, list of MoleculeFingerprint)
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from db.models import Molecule, MoleculeFingerprint

        stmt = (
            select(Molecule)
            .options(selectinload(Molecule.fingerprints))
            .where(
                Molecule.id == molecule_id,
                Molecule.organization_id == self.organization_id,
            )
        )
        result = await self.session.execute(stmt)
        molecule = result.scalar_one_or_none()

        if molecule:
            return molecule, list(molecule.fingerprints)
        return None, []


async def process_and_store_molecule(
    session: "AsyncSession",
    organization_id: UUID,
    user_id: UUID,
    smiles: str,
    name: str | None = None,
    compute_fingerprints: bool = True,
    store_extended_fingerprints: bool = False,
) -> UpsertResult:
    """
    High-level function to process a SMILES and store with computed properties.

    This combines:
    1. SMILES validation and canonicalization
    2. Descriptor calculation
    3. Fingerprint generation
    4. Database storage with upsert

    Args:
        session: Database session
        organization_id: Organization ID
        user_id: User ID for audit
        smiles: SMILES string to process
        name: Optional molecule name
        compute_fingerprints: Whether to compute fingerprints
        store_extended_fingerprints: Whether to store in molecule_fingerprints table

    Returns:
        UpsertResult with molecule_id
    """
    from packages.chemistry.features import (
        calculate_descriptors,
        calculate_maccs_fingerprint,
        calculate_morgan_fingerprint,
        calculate_rdkit_fingerprint,
    )
    from packages.chemistry.smiles import canonicalize_smiles

    # Canonicalize and validate
    canon_result = canonicalize_smiles(smiles, standardize=True)

    # Calculate descriptors
    descriptors = calculate_descriptors(canon_result.canonical_smiles)

    # Prepare molecule data
    mol_data = MoleculeData(
        canonical_smiles=canon_result.canonical_smiles,
        inchi_key=canon_result.inchikey,
        name=name,
        molecular_weight=descriptors.molecular_weight,
        logp=descriptors.logp,
        tpsa=descriptors.tpsa,
        hbd=descriptors.hbd,
        hba=descriptors.hba,
        rotatable_bonds=descriptors.num_rotatable_bonds,
        num_rings=descriptors.num_rings,
        num_aromatic_rings=descriptors.num_aromatic_rings,
        num_heavy_atoms=descriptors.num_heavy_atoms,
        fraction_sp3=descriptors.fraction_sp3,
        lipinski_violations=descriptors.lipinski_violations(),
    )

    # Calculate fingerprints
    if compute_fingerprints:
        fp_morgan = calculate_morgan_fingerprint(canon_result.canonical_smiles)
        fp_maccs = calculate_maccs_fingerprint(canon_result.canonical_smiles)
        fp_rdkit = calculate_rdkit_fingerprint(canon_result.canonical_smiles)

        mol_data.fingerprint_morgan = fp_morgan.bytes_data
        mol_data.fingerprint_maccs = fp_maccs.bytes_data
        mol_data.fingerprint_rdkit = fp_rdkit.bytes_data

    # Upsert to database
    repo = MoleculeRepository(session, organization_id, user_id)
    result = await repo.upsert(mol_data)

    # Optionally store extended fingerprints
    if compute_fingerprints and store_extended_fingerprints:
        await repo.store_fingerprints(
            result.molecule_id,
            {
                "morgan": (fp_morgan.bytes_data, {"radius": fp_morgan.radius, "num_bits": fp_morgan.num_bits}),
                "maccs": (fp_maccs.bytes_data, {"num_bits": fp_maccs.num_bits}),
                "rdkit": (fp_rdkit.bytes_data, {"num_bits": fp_rdkit.num_bits}),
            },
        )

    return result
