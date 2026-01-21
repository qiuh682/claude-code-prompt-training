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

# Batch CSV/Excel import
from packages.chemistry.batch_import import (
    BatchImporter,
    BatchImportResult,
    ColumnMapping,
    FileType,
    ImportedMolecule,
    ImportErrorCode,
    RowError as ImportRowError,
    auto_detect_mapping,
    detect_file_type,
    import_molecules_from_csv,
    import_molecules_from_excel,
    import_molecules_from_file,
    read_tabular_file,
    validate_mapping,
)

# SDF/MOL parsing (dedicated module)
from packages.chemistry.sdf_parser import (
    MoleculeIdentifiers as SDFMoleculeIdentifiers,
    ParsedMolecule,
    ParseError,
    SDFErrorCode,
    SDFParseError,
    SDFParseResult,
    SDFParser,
    iter_sdf_file,
    parse_mol_block as parse_mol_block_sdf,
    parse_sdf_bytes,
    parse_sdf_file,
    parse_sdf_string,
)

# SMILES processing (dedicated module)
from packages.chemistry.smiles import (
    CanonicalizeResult,
    SmilesError,
    SmilesErrorCode,
    ValidationResult,
    canonicalize_smiles_batch,
    get_molecular_formula,
    smiles_are_equivalent,
    smiles_to_mol,
    validate_smiles_batch,
    validate_smiles_detailed,
)

# Legacy compatibility (basic validation)
from packages.chemistry.utils import validate_smiles

# Override with RDKit-based validation
from packages.chemistry.smiles import validate_smiles, canonicalize_smiles

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
    # Batch CSV/Excel import
    "BatchImporter",
    "BatchImportResult",
    "ColumnMapping",
    "FileType",
    "ImportedMolecule",
    "ImportErrorCode",
    "ImportRowError",
    "import_molecules_from_file",
    "import_molecules_from_csv",
    "import_molecules_from_excel",
    "auto_detect_mapping",
    "detect_file_type",
    "read_tabular_file",
    "validate_mapping",
    # SDF/MOL parsing
    "SDFParser",
    "SDFParseResult",
    "SDFParseError",
    "SDFErrorCode",
    "ParsedMolecule",
    "ParseError",
    "SDFMoleculeIdentifiers",
    "parse_sdf_file",
    "parse_sdf_string",
    "parse_sdf_bytes",
    "parse_mol_block_sdf",
    "iter_sdf_file",
    # SMILES processing
    "validate_smiles",
    "validate_smiles_detailed",
    "validate_smiles_batch",
    "canonicalize_smiles",
    "canonicalize_smiles_batch",
    "smiles_to_mol",
    "smiles_are_equivalent",
    "get_molecular_formula",
    "SmilesError",
    "SmilesErrorCode",
    "ValidationResult",
    "CanonicalizeResult",
]
