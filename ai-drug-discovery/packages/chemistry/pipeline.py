"""
Molecular Data Processing Pipeline.

Main entry point for processing molecular inputs through:
1. Parsing - SMILES, SDF/MOL, CSV/Excel
2. Normalization - Canonicalization, InChI generation
3. Computation - Descriptors, fingerprints, 2D rendering
4. Storage - Database persistence (optional)

Usage:
    # Process single molecule
    result = await process_molecule_input(
        value="CCO",
        format=InputFormat.SMILES,
        compute_descriptors=True,
        compute_fingerprints=[FingerprintType.MORGAN, FingerprintType.MACCS],
    )

    # Process batch from CSV
    results = await process_batch_input(
        csv_content=csv_data,
        skip_errors=True,
    )
"""

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.chemistry.compute import (
    DescriptorCalculator,
    FingerprintCalculator,
    MoleculeRenderer,
)
from packages.chemistry.exceptions import (
    BatchResult,
    ChemistryError,
    ChemistryErrorCode,
    ParsingError,
    RowError,
)
from packages.chemistry.normalizer import MoleculeNormalizer, NormalizationOptions
from packages.chemistry.parsers.batch import BatchParser
from packages.chemistry.parsers.molfile import MolfileParser
from packages.chemistry.parsers.smiles import SmilesParser
from packages.chemistry.schemas import (
    BatchInput,
    BatchProcessingResult,
    FingerprintType,
    InputFormat,
    MoleculeInput,
    ProcessedMolecule,
    StorageResult,
)
from packages.chemistry.storage import MoleculeStorage, MoleculeStorageData

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class PipelineOptions:
    """Options for the processing pipeline."""

    # Parsing
    sanitize: bool = True

    # Normalization
    normalize_options: NormalizationOptions = field(
        default_factory=NormalizationOptions
    )

    # Computation
    compute_descriptors: bool = True
    compute_fingerprints: list[FingerprintType] = field(
        default_factory=lambda: [FingerprintType.MORGAN, FingerprintType.MACCS]
    )
    render_svg: bool = False
    render_png: bool = False
    render_width: int = 300
    render_height: int = 300

    # Error handling
    skip_errors: bool = True  # For batch processing


class MoleculeProcessor:
    """
    Core molecule processor.

    Orchestrates parsing → normalization → computation.
    """

    def __init__(self, options: PipelineOptions | None = None):
        """
        Initialize processor.

        Args:
            options: Pipeline configuration options.
        """
        self.options = options or PipelineOptions()

        # Initialize components
        self._smiles_parser = SmilesParser(sanitize=self.options.sanitize)
        self._molfile_parser = MolfileParser(sanitize=self.options.sanitize)
        self._normalizer = MoleculeNormalizer(options=self.options.normalize_options)
        self._descriptor_calc = DescriptorCalculator()
        self._fingerprint_calc = FingerprintCalculator()
        self._renderer = MoleculeRenderer(
            width=self.options.render_width,
            height=self.options.render_height,
        )

    def process(self, input_data: MoleculeInput) -> ProcessedMolecule:
        """
        Process a single molecule input.

        Args:
            input_data: Molecule input with value and format.

        Returns:
            ProcessedMolecule with all computed data.

        Raises:
            ChemistryError: If processing fails.
        """
        warnings = []

        # Step 1: Parse input to RDKit Mol
        mol = self._parse(input_data)

        # Step 2: Normalize and get identifiers
        mol, identifiers = self._normalizer.normalize(mol)

        # Step 3: Compute descriptors
        descriptors = None
        if self.options.compute_descriptors:
            try:
                descriptors = self._descriptor_calc.calculate(mol)
            except ChemistryError as e:
                warnings.append(f"Descriptor calculation failed: {e.message}")

        # Step 4: Compute fingerprints
        fingerprints = {}
        if self.options.compute_fingerprints:
            fingerprints = self._fingerprint_calc.calculate_multiple(
                mol, self.options.compute_fingerprints
            )

        # Step 5: Render 2D structure
        svg_image = None
        png_image = None

        if self.options.render_svg:
            try:
                svg_image = self._renderer.render_svg(mol)
            except ChemistryError as e:
                warnings.append(f"SVG rendering failed: {e.message}")

        if self.options.render_png:
            try:
                png_image = self._renderer.render_png(mol)
            except ChemistryError as e:
                warnings.append(f"PNG rendering failed: {e.message}")

        return ProcessedMolecule(
            identifiers=identifiers,
            original_input=input_data.value,
            input_format=input_data.format,
            name=input_data.name,
            descriptors=descriptors,
            fingerprints=fingerprints,
            svg_image=svg_image,
            png_image=png_image,
            is_valid=True,
            warnings=warnings,
            metadata=input_data.metadata or {},
        )

    def _parse(self, input_data: MoleculeInput):
        """Parse input to RDKit Mol based on format."""
        if input_data.format == InputFormat.SMILES:
            return self._smiles_parser.parse(input_data.value).mol
        elif input_data.format == InputFormat.MOL:
            return self._molfile_parser.parse_molblock(input_data.value).mol
        elif input_data.format == InputFormat.SDF:
            # For SDF, parse first molecule only
            records = self._molfile_parser.parse_sdf_string(input_data.value)
            if not records:
                raise ParsingError(
                    message="No valid molecules in SDF",
                    code=ChemistryErrorCode.INVALID_SDF,
                )
            return records[0].mol
        elif input_data.format == InputFormat.INCHI:
            # Convert InChI to Mol
            from rdkit import Chem

            mol = Chem.MolFromInchi(input_data.value)
            if mol is None:
                raise ParsingError(
                    message=f"Invalid InChI: {input_data.value}",
                    code=ChemistryErrorCode.INVALID_SMILES,
                )
            return mol
        else:
            raise ParsingError(
                message=f"Unsupported format: {input_data.format}",
                code=ChemistryErrorCode.UNSUPPORTED_FORMAT,
            )

    def process_batch(
        self,
        molecules: list[MoleculeInput],
    ) -> BatchProcessingResult:
        """
        Process multiple molecules.

        Args:
            molecules: List of molecule inputs.

        Returns:
            BatchProcessingResult with successes and failures.
        """
        successful = []
        failed = []

        for idx, mol_input in enumerate(molecules):
            try:
                result = self.process(mol_input)
                successful.append(result)
            except ChemistryError as e:
                if not self.options.skip_errors:
                    raise
                failed.append(
                    {
                        "row_index": idx,
                        "input_value": mol_input.value,
                        "error_code": e.code.value,
                        "error_message": e.message,
                        "details": e.details,
                    }
                )
            except Exception as e:
                if not self.options.skip_errors:
                    raise
                failed.append(
                    {
                        "row_index": idx,
                        "input_value": mol_input.value,
                        "error_code": ChemistryErrorCode.UNKNOWN_ERROR.value,
                        "error_message": str(e),
                    }
                )

        return BatchProcessingResult(
            successful=successful,
            failed=failed,
            total_count=len(molecules),
            successful_count=len(successful),
            failed_count=len(failed),
        )


# =============================================================================
# Public API Functions
# =============================================================================


def process_molecule_input(
    value: str,
    format: InputFormat = InputFormat.SMILES,
    name: str | None = None,
    compute_descriptors: bool = True,
    compute_fingerprints: list[FingerprintType] | None = None,
    render_svg: bool = False,
    render_png: bool = False,
    metadata: dict | None = None,
) -> ProcessedMolecule:
    """
    Process a single molecule input.

    This is the main entry point for single molecule processing.

    Args:
        value: Molecular representation (SMILES, MOL block, InChI).
        format: Input format (default: SMILES).
        name: Optional molecule name.
        compute_descriptors: Calculate molecular descriptors.
        compute_fingerprints: Fingerprint types to compute (default: Morgan, MACCS).
        render_svg: Generate SVG image.
        render_png: Generate PNG image.
        metadata: Additional metadata.

    Returns:
        ProcessedMolecule with identifiers, descriptors, fingerprints.

    Raises:
        ParsingError: If input cannot be parsed.
        NormalizationError: If normalization fails.
        ComputationError: If computation fails.

    Example:
        >>> result = process_molecule_input("CCO", compute_descriptors=True)
        >>> print(result.identifiers.canonical_smiles)
        'CCO'
        >>> print(result.descriptors.molecular_weight)
        Decimal('46.0684')
    """
    if compute_fingerprints is None:
        compute_fingerprints = [FingerprintType.MORGAN, FingerprintType.MACCS]

    options = PipelineOptions(
        compute_descriptors=compute_descriptors,
        compute_fingerprints=compute_fingerprints,
        render_svg=render_svg,
        render_png=render_png,
    )

    processor = MoleculeProcessor(options=options)

    input_data = MoleculeInput(
        value=value,
        format=format,
        name=name,
        metadata=metadata,
    )

    return processor.process(input_data)


def process_batch_input(
    molecules: list[MoleculeInput] | None = None,
    csv_content: str | None = None,
    excel_content: bytes | None = None,
    smiles_column: str | None = None,
    skip_errors: bool = True,
    compute_descriptors: bool = True,
    compute_fingerprints: list[FingerprintType] | None = None,
) -> BatchProcessingResult:
    """
    Process multiple molecules from various input sources.

    Args:
        molecules: List of MoleculeInput objects.
        csv_content: CSV string with molecules.
        excel_content: Excel file bytes with molecules.
        smiles_column: Column name for SMILES (auto-detect if None).
        skip_errors: Continue processing if some molecules fail.
        compute_descriptors: Calculate molecular descriptors.
        compute_fingerprints: Fingerprint types to compute.

    Returns:
        BatchProcessingResult with successes and failures.

    Example:
        >>> csv = "name,smiles\\nEthanol,CCO\\nMethanol,CO"
        >>> result = process_batch_input(csv_content=csv)
        >>> print(result.successful_count)
        2
    """
    if compute_fingerprints is None:
        compute_fingerprints = [FingerprintType.MORGAN, FingerprintType.MACCS]

    # Parse input source to molecules list
    if molecules is None:
        if csv_content is not None:
            parser = BatchParser(smiles_column=smiles_column)
            parse_result = parser.parse_csv(csv_content)
            molecules = parse_result.molecules
        elif excel_content is not None:
            parser = BatchParser(smiles_column=smiles_column)
            parse_result = parser.parse_excel(excel_content)
            molecules = parse_result.molecules
        else:
            raise ValueError("Must provide molecules, csv_content, or excel_content")

    options = PipelineOptions(
        skip_errors=skip_errors,
        compute_descriptors=compute_descriptors,
        compute_fingerprints=compute_fingerprints,
    )

    processor = MoleculeProcessor(options=options)
    return processor.process_batch(molecules)


async def process_and_store(
    value: str,
    format: InputFormat,
    session: "AsyncSession",
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    name: str | None = None,
    compute_descriptors: bool = True,
    compute_fingerprints: list[FingerprintType] | None = None,
    skip_if_exists: bool = True,
    metadata: dict | None = None,
) -> tuple[ProcessedMolecule, StorageResult]:
    """
    Process a molecule and store it in the database.

    Args:
        value: Molecular representation.
        format: Input format.
        session: Database session.
        organization_id: Organization ID for multi-tenant isolation.
        created_by: User ID creating the molecule.
        name: Optional molecule name.
        compute_descriptors: Calculate descriptors.
        compute_fingerprints: Fingerprint types.
        skip_if_exists: Skip if molecule already exists.
        metadata: Additional metadata.

    Returns:
        Tuple of (ProcessedMolecule, StorageResult).

    Example:
        >>> async with get_async_session() as session:
        ...     processed, stored = await process_and_store(
        ...         value="CCO",
        ...         format=InputFormat.SMILES,
        ...         session=session,
        ...         organization_id=org_id,
        ...         created_by=user_id,
        ...     )
        ...     print(stored.is_new)
        True
    """
    if compute_fingerprints is None:
        compute_fingerprints = [FingerprintType.MORGAN, FingerprintType.MACCS]

    # Process molecule
    processed = process_molecule_input(
        value=value,
        format=format,
        name=name,
        compute_descriptors=compute_descriptors,
        compute_fingerprints=compute_fingerprints,
        metadata=metadata,
    )

    # Prepare storage data
    storage_data = MoleculeStorageData(
        identifiers=processed.identifiers,
        descriptors=processed.descriptors,
        fingerprints=processed.fingerprints,
        name=name,
        metadata=metadata,
    )

    # Store
    storage = MoleculeStorage(session=session, organization_id=organization_id)
    result = await storage.store(storage_data, created_by, skip_if_exists)

    return processed, result


async def process_and_store_batch(
    molecules: list[MoleculeInput],
    session: "AsyncSession",
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    skip_errors: bool = True,
    skip_if_exists: bool = True,
    compute_descriptors: bool = True,
    compute_fingerprints: list[FingerprintType] | None = None,
) -> tuple[BatchProcessingResult, list[StorageResult], list[RowError]]:
    """
    Process and store multiple molecules.

    Args:
        molecules: List of molecule inputs.
        session: Database session.
        organization_id: Organization ID.
        created_by: User ID.
        skip_errors: Continue on processing errors.
        skip_if_exists: Skip molecules that already exist.
        compute_descriptors: Calculate descriptors.
        compute_fingerprints: Fingerprint types.

    Returns:
        Tuple of (processing results, storage results, storage errors).
    """
    if compute_fingerprints is None:
        compute_fingerprints = [FingerprintType.MORGAN, FingerprintType.MACCS]

    # Process batch
    processing_result = process_batch_input(
        molecules=molecules,
        skip_errors=skip_errors,
        compute_descriptors=compute_descriptors,
        compute_fingerprints=compute_fingerprints,
    )

    # Prepare storage data for successful molecules
    storage_data_list = []
    for processed in processing_result.successful:
        storage_data_list.append(
            MoleculeStorageData(
                identifiers=processed.identifiers,
                descriptors=processed.descriptors,
                fingerprints=processed.fingerprints,
                name=processed.name,
                metadata=processed.metadata,
            )
        )

    # Store batch
    storage = MoleculeStorage(session=session, organization_id=organization_id)
    storage_results, storage_errors = await storage.store_batch(
        storage_data_list, created_by, skip_if_exists
    )

    return processing_result, storage_results, storage_errors
