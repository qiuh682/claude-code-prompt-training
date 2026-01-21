"""
Chemistry utilities package for molecular data processing.

This package provides a complete pipeline for:
- Parsing molecular inputs (SMILES, SDF/MOL, CSV/Excel)
- Normalizing and canonicalizing structures
- Computing descriptors and fingerprints
- Storing molecules in the database

Quick Start:
    >>> from packages.chemistry import process_molecule_input, InputFormat
    >>> result = process_molecule_input("CCO", format=InputFormat.SMILES)
    >>> print(result.identifiers.canonical_smiles)
    'CCO'
    >>> print(result.descriptors.molecular_weight)
    Decimal('46.0684')

Batch Processing:
    >>> from packages.chemistry import process_batch_input
    >>> csv = "name,smiles\\nEthanol,CCO\\nMethanol,CO"
    >>> result = process_batch_input(csv_content=csv)
    >>> print(result.successful_count)
    2
"""

# Exceptions
from packages.chemistry.exceptions import (
    BatchResult,
    ChemistryError,
    ChemistryErrorCode,
    ComputationError,
    NormalizationError,
    ParsingError,
    RowError,
    StorageError,
)

# Schemas
from packages.chemistry.schemas import (
    BatchInput,
    BatchProcessingResult,
    FingerprintData,
    FingerprintType,
    InputFormat,
    MolecularDescriptors,
    MoleculeIdentifiers,
    MoleculeInput,
    ProcessedMolecule,
    StorageResult,
)

# Parsers
from packages.chemistry.parsers import (
    BatchParser,
    MolfileParser,
    SmilesParser,
    parse_csv,
    parse_excel,
    parse_molblock,
    parse_sdf,
    parse_smiles,
)

# Normalizer
from packages.chemistry.normalizer import (
    MoleculeNormalizer,
    NormalizationOptions,
    canonicalize_smiles,
    generate_smiles_hash,
    normalize_molecule,
)

# Compute
from packages.chemistry.compute import (
    DescriptorCalculator,
    FingerprintCalculator,
    MoleculeRenderer,
    calculate_descriptors,
    calculate_fingerprint,
    calculate_fingerprints,
    render_molecule_png,
    render_molecule_svg,
)

# Storage
from packages.chemistry.storage import (
    MoleculeStorage,
    MoleculeStorageData,
)

# Pipeline (main entry points)
from packages.chemistry.pipeline import (
    MoleculeProcessor,
    PipelineOptions,
    process_and_store,
    process_and_store_batch,
    process_batch_input,
    process_molecule_input,
)

# Legacy compatibility
from packages.chemistry.utils import validate_smiles

__all__ = [
    # Exceptions
    "ChemistryError",
    "ChemistryErrorCode",
    "ParsingError",
    "NormalizationError",
    "ComputationError",
    "StorageError",
    "RowError",
    "BatchResult",
    # Schemas
    "InputFormat",
    "FingerprintType",
    "MoleculeInput",
    "BatchInput",
    "MolecularDescriptors",
    "FingerprintData",
    "MoleculeIdentifiers",
    "ProcessedMolecule",
    "BatchProcessingResult",
    "StorageResult",
    # Parsers
    "SmilesParser",
    "MolfileParser",
    "BatchParser",
    "parse_smiles",
    "parse_molblock",
    "parse_sdf",
    "parse_csv",
    "parse_excel",
    # Normalizer
    "MoleculeNormalizer",
    "NormalizationOptions",
    "normalize_molecule",
    "canonicalize_smiles",
    "generate_smiles_hash",
    # Compute
    "DescriptorCalculator",
    "FingerprintCalculator",
    "MoleculeRenderer",
    "calculate_descriptors",
    "calculate_fingerprint",
    "calculate_fingerprints",
    "render_molecule_svg",
    "render_molecule_png",
    # Storage
    "MoleculeStorage",
    "MoleculeStorageData",
    # Pipeline
    "MoleculeProcessor",
    "PipelineOptions",
    "process_molecule_input",
    "process_batch_input",
    "process_and_store",
    "process_and_store_batch",
    # Legacy
    "validate_smiles",
]
