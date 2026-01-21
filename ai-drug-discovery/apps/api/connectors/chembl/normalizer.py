"""
ChEMBL data normalizer.

Transforms raw ChEMBL API responses into normalized schemas.
This layer is separate from HTTP fetching for:
- Testability (mock raw data, test normalization)
- Reusability (normalize data from files, other sources)
- Maintainability (API changes only affect this layer)
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.api.connectors.chembl.schemas import (
    AssayConditions,
    AssayTypeEnum,
    BioactivityType,
    ChEMBLAssay,
    ChEMBLBioactivity,
    ChEMBLCompound,
    ChEMBLTarget,
    RelationshipType,
)

logger = logging.getLogger(__name__)


class ChEMBLNormalizer:
    """
    Normalizes raw ChEMBL API responses to typed schemas.

    Usage:
        normalizer = ChEMBLNormalizer()

        # Normalize single compound
        raw_molecule = {"molecule_chembl_id": "CHEMBL25", ...}
        compound = normalizer.normalize_compound(raw_molecule)

        # Normalize list of bioactivities
        raw_activities = [{"activity_id": 123, ...}, ...]
        bioactivities = normalizer.normalize_bioactivities(raw_activities)
    """

    # =========================================================================
    # Type Mappings
    # =========================================================================

    ASSAY_TYPE_MAP = {
        "B": AssayTypeEnum.BINDING,
        "F": AssayTypeEnum.FUNCTIONAL,
        "A": AssayTypeEnum.ADMET,
        "T": AssayTypeEnum.TOXICITY,
        "P": AssayTypeEnum.PHYSICOCHEMICAL,
        "U": AssayTypeEnum.UNCLASSIFIED,
    }

    BIOACTIVITY_TYPE_MAP = {
        "IC50": BioactivityType.IC50,
        "EC50": BioactivityType.EC50,
        "Ki": BioactivityType.KI,
        "Kd": BioactivityType.KD,
        "AC50": BioactivityType.AC50,
        "GI50": BioactivityType.GI50,
        "LC50": BioactivityType.LC50,
        "ED50": BioactivityType.ED50,
        "Inhibition": BioactivityType.INHIBITION,
        "Activity": BioactivityType.ACTIVITY,
        "Potency": BioactivityType.POTENCY,
    }

    RELATION_MAP = {
        "=": RelationshipType.EQUALS,
        "<": RelationshipType.LESS_THAN,
        ">": RelationshipType.GREATER_THAN,
        "<=": RelationshipType.LESS_EQUAL,
        ">=": RelationshipType.GREATER_EQUAL,
        "~": RelationshipType.APPROXIMATELY,
    }

    # =========================================================================
    # Compound Normalization
    # =========================================================================

    def normalize_compound(self, raw: dict) -> ChEMBLCompound:
        """
        Normalize a single compound from ChEMBL molecule endpoint.

        Args:
            raw: Raw molecule data from ChEMBL API

        Returns:
            Normalized ChEMBLCompound
        """
        props = raw.get("molecule_properties") or {}
        structures = raw.get("molecule_structures") or {}

        return ChEMBLCompound(
            chembl_id=raw.get("molecule_chembl_id", ""),
            # Structure
            canonical_smiles=structures.get("canonical_smiles"),
            standard_inchi=structures.get("standard_inchi"),
            standard_inchi_key=structures.get("standard_inchi_key"),
            # Names
            pref_name=raw.get("pref_name"),
            synonyms=self._extract_synonyms(raw),
            # Properties
            molecular_formula=props.get("full_molformula"),
            molecular_weight=self._to_decimal(props.get("full_mwt")),
            exact_mass=self._to_decimal(props.get("mw_monoisotopic")),
            alogp=self._to_decimal(props.get("alogp")),
            hbd=self._to_int(props.get("hbd")),
            hba=self._to_int(props.get("hba")),
            psa=self._to_decimal(props.get("psa")),
            rtb=self._to_int(props.get("rtb")),
            num_ro5_violations=self._to_int(props.get("num_ro5_violations")),
            aromatic_rings=self._to_int(props.get("aromatic_rings")),
            heavy_atoms=self._to_int(props.get("heavy_atoms")),
            # Drug properties
            max_phase=self._to_int(raw.get("max_phase")),
            molecule_type=raw.get("molecule_type"),
            therapeutic_flag=raw.get("therapeutic_flag", False),
            natural_product=self._to_bool(raw.get("natural_product")),
            oral=self._to_bool(raw.get("oral")),
            # Cross-references
            pubchem_cid=self._extract_xref(raw, "PubChem"),
            drugbank_id=self._extract_xref_str(raw, "DrugBank"),
            first_approval=self._to_int(raw.get("first_approval")),
        )

    def normalize_compounds(self, raw_list: list[dict]) -> list[ChEMBLCompound]:
        """Normalize a list of compounds."""
        return [self.normalize_compound(r) for r in raw_list]

    # =========================================================================
    # Target Normalization
    # =========================================================================

    def normalize_target(self, raw: dict) -> ChEMBLTarget:
        """
        Normalize a single target from ChEMBL target endpoint.

        Args:
            raw: Raw target data from ChEMBL API

        Returns:
            Normalized ChEMBLTarget
        """
        # Extract UniProt ID and sequence from components
        uniprot_id = None
        sequence = None
        sequence_length = None

        components = raw.get("target_components") or []
        for comp in components:
            # UniProt ID
            xrefs = comp.get("target_component_xrefs") or []
            for xref in xrefs:
                if xref.get("xref_src_db") == "UniProt":
                    uniprot_id = xref.get("xref_id")
                    break

            # Sequence
            if not sequence:
                sequence = comp.get("sequence")
                if sequence:
                    sequence_length = len(sequence)

            if uniprot_id:
                break

        # Extract gene symbol from synonyms
        gene_symbol = None
        for comp in components:
            synonyms = comp.get("target_component_synonyms") or []
            for syn in synonyms:
                if syn.get("syn_type") == "GENE_SYMBOL":
                    gene_symbol = syn.get("component_synonym")
                    break
            if gene_symbol:
                break

        # Extract PDB IDs
        pdb_ids = []
        for comp in components:
            xrefs = comp.get("target_component_xrefs") or []
            for xref in xrefs:
                if xref.get("xref_src_db") == "PDBe":
                    pdb_id = xref.get("xref_id")
                    if pdb_id:
                        pdb_ids.append(pdb_id)

        return ChEMBLTarget(
            chembl_id=raw.get("target_chembl_id", ""),
            uniprot_id=uniprot_id,
            gene_symbol=gene_symbol,
            pref_name=raw.get("pref_name", ""),
            target_type=raw.get("target_type"),
            organism=raw.get("organism", "Homo sapiens"),
            tax_id=self._to_int(raw.get("tax_id")),
            target_class=self._extract_target_class(raw),
            protein_class=self._extract_protein_classes(raw),
            sequence=sequence,
            sequence_length=sequence_length,
            pdb_ids=pdb_ids[:20],  # Limit PDB IDs
            description=raw.get("target_description"),
        )

    def normalize_targets(self, raw_list: list[dict]) -> list[ChEMBLTarget]:
        """Normalize a list of targets."""
        return [self.normalize_target(r) for r in raw_list]

    # =========================================================================
    # Assay Normalization
    # =========================================================================

    def normalize_assay(self, raw: dict) -> ChEMBLAssay:
        """
        Normalize a single assay from ChEMBL assay endpoint.

        Args:
            raw: Raw assay data from ChEMBL API

        Returns:
            Normalized ChEMBLAssay
        """
        assay_type_str = raw.get("assay_type", "U")
        assay_type = self.ASSAY_TYPE_MAP.get(assay_type_str, AssayTypeEnum.UNCLASSIFIED)

        return ChEMBLAssay(
            chembl_id=raw.get("assay_chembl_id", ""),
            target_chembl_id=raw.get("target_chembl_id"),
            assay_type=assay_type,
            assay_type_description=raw.get("assay_type_description"),
            description=raw.get("description"),
            assay_category=raw.get("assay_category"),
            conditions=AssayConditions(
                cell_type=raw.get("assay_cell_type"),
                tissue=raw.get("assay_tissue"),
                subcellular_fraction=raw.get("assay_subcellular_fraction"),
                assay_organism=raw.get("assay_organism"),
                assay_strain=raw.get("assay_strain"),
                assay_tax_id=self._to_int(raw.get("assay_tax_id")),
            ),
            confidence_score=self._to_int(raw.get("confidence_score")),
            confidence_description=raw.get("confidence_description"),
            src_id=self._to_int(raw.get("src_id")),
            src_description=raw.get("src_description"),
            document_chembl_id=raw.get("document_chembl_id"),
            bao_format=raw.get("bao_format"),
            bao_label=raw.get("bao_label"),
        )

    def normalize_assays(self, raw_list: list[dict]) -> list[ChEMBLAssay]:
        """Normalize a list of assays."""
        return [self.normalize_assay(r) for r in raw_list]

    # =========================================================================
    # Bioactivity Normalization
    # =========================================================================

    def normalize_bioactivity(self, raw: dict) -> ChEMBLBioactivity:
        """
        Normalize a single bioactivity from ChEMBL activity endpoint.

        Args:
            raw: Raw activity data from ChEMBL API

        Returns:
            Normalized ChEMBLBioactivity
        """
        standard_type_str = raw.get("standard_type", "")
        standard_type = self.BIOACTIVITY_TYPE_MAP.get(
            standard_type_str, BioactivityType.OTHER
        )

        standard_relation_str = raw.get("standard_relation")
        standard_relation = self.RELATION_MAP.get(standard_relation_str)

        return ChEMBLBioactivity(
            activity_id=raw.get("activity_id", 0),
            molecule_chembl_id=raw.get("molecule_chembl_id", ""),
            target_chembl_id=raw.get("target_chembl_id"),
            assay_chembl_id=raw.get("assay_chembl_id", ""),
            # Standard values
            standard_type=standard_type,
            standard_value=self._to_decimal(raw.get("standard_value")),
            standard_units=raw.get("standard_units"),
            standard_relation=standard_relation,
            # Published values
            published_type=raw.get("published_type"),
            published_value=self._to_decimal(raw.get("published_value")),
            published_units=raw.get("published_units"),
            published_relation=raw.get("published_relation"),
            # Classification
            activity_comment=raw.get("activity_comment"),
            data_validity_comment=raw.get("data_validity_comment"),
            potential_duplicate=self._to_bool(raw.get("potential_duplicate")),
            pchembl_value=self._to_decimal(raw.get("pchembl_value")),
            # Ligand efficiency
            ligand_efficiency_bei=self._to_decimal(
                raw.get("ligand_efficiency", {}).get("bei")
            ),
            ligand_efficiency_le=self._to_decimal(
                raw.get("ligand_efficiency", {}).get("le")
            ),
            ligand_efficiency_lle=self._to_decimal(
                raw.get("ligand_efficiency", {}).get("lle")
            ),
            ligand_efficiency_sei=self._to_decimal(
                raw.get("ligand_efficiency", {}).get("sei")
            ),
            # Source
            document_chembl_id=raw.get("document_chembl_id"),
            src_id=self._to_int(raw.get("src_id")),
        )

    def normalize_bioactivities(self, raw_list: list[dict]) -> list[ChEMBLBioactivity]:
        """Normalize a list of bioactivities."""
        return [self.normalize_bioactivity(r) for r in raw_list]

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _to_decimal(self, value: Any) -> Decimal | None:
        """Safely convert value to Decimal."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    def _to_int(self, value: Any) -> int | None:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _to_bool(self, value: Any) -> bool:
        """Convert value to bool."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    def _extract_synonyms(self, raw: dict) -> list[str]:
        """Extract synonyms from molecule data."""
        synonyms = []
        syn_list = raw.get("molecule_synonyms") or []
        for syn in syn_list:
            if isinstance(syn, dict):
                name = syn.get("molecule_synonym") or syn.get("synonyms")
                if name:
                    synonyms.append(name)
            elif isinstance(syn, str):
                synonyms.append(syn)
        return synonyms[:30]  # Limit to 30

    def _extract_xref(self, raw: dict, db_name: str) -> int | None:
        """Extract numeric cross-reference ID."""
        xrefs = raw.get("cross_references") or []
        for xref in xrefs:
            if xref.get("xref_src") == db_name:
                try:
                    return int(xref.get("xref_id"))
                except (ValueError, TypeError):
                    pass
        return None

    def _extract_xref_str(self, raw: dict, db_name: str) -> str | None:
        """Extract string cross-reference ID."""
        xrefs = raw.get("cross_references") or []
        for xref in xrefs:
            if xref.get("xref_src") == db_name:
                return xref.get("xref_id")
        return None

    def _extract_target_class(self, raw: dict) -> str | None:
        """Extract primary target class."""
        components = raw.get("target_components") or []
        for comp in components:
            classes = comp.get("protein_classifications") or []
            if classes:
                # Return the most specific (last in hierarchy)
                return classes[-1].get("protein_classification_id")
        return None

    def _extract_protein_classes(self, raw: dict) -> list[str]:
        """Extract all protein classification labels."""
        classes = []
        components = raw.get("target_components") or []
        for comp in components:
            pc_list = comp.get("protein_classifications") or []
            for pc in pc_list:
                label = pc.get("protein_classification_id")
                if label and label not in classes:
                    classes.append(label)
        return classes[:10]
