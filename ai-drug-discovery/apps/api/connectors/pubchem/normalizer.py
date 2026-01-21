"""
PubChem data normalizer.

Transforms raw PubChem API responses into normalized schemas.
This layer is separate from HTTP fetching for:
- Testability (mock raw data, test normalization)
- Reusability (normalize data from files, other sources)
- Maintainability (API changes only affect this layer)
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.api.connectors.pubchem.schemas import (
    AssayOutcome,
    AssayType,
    CompoundProperties,
    PubChemAssay,
    PubChemBioactivity,
    PubChemCompound,
)

logger = logging.getLogger(__name__)


class PubChemNormalizer:
    """
    Normalizes raw PubChem API responses to typed schemas.

    Usage:
        normalizer = PubChemNormalizer()

        # Normalize compound from properties endpoint
        raw_props = {"CID": 2244, "MolecularWeight": 180.16, ...}
        compound = normalizer.normalize_compound_from_properties(raw_props)

        # Normalize from full compound record
        raw_compound = {"id": {"id": {"cid": 2244}}, ...}
        compound = normalizer.normalize_compound_from_record(raw_compound)
    """

    # =========================================================================
    # Outcome Mappings
    # =========================================================================

    OUTCOME_MAP = {
        1: AssayOutcome.INACTIVE,
        2: AssayOutcome.ACTIVE,
        3: AssayOutcome.INCONCLUSIVE,
        4: AssayOutcome.UNSPECIFIED,
        5: AssayOutcome.PROBE,
    }

    ASSAY_TYPE_MAP = {
        "screening": AssayType.SCREENING,
        "confirmatory": AssayType.CONFIRMATORY,
        "summary": AssayType.SUMMARY,
    }

    # =========================================================================
    # Compound Normalization
    # =========================================================================

    def normalize_compound_from_properties(
        self,
        raw: dict,
        synonyms: list[str] | None = None,
    ) -> PubChemCompound:
        """
        Normalize compound from PUG REST property endpoint.

        Args:
            raw: Raw property data from /compound/cid/X/property/...
            synonyms: Optional list of synonyms

        Returns:
            Normalized PubChemCompound
        """
        return PubChemCompound(
            cid=raw.get("CID", 0),
            # Structure
            canonical_smiles=raw.get("CanonicalSMILES"),
            isomeric_smiles=raw.get("IsomericSMILES"),
            inchi=raw.get("InChI"),
            inchikey=raw.get("InChIKey"),
            # Names
            iupac_name=raw.get("IUPACName"),
            title=raw.get("Title"),
            synonyms=synonyms or [],
            # Properties
            molecular_formula=raw.get("MolecularFormula"),
            molecular_weight=self._to_decimal(raw.get("MolecularWeight")),
            exact_mass=self._to_decimal(
                raw.get("ExactMass") or raw.get("MonoisotopicMass")
            ),
            xlogp=self._to_decimal(raw.get("XLogP")),
            tpsa=self._to_decimal(raw.get("TPSA")),
            complexity=self._to_decimal(raw.get("Complexity")),
            # Counts
            heavy_atom_count=self._to_int(raw.get("HeavyAtomCount")),
            atom_stereo_count=self._to_int(raw.get("AtomStereoCount")),
            defined_atom_stereo_count=self._to_int(raw.get("DefinedAtomStereoCount")),
            undefined_atom_stereo_count=self._to_int(
                raw.get("UndefinedAtomStereoCount")
            ),
            bond_stereo_count=self._to_int(raw.get("BondStereoCount")),
            covalent_unit_count=self._to_int(raw.get("CovalentUnitCount")),
            hbond_acceptor_count=self._to_int(raw.get("HBondAcceptorCount")),
            hbond_donor_count=self._to_int(raw.get("HBondDonorCount")),
            rotatable_bond_count=self._to_int(raw.get("RotatableBondCount")),
            # Charge
            charge=self._to_int(raw.get("Charge")),
        )

    def normalize_compound_from_record(
        self,
        raw: dict,
        synonyms: list[str] | None = None,
    ) -> PubChemCompound:
        """
        Normalize compound from full PUG REST compound record.

        Args:
            raw: Raw compound data from /compound/cid/X/JSON
            synonyms: Optional list of synonyms

        Returns:
            Normalized PubChemCompound
        """
        # Extract CID
        cid = 0
        id_section = raw.get("id", {}).get("id", {})
        if isinstance(id_section, dict):
            cid = id_section.get("cid", 0)

        # Extract properties from the props array
        props = self._extract_props(raw.get("props", []))
        atoms = raw.get("atoms", {})
        bonds = raw.get("bonds", {})

        # Count heavy atoms (non-hydrogen)
        heavy_atom_count = None
        if "element" in atoms:
            heavy_atom_count = sum(1 for e in atoms["element"] if e != 1)

        return PubChemCompound(
            cid=cid,
            # Structure (from props)
            canonical_smiles=props.get("SMILES", {}).get("Canonical"),
            isomeric_smiles=props.get("SMILES", {}).get("Isomeric"),
            inchi=props.get("InChI", {}).get("Standard"),
            inchikey=props.get("InChIKey", {}).get("Standard"),
            # Names
            iupac_name=props.get("IUPAC Name", {}).get("Preferred")
            or props.get("IUPAC Name", {}).get("Systematic"),
            synonyms=synonyms or [],
            # Properties
            molecular_formula=props.get("Molecular Formula"),
            molecular_weight=self._to_decimal(props.get("Molecular Weight")),
            exact_mass=self._to_decimal(props.get("Exact Mass")),
            xlogp=self._to_decimal(props.get("Log P", {}).get("XLogP3")),
            tpsa=self._to_decimal(props.get("Topological Polar Surface Area")),
            complexity=self._to_decimal(props.get("Complexity")),
            # Counts
            heavy_atom_count=heavy_atom_count,
            hbond_acceptor_count=self._to_int(props.get("Hydrogen Bond Acceptor")),
            hbond_donor_count=self._to_int(props.get("Hydrogen Bond Donor")),
            rotatable_bond_count=self._to_int(props.get("Rotatable Bond")),
            # Charge
            charge=self._to_int(props.get("Charge")),
        )

    def normalize_properties(self, raw: dict) -> CompoundProperties:
        """
        Normalize to CompoundProperties (subset focused on physicochemical).

        Args:
            raw: Raw property data

        Returns:
            CompoundProperties object
        """
        mw = self._to_decimal(raw.get("MolecularWeight"))
        hba = self._to_int(raw.get("HBondAcceptorCount"))
        hbd = self._to_int(raw.get("HBondDonorCount"))
        xlogp = self._to_decimal(raw.get("XLogP"))

        # Compute Lipinski RO5 violations
        ro5_violations = self._compute_ro5_violations(mw, hba, hbd, xlogp)

        return CompoundProperties(
            cid=raw.get("CID", 0),
            molecular_weight=mw,
            exact_mass=self._to_decimal(
                raw.get("ExactMass") or raw.get("MonoisotopicMass")
            ),
            xlogp=xlogp,
            tpsa=self._to_decimal(raw.get("TPSA")),
            complexity=self._to_decimal(raw.get("Complexity")),
            heavy_atom_count=self._to_int(raw.get("HeavyAtomCount")),
            hbond_acceptor_count=hba,
            hbond_donor_count=hbd,
            rotatable_bond_count=self._to_int(raw.get("RotatableBondCount")),
            charge=self._to_int(raw.get("Charge")),
            ro5_violations=ro5_violations,
        )

    def normalize_compounds(
        self,
        raw_list: list[dict],
        synonyms_map: dict[int, list[str]] | None = None,
    ) -> list[PubChemCompound]:
        """Normalize a list of compounds from properties endpoint."""
        synonyms_map = synonyms_map or {}
        return [
            self.normalize_compound_from_properties(
                r, synonyms=synonyms_map.get(r.get("CID"))
            )
            for r in raw_list
        ]

    # =========================================================================
    # Assay Normalization
    # =========================================================================

    def normalize_assay(self, raw: dict) -> PubChemAssay:
        """
        Normalize assay from PUG REST assay description endpoint.

        Args:
            raw: Raw assay data from /assay/aid/X/description/JSON

        Returns:
            Normalized PubChemAssay
        """
        assay = raw.get("assay", {})
        descr = assay.get("descr", {})

        # Get AID
        aid = descr.get("aid", {}).get("id", 0)

        # Get assay type
        assay_type_str = descr.get("activity_outcome_method", "").lower()
        assay_type = self.ASSAY_TYPE_MAP.get(assay_type_str, AssayType.OTHER)

        # Extract target info
        target_name = None
        target_gi = None
        target_gene_id = None
        target_gene_symbol = None

        targets = descr.get("target", [])
        if targets:
            target = targets[0]
            target_name = target.get("name")
            target_gi = self._to_int(target.get("mol_id"))
            target_gene_id = self._to_int(target.get("gene_id"))

        # Get description text
        description_list = descr.get("description", [])
        description = "\n".join(description_list) if description_list else None

        # Get protocol
        protocol_list = descr.get("protocol", [])
        protocol = "\n".join(protocol_list) if protocol_list else None

        # Get source
        source = descr.get("aid_source", {}).get("db", {})
        source_name = source.get("source_id", {}).get("str")
        source_id = source.get("aid", {}).get("id")

        return PubChemAssay(
            aid=aid,
            name=descr.get("name"),
            description=description,
            assay_type=assay_type,
            protocol=protocol,
            target_name=target_name,
            target_gi=target_gi,
            target_gene_id=target_gene_id,
            target_gene_symbol=target_gene_symbol,
            source_name=source_name,
            source_id=str(source_id) if source_id else None,
            activity_outcome_method=descr.get("activity_outcome_method"),
            comment=descr.get("comment"),
        )

    def normalize_assay_from_summary(self, row: dict, columns: list[str]) -> dict:
        """
        Normalize assay summary row to a simple dict.

        Args:
            row: Row from assay summary
            columns: Column names

        Returns:
            Dict with column-value pairs
        """
        cells = row.get("Cell", [])
        result = {}
        for i, col in enumerate(columns):
            if i < len(cells):
                cell = cells[i]
                # Cell can have different value types
                for val_type in ["NumValue", "StringValue", "BoolValue"]:
                    if val_type in cell:
                        result[col] = cell[val_type]
                        break
        return result

    # =========================================================================
    # Bioactivity Normalization
    # =========================================================================

    def normalize_bioactivity(
        self,
        raw: dict,
        aid: int,
    ) -> PubChemBioactivity:
        """
        Normalize bioactivity from assay data.

        Args:
            raw: Raw activity data
            aid: Assay ID

        Returns:
            Normalized PubChemBioactivity
        """
        # Extract outcome
        outcome_int = raw.get("outcome", 4)
        outcome = self.OUTCOME_MAP.get(outcome_int, AssayOutcome.UNSPECIFIED)

        # Extract primary activity value
        activity_value = None
        activity_name = None
        activity_unit = None
        additional_data = {}

        data_list = raw.get("data", [])
        for item in data_list:
            tid = item.get("tid")
            value = item.get("value", {})

            # Get the actual value
            val = None
            for val_type in ["fval", "ival", "sval", "bval"]:
                if val_type in value:
                    val = value[val_type]
                    break

            if tid == 1 and val is not None:
                # TID 1 is typically the primary result
                activity_value = self._to_decimal(val)
            elif val is not None:
                additional_data[f"tid_{tid}"] = val

        return PubChemBioactivity(
            sid=raw.get("sid"),
            cid=raw.get("cid", 0),
            aid=aid,
            outcome=outcome,
            activity_value=activity_value,
            activity_name=activity_name,
            activity_unit=activity_unit,
            data=additional_data if additional_data else None,
            comment=raw.get("comment"),
        )

    def normalize_bioactivities_from_summary(
        self,
        rows: list[dict],
        columns: list[str],
        cid: int,
    ) -> list[PubChemBioactivity]:
        """
        Normalize bioactivities from assay summary table.

        Args:
            rows: Rows from assay summary
            columns: Column names
            cid: Compound ID

        Returns:
            List of PubChemBioactivity objects
        """
        activities = []

        for row in rows:
            data = self.normalize_assay_from_summary(row, columns)

            # Map common columns
            aid = self._to_int(data.get("AID"))
            if not aid:
                continue

            outcome_str = data.get("Bioactivity Outcome", "Unspecified")
            outcome = AssayOutcome.UNSPECIFIED
            for member in AssayOutcome:
                if member.value.lower() == outcome_str.lower():
                    outcome = member
                    break

            activity = PubChemBioactivity(
                cid=cid,
                aid=aid,
                outcome=outcome,
                activity_value=self._to_decimal(data.get("Activity Value")),
                activity_name=data.get("Activity Name"),
                activity_unit=data.get("Activity Unit"),
                data={k: v for k, v in data.items() if k not in ["AID", "CID"]},
            )
            activities.append(activity)

        return activities

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

    def _extract_props(self, props_list: list[dict]) -> dict:
        """
        Extract properties from PubChem props array.

        PubChem uses a complex nested structure for properties.
        """
        result: dict = {}

        for prop in props_list:
            urn = prop.get("urn", {})
            label = urn.get("label")
            name = urn.get("name")
            value_dict = prop.get("value", {})

            # Get the actual value
            value = None
            for val_type in ["sval", "fval", "ival", "binary"]:
                if val_type in value_dict:
                    value = value_dict[val_type]
                    break

            if label:
                if name:
                    if label not in result:
                        result[label] = {}
                    if isinstance(result[label], dict):
                        result[label][name] = value
                else:
                    result[label] = value

        return result

    def _compute_ro5_violations(
        self,
        mw: Decimal | None,
        hba: int | None,
        hbd: int | None,
        logp: Decimal | None,
    ) -> int | None:
        """Compute Lipinski Rule of 5 violations."""
        if all(v is None for v in [mw, hba, hbd, logp]):
            return None

        violations = 0
        if mw is not None and mw > 500:
            violations += 1
        if hba is not None and hba > 10:
            violations += 1
        if hbd is not None and hbd > 5:
            violations += 1
        if logp is not None and logp > 5:
            violations += 1

        return violations
