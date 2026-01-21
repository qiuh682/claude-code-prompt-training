"""
DrugBank data normalizer.

Transforms raw DrugBank API responses and local XML/CSV data into normalized schemas.
This layer is separate from data fetching for:
- Testability (mock raw data, test normalization)
- Reusability (normalize data from API or local files)
- Maintainability (format changes only affect this layer)
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.api.connectors.drugbank.schemas import (
    ADMETProperties,
    DrugBankDrug,
    DrugCategory,
    DrugGroup,
    DrugInteraction,
    DrugSearchHit,
    DrugSynonym,
    DrugTargetInteraction,
    DrugType,
    ExternalIdentifier,
    TargetAction,
    TargetType,
)

logger = logging.getLogger(__name__)


class DrugBankNormalizer:
    """
    Normalizes raw DrugBank data to typed schemas.

    Handles both API responses and local XML/CSV data formats.

    Usage:
        normalizer = DrugBankNormalizer()

        # Normalize from API
        raw_drug = await client.get_drug("DB00945")
        drug = normalizer.normalize_drug(raw_drug)

        # Normalize from local reader
        raw_drug = await reader.get_drug("DB00945")
        drug = normalizer.normalize_drug(raw_drug, source="local")
    """

    # =========================================================================
    # Mappings
    # =========================================================================

    DRUG_TYPE_MAP = {
        "small molecule": DrugType.SMALL_MOLECULE,
        "small_molecule": DrugType.SMALL_MOLECULE,
        "biotech": DrugType.BIOTECH,
        "biologics": DrugType.BIOTECH,
    }

    GROUP_MAP = {
        "approved": DrugGroup.APPROVED,
        "investigational": DrugGroup.INVESTIGATIONAL,
        "experimental": DrugGroup.EXPERIMENTAL,
        "withdrawn": DrugGroup.WITHDRAWN,
        "nutraceutical": DrugGroup.NUTRACEUTICAL,
        "illicit": DrugGroup.ILLICIT,
        "vet_approved": DrugGroup.VET_APPROVED,
    }

    ACTION_MAP = {
        "inhibitor": TargetAction.INHIBITOR,
        "agonist": TargetAction.AGONIST,
        "antagonist": TargetAction.ANTAGONIST,
        "binder": TargetAction.BINDER,
        "activator": TargetAction.ACTIVATOR,
        "modulator": TargetAction.MODULATOR,
        "blocker": TargetAction.BLOCKER,
        "inducer": TargetAction.INDUCER,
        "substrate": TargetAction.SUBSTRATE,
        "carrier": TargetAction.CARRIER,
        "transporter": TargetAction.TRANSPORTER,
    }

    TARGET_TYPE_MAP = {
        "target": TargetType.TARGET,
        "enzyme": TargetType.ENZYME,
        "carrier": TargetType.CARRIER,
        "transporter": TargetType.TRANSPORTER,
    }

    # =========================================================================
    # Drug Normalization
    # =========================================================================

    def normalize_drug(self, raw: dict, source: str = "api") -> DrugBankDrug:
        """
        Normalize drug data from API or local source.

        Args:
            raw: Raw drug data
            source: Data source ("api" or "local")

        Returns:
            Normalized DrugBankDrug
        """
        if source == "local":
            return self._normalize_drug_local(raw)
        return self._normalize_drug_api(raw)

    def _normalize_drug_api(self, raw: dict) -> DrugBankDrug:
        """Normalize drug from API response."""
        # Drug type
        drug_type_str = raw.get("type", "").lower()
        drug_type = self.DRUG_TYPE_MAP.get(drug_type_str, DrugType.UNKNOWN)

        # Groups
        groups = []
        for g in raw.get("groups", []):
            group_str = g.lower() if isinstance(g, str) else ""
            if group_str in self.GROUP_MAP:
                groups.append(self.GROUP_MAP[group_str])

        # Synonyms
        synonyms = []
        for syn in raw.get("synonyms", []):
            if isinstance(syn, dict):
                synonyms.append(DrugSynonym(
                    name=syn.get("name", ""),
                    language=syn.get("language"),
                    coder=syn.get("coder"),
                ))
            elif isinstance(syn, str):
                synonyms.append(DrugSynonym(name=syn))

        # Categories
        categories = []
        for cat in raw.get("categories", []):
            if isinstance(cat, dict):
                categories.append(DrugCategory(
                    category=cat.get("category", ""),
                    mesh_id=cat.get("mesh_id"),
                ))
            elif isinstance(cat, str):
                categories.append(DrugCategory(category=cat))

        # External identifiers
        ext_ids = []
        chembl_id = None
        pubchem_cid = None
        kegg_id = None
        chebi_id = None
        pdb_ids = []

        for ext in raw.get("external_identifiers", []) or raw.get("external_ids", []):
            resource = ext.get("resource", "")
            identifier = ext.get("identifier", "")
            ext_ids.append(ExternalIdentifier(resource=resource, identifier=identifier))

            # Extract specific IDs
            resource_lower = resource.lower()
            if "chembl" in resource_lower:
                chembl_id = identifier
            elif "pubchem" in resource_lower and "compound" in resource_lower:
                pubchem_cid = self._to_int(identifier)
            elif resource_lower == "kegg drug" or resource_lower == "kegg":
                kegg_id = identifier
            elif "chebi" in resource_lower:
                chebi_id = identifier
            elif resource_lower == "pdb":
                pdb_ids.append(identifier)

        # ADMET properties
        admet = self._extract_admet_api(raw)

        # Drug interactions
        drug_interactions = []
        for inter in raw.get("drug_interactions", []):
            drug_interactions.append(DrugInteraction(
                drugbank_id=inter.get("drugbank_id", ""),
                drug_name=inter.get("name"),
                description=inter.get("description"),
            ))

        # Properties
        props = raw.get("calculated_properties", {}) or {}
        exp_props = raw.get("experimental_properties", {}) or {}

        return DrugBankDrug(
            drugbank_id=raw.get("drugbank_id", "") or raw.get("primary_id", ""),
            secondary_ids=raw.get("secondary_ids", []),
            drug_type=drug_type,
            groups=groups,
            is_approved=DrugGroup.APPROVED in groups,
            name=raw.get("name", ""),
            description=raw.get("description"),
            synonyms=synonyms,
            brands=raw.get("brands", []),
            cas_number=raw.get("cas_number"),
            unii=raw.get("unii"),
            canonical_smiles=raw.get("smiles") or props.get("SMILES"),
            inchi=raw.get("inchi") or props.get("InChI"),
            inchikey=raw.get("inchikey") or props.get("InChIKey"),
            molecular_formula=raw.get("molecular_formula") or props.get("Molecular Formula"),
            molecular_weight=self._to_decimal(raw.get("molecular_weight") or props.get("Molecular Weight")),
            average_mass=self._to_decimal(raw.get("average_mass")),
            monoisotopic_mass=self._to_decimal(raw.get("monoisotopic_mass") or props.get("Monoisotopic Weight")),
            state=raw.get("state"),
            logp=self._to_decimal(props.get("logP") or exp_props.get("logP")),
            psa=self._to_decimal(props.get("Polar Surface Area (PSA)")),
            hbd=self._to_int(props.get("H Bond Donor Count")),
            hba=self._to_int(props.get("H Bond Acceptor Count")),
            rotatable_bonds=self._to_int(props.get("Rotatable Bond Count")),
            categories=categories,
            atc_codes=raw.get("atc_codes", []),
            indication=raw.get("indication"),
            pharmacodynamics=raw.get("pharmacodynamics"),
            mechanism_of_action=raw.get("mechanism_of_action"),
            admet=admet,
            external_ids=ext_ids,
            chembl_id=chembl_id,
            pubchem_cid=pubchem_cid,
            kegg_id=kegg_id,
            chebi_id=chebi_id,
            pdb_ids=pdb_ids,
            drug_interactions=drug_interactions,
            food_interactions=raw.get("food_interactions", []),
            target_count=len(raw.get("targets", [])),
            enzyme_count=len(raw.get("enzymes", [])),
            carrier_count=len(raw.get("carriers", [])),
            transporter_count=len(raw.get("transporters", [])),
        )

    def _normalize_drug_local(self, raw: dict) -> DrugBankDrug:
        """Normalize drug from local XML/CSV data."""
        # Drug type
        drug_type_str = raw.get("drug_type", "").lower()
        drug_type = self.DRUG_TYPE_MAP.get(drug_type_str, DrugType.UNKNOWN)

        # Groups
        groups = []
        for g in raw.get("groups", []):
            group_str = g.lower() if isinstance(g, str) else ""
            if group_str in self.GROUP_MAP:
                groups.append(self.GROUP_MAP[group_str])

        # Synonyms (simpler format from local)
        synonyms = [DrugSynonym(name=s) for s in raw.get("synonyms", [])]

        # Categories
        categories = []
        for cat in raw.get("categories", []):
            if isinstance(cat, dict):
                categories.append(DrugCategory(
                    category=cat.get("category", ""),
                    mesh_id=cat.get("mesh_id"),
                ))

        # External identifiers
        ext_ids = []
        chembl_id = None
        pubchem_cid = None
        kegg_id = None
        chebi_id = None
        pdb_ids = []

        for ext in raw.get("external_ids", []):
            resource = ext.get("resource", "")
            identifier = ext.get("identifier", "")
            ext_ids.append(ExternalIdentifier(resource=resource, identifier=identifier))

            resource_lower = resource.lower()
            if "chembl" in resource_lower:
                chembl_id = identifier
            elif "pubchem" in resource_lower:
                pubchem_cid = self._to_int(identifier)
            elif "kegg" in resource_lower:
                kegg_id = identifier
            elif "chebi" in resource_lower:
                chebi_id = identifier
            elif resource_lower == "pdb":
                pdb_ids.append(identifier)

        # ADMET from local data
        admet = self._extract_admet_local(raw)

        # Drug interactions
        drug_interactions = []
        for inter in raw.get("drug_interactions", []):
            drug_interactions.append(DrugInteraction(
                drugbank_id=inter.get("drugbank_id", ""),
                drug_name=inter.get("name"),
                description=inter.get("description"),
            ))

        # Calculated properties (prefixed with calc_ in local format)
        smiles = raw.get("smiles") or raw.get("calc_smiles")
        inchi = raw.get("inchi") or raw.get("calc_inchi")
        inchikey = raw.get("inchikey") or raw.get("calc_inchikey")
        mw = raw.get("calc_molecular_weight")
        logp = raw.get("calc_logp") or raw.get("exp_logp")
        psa = raw.get("calc_polar_surface_area_(psa)")

        return DrugBankDrug(
            drugbank_id=raw.get("drugbank_id", ""),
            secondary_ids=raw.get("secondary_ids", []),
            drug_type=drug_type,
            groups=groups,
            is_approved=DrugGroup.APPROVED in groups,
            name=raw.get("name", ""),
            description=raw.get("description"),
            synonyms=synonyms,
            brands=raw.get("brands", []),
            cas_number=raw.get("cas_number"),
            unii=raw.get("unii"),
            canonical_smiles=smiles,
            inchi=inchi,
            inchikey=inchikey,
            molecular_formula=raw.get("calc_molecular_formula"),
            molecular_weight=self._to_decimal(mw),
            state=raw.get("state"),
            logp=self._to_decimal(logp),
            psa=self._to_decimal(psa),
            hbd=self._to_int(raw.get("calc_h_bond_donor_count")),
            hba=self._to_int(raw.get("calc_h_bond_acceptor_count")),
            rotatable_bonds=self._to_int(raw.get("calc_rotatable_bond_count")),
            categories=categories,
            atc_codes=raw.get("atc_codes", []),
            indication=raw.get("indication"),
            pharmacodynamics=raw.get("pharmacodynamics"),
            mechanism_of_action=raw.get("mechanism_of_action"),
            admet=admet,
            external_ids=ext_ids,
            chembl_id=chembl_id,
            pubchem_cid=pubchem_cid,
            kegg_id=kegg_id,
            chebi_id=chebi_id,
            pdb_ids=pdb_ids,
            drug_interactions=drug_interactions,
            food_interactions=raw.get("food_interactions", []),
            target_count=len(raw.get("targets", [])),
            enzyme_count=len(raw.get("enzymes", [])),
            carrier_count=len(raw.get("carriers", [])),
            transporter_count=len(raw.get("transporters", [])),
        )

    def normalize_drugs(self, raw_list: list[dict], source: str = "api") -> list[DrugBankDrug]:
        """Normalize a list of drugs."""
        return [self.normalize_drug(r, source=source) for r in raw_list]

    # =========================================================================
    # ADMET Normalization
    # =========================================================================

    def _extract_admet_api(self, raw: dict) -> ADMETProperties:
        """Extract ADMET properties from API response."""
        return ADMETProperties(
            absorption=raw.get("absorption"),
            bioavailability=raw.get("bioavailability"),
            distribution=raw.get("distribution"),
            volume_of_distribution=raw.get("volume_of_distribution"),
            protein_binding=raw.get("protein_binding"),
            metabolism=raw.get("metabolism"),
            route_of_elimination=raw.get("route_of_elimination"),
            half_life=raw.get("half_life"),
            clearance=raw.get("clearance"),
            excretion=raw.get("excretion"),
            toxicity=raw.get("toxicity"),
            pharmacodynamics=raw.get("pharmacodynamics"),
            mechanism_of_action=raw.get("mechanism_of_action"),
            indication=raw.get("indication"),
        )

    def _extract_admet_local(self, raw: dict) -> ADMETProperties:
        """Extract ADMET properties from local data."""
        return ADMETProperties(
            absorption=raw.get("absorption"),
            bioavailability=None,  # Not in XML
            distribution=None,
            volume_of_distribution=raw.get("volume_of_distribution"),
            protein_binding=raw.get("protein_binding"),
            metabolism=raw.get("metabolism"),
            route_of_elimination=raw.get("route_of_elimination"),
            half_life=raw.get("half_life"),
            clearance=raw.get("clearance"),
            excretion=None,
            toxicity=raw.get("toxicity"),
            pharmacodynamics=raw.get("pharmacodynamics"),
            mechanism_of_action=raw.get("mechanism_of_action"),
            indication=raw.get("indication"),
        )

    def normalize_admet(self, raw: dict) -> ADMETProperties:
        """Normalize ADMET properties."""
        return self._extract_admet_api(raw)

    # =========================================================================
    # DTI Normalization
    # =========================================================================

    def normalize_dti(
        self,
        raw: dict,
        drugbank_id: str,
        drug_name: str | None = None,
        source: str = "api",
    ) -> DrugTargetInteraction:
        """
        Normalize a drug-target interaction.

        Args:
            raw: Raw target/interaction data
            drugbank_id: DrugBank ID of the drug
            drug_name: Drug name
            source: Data source

        Returns:
            Normalized DrugTargetInteraction
        """
        # Target type
        target_type_str = raw.get("target_type", "target").lower()
        target_type = self.TARGET_TYPE_MAP.get(target_type_str, TargetType.TARGET)

        # Actions
        actions_raw = raw.get("actions", [])
        if isinstance(actions_raw, str):
            actions_raw = [a.strip() for a in actions_raw.split(",")]

        actions = []
        primary_action = TargetAction.UNKNOWN

        for action_str in actions_raw:
            action_lower = action_str.lower().strip()
            if action_lower in self.ACTION_MAP:
                actions.append(action_str)
                if primary_action == TargetAction.UNKNOWN:
                    primary_action = self.ACTION_MAP[action_lower]

        return DrugTargetInteraction(
            drugbank_id=drugbank_id,
            drug_name=drug_name,
            target_id=raw.get("id"),
            target_name=raw.get("name") or raw.get("target_name"),
            target_type=target_type,
            gene_name=raw.get("gene_name"),
            uniprot_id=raw.get("uniprot_id"),
            action=primary_action,
            actions=actions,
            known_action=raw.get("known_action", False),
            organism=raw.get("organism"),
            references=raw.get("references", []),
            pubmed_ids=raw.get("pubmed_ids", []),
            polypeptide_name=raw.get("polypeptide_name"),
            polypeptide_sequence=raw.get("polypeptide_sequence"),
        )

    def normalize_dtis(
        self,
        raw_list: list[dict],
        drugbank_id: str,
        drug_name: str | None = None,
        source: str = "api",
    ) -> list[DrugTargetInteraction]:
        """Normalize a list of DTIs."""
        return [
            self.normalize_dti(r, drugbank_id, drug_name, source)
            for r in raw_list
        ]

    # =========================================================================
    # Search Result Normalization
    # =========================================================================

    def normalize_search_hit(self, raw: dict) -> DrugSearchHit:
        """Normalize a search result hit."""
        groups = []
        for g in raw.get("groups", []):
            group_str = g.lower() if isinstance(g, str) else ""
            if group_str in self.GROUP_MAP:
                groups.append(self.GROUP_MAP[group_str])

        drug_type_str = raw.get("type", "").lower()
        drug_type = self.DRUG_TYPE_MAP.get(drug_type_str, DrugType.UNKNOWN)

        return DrugSearchHit(
            drugbank_id=raw.get("drugbank_id", "") or raw.get("primary_id", ""),
            name=raw.get("name", ""),
            drug_type=drug_type,
            groups=groups,
            cas_number=raw.get("cas_number"),
            molecular_weight=self._to_decimal(raw.get("molecular_weight")),
        )

    def normalize_search_hits(self, raw_list: list[dict]) -> list[DrugSearchHit]:
        """Normalize search result hits."""
        return [self.normalize_search_hit(r) for r in raw_list]

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
            return int(float(value))
        except (ValueError, TypeError):
            return None
