"""
DrugBank local data reader for XML/CSV datasets.

Provides offline access to DrugBank data when API credentials are not available.
Supports the free academic dataset available from https://go.drugbank.com/releases

Supported formats:
- Full XML database (drugbank_all_full_database.xml)
- Structures CSV (drugbank_all_structures.csv)
- Drug-target interactions CSV (drugbank_all_drug-target-identifiers.csv)

Usage:
    reader = DrugBankLocalReader("/path/to/drugbank/data")

    # Check if data is available
    if reader.is_available:
        drug = await reader.get_drug("DB00945")
        targets = await reader.get_drug_targets("DB00945")
"""

import csv
import logging
import os
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class LocalDataNotFoundError(Exception):
    """Local DrugBank data not found or not configured."""

    def __init__(self, path: str | None = None):
        message = "DrugBank local data not found"
        if path:
            message += f" at: {path}"
        message += ". Download from https://go.drugbank.com/releases"
        super().__init__(message)
        self.path = path


class DrugBankLocalReader:
    """
    Reader for local DrugBank XML/CSV datasets.

    The DrugBank academic dataset includes:
    - drugbank_all_full_database.xml - Complete drug database
    - drugbank_all_structures.csv - Chemical structures
    - drugbank_all_drug-target-identifiers.csv - DTI data

    Example:
        reader = DrugBankLocalReader("/data/drugbank")

        # Load index (required before queries)
        await reader.load_index()

        # Query drugs
        drug = await reader.get_drug("DB00945")
        targets = await reader.get_drug_targets("DB00945")

        # Search
        results = await reader.search_drugs("aspirin")
    """

    # Expected filenames in the data directory
    XML_DATABASE = "drugbank_all_full_database.xml"
    STRUCTURES_CSV = "drugbank_all_structures.csv"
    DTI_CSV = "drugbank_all_drug-target-identifiers.csv"
    VOCAB_CSV = "drugbank_vocabulary.csv"

    # DrugBank XML namespace
    NS = {"db": "http://www.drugbank.ca"}

    def __init__(self, data_path: str | None = None):
        """
        Initialize local reader.

        Args:
            data_path: Path to directory containing DrugBank files
        """
        self.data_path = Path(data_path) if data_path else None

        # In-memory indices (loaded on demand)
        self._drug_index: dict[str, dict] = {}  # drugbank_id -> basic info
        self._name_index: dict[str, list[str]] = {}  # name -> drugbank_ids
        self._dti_index: dict[str, list[dict]] = {}  # drugbank_id -> targets
        self._structure_index: dict[str, dict] = {}  # drugbank_id -> structure

        self._index_loaded = False
        self._xml_tree: ET.ElementTree | None = None

    @property
    def is_available(self) -> bool:
        """Check if local data is available."""
        if not self.data_path:
            return False
        if not self.data_path.exists():
            return False

        # Check for at least XML or CSV files
        xml_path = self.data_path / self.XML_DATABASE
        csv_path = self.data_path / self.STRUCTURES_CSV

        return xml_path.exists() or csv_path.exists()

    @property
    def has_xml(self) -> bool:
        """Check if full XML database is available."""
        if not self.data_path:
            return False
        return (self.data_path / self.XML_DATABASE).exists()

    @property
    def has_structures_csv(self) -> bool:
        """Check if structures CSV is available."""
        if not self.data_path:
            return False
        return (self.data_path / self.STRUCTURES_CSV).exists()

    @property
    def has_dti_csv(self) -> bool:
        """Check if DTI CSV is available."""
        if not self.data_path:
            return False
        return (self.data_path / self.DTI_CSV).exists()

    def get_status(self) -> dict:
        """Get status of local data availability."""
        return {
            "is_available": self.is_available,
            "data_path": str(self.data_path) if self.data_path else None,
            "has_xml_database": self.has_xml,
            "has_structures_csv": self.has_structures_csv,
            "has_dti_csv": self.has_dti_csv,
            "index_loaded": self._index_loaded,
            "drug_count": len(self._drug_index) if self._index_loaded else None,
        }

    # =========================================================================
    # Index Loading
    # =========================================================================

    async def load_index(self, force: bool = False) -> None:
        """
        Load index from local files.

        This loads basic drug info into memory for fast lookups.
        Full drug data is loaded on-demand from XML.

        Args:
            force: Force reload even if already loaded
        """
        if self._index_loaded and not force:
            return

        if not self.is_available:
            raise LocalDataNotFoundError(str(self.data_path))

        logger.info(f"Loading DrugBank index from {self.data_path}")

        # Load from CSV first (faster)
        if self.has_structures_csv:
            await self._load_structures_csv()

        # Load DTI data
        if self.has_dti_csv:
            await self._load_dti_csv()

        # If no CSV, build index from XML (slower)
        if not self._drug_index and self.has_xml:
            await self._load_xml_index()

        self._index_loaded = True
        logger.info(f"DrugBank index loaded: {len(self._drug_index)} drugs")

    async def _load_structures_csv(self) -> None:
        """Load drug index from structures CSV."""
        csv_path = self.data_path / self.STRUCTURES_CSV

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                drugbank_id = row.get("DrugBank ID", "").strip()
                if not drugbank_id:
                    continue

                name = row.get("Name", "").strip()
                cas = row.get("CAS", "").strip()
                smiles = row.get("SMILES", "").strip()
                inchi = row.get("InChI", "").strip()
                inchikey = row.get("InChIKey", "").strip()

                self._drug_index[drugbank_id] = {
                    "drugbank_id": drugbank_id,
                    "name": name,
                    "cas_number": cas if cas else None,
                    "smiles": smiles if smiles else None,
                    "inchi": inchi if inchi else None,
                    "inchikey": inchikey if inchikey else None,
                }

                # Build name index
                if name:
                    name_lower = name.lower()
                    if name_lower not in self._name_index:
                        self._name_index[name_lower] = []
                    self._name_index[name_lower].append(drugbank_id)

                self._structure_index[drugbank_id] = {
                    "smiles": smiles if smiles else None,
                    "inchi": inchi if inchi else None,
                    "inchikey": inchikey if inchikey else None,
                }

    async def _load_dti_csv(self) -> None:
        """Load drug-target interactions from CSV."""
        csv_path = self.data_path / self.DTI_CSV

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                drugbank_id = row.get("Drug ID", "").strip()
                if not drugbank_id:
                    continue

                target_info = {
                    "target_name": row.get("Name", "").strip(),
                    "gene_name": row.get("Gene Name", "").strip() or None,
                    "uniprot_id": row.get("UniProt ID", "").strip() or None,
                    "target_type": row.get("Target Type", "target").lower(),
                    "actions": row.get("Actions", "").strip() or None,
                    "organism": row.get("Species", "").strip() or None,
                }

                if drugbank_id not in self._dti_index:
                    self._dti_index[drugbank_id] = []
                self._dti_index[drugbank_id].append(target_info)

    async def _load_xml_index(self) -> None:
        """Build index from XML database (slower but complete)."""
        xml_path = self.data_path / self.XML_DATABASE

        # Use iterparse to avoid loading entire XML into memory
        for event, elem in ET.iterparse(xml_path, events=["end"]):
            if elem.tag == f"{{{self.NS['db']}}}drug":
                drugbank_id = elem.find("db:drugbank-id[@primary='true']", self.NS)
                name = elem.find("db:name", self.NS)

                if drugbank_id is not None and drugbank_id.text:
                    db_id = drugbank_id.text.strip()
                    drug_name = name.text.strip() if name is not None and name.text else ""

                    self._drug_index[db_id] = {
                        "drugbank_id": db_id,
                        "name": drug_name,
                    }

                    if drug_name:
                        name_lower = drug_name.lower()
                        if name_lower not in self._name_index:
                            self._name_index[name_lower] = []
                        self._name_index[name_lower].append(db_id)

                # Clear element to save memory
                elem.clear()

    # =========================================================================
    # Data Retrieval
    # =========================================================================

    async def get_drug(self, drugbank_id: str) -> dict | None:
        """
        Get drug data by DrugBank ID.

        Args:
            drugbank_id: DrugBank ID (e.g., DB00945)

        Returns:
            Drug data dict or None if not found
        """
        if not self._index_loaded:
            await self.load_index()

        # Get basic info from index
        basic_info = self._drug_index.get(drugbank_id)
        if not basic_info:
            return None

        # If we have XML, get full data
        if self.has_xml:
            full_data = await self._get_drug_from_xml(drugbank_id)
            if full_data:
                return full_data

        # Return basic info from CSV
        result = dict(basic_info)

        # Add structure info
        if drugbank_id in self._structure_index:
            result.update(self._structure_index[drugbank_id])

        return result

    async def _get_drug_from_xml(self, drugbank_id: str) -> dict | None:
        """Parse full drug data from XML."""
        xml_path = self.data_path / self.XML_DATABASE

        # Search for the specific drug in XML
        for event, elem in ET.iterparse(xml_path, events=["end"]):
            if elem.tag == f"{{{self.NS['db']}}}drug":
                primary_id = elem.find("db:drugbank-id[@primary='true']", self.NS)
                if primary_id is not None and primary_id.text == drugbank_id:
                    result = self._parse_drug_element(elem)
                    elem.clear()
                    return result
                elem.clear()

        return None

    def _parse_drug_element(self, elem: ET.Element) -> dict:
        """Parse a drug XML element into a dict."""
        ns = self.NS

        def get_text(path: str) -> str | None:
            el = elem.find(path, ns)
            return el.text.strip() if el is not None and el.text else None

        def get_all_text(path: str) -> list[str]:
            elements = elem.findall(path, ns)
            return [e.text.strip() for e in elements if e.text]

        # Basic info
        result = {
            "drugbank_id": get_text("db:drugbank-id[@primary='true']"),
            "name": get_text("db:name"),
            "description": get_text("db:description"),
            "cas_number": get_text("db:cas-number"),
            "unii": get_text("db:unii"),
            "state": get_text("db:state"),
            "indication": get_text("db:indication"),
            "pharmacodynamics": get_text("db:pharmacodynamics"),
            "mechanism_of_action": get_text("db:mechanism-of-action"),
            "toxicity": get_text("db:toxicity"),
            "metabolism": get_text("db:metabolism"),
            "absorption": get_text("db:absorption"),
            "half_life": get_text("db:half-life"),
            "protein_binding": get_text("db:protein-binding"),
            "route_of_elimination": get_text("db:route-of-elimination"),
            "volume_of_distribution": get_text("db:volume-of-distribution"),
            "clearance": get_text("db:clearance"),
        }

        # Drug type
        drug_type = elem.get("type")
        result["drug_type"] = drug_type if drug_type else "unknown"

        # Groups (approved, experimental, etc.)
        groups = get_all_text("db:groups/db:group")
        result["groups"] = groups

        # Secondary IDs
        secondary_ids = get_all_text("db:drugbank-id[not(@primary)]")
        result["secondary_ids"] = secondary_ids

        # Synonyms
        synonyms = get_all_text("db:synonyms/db:synonym")
        result["synonyms"] = synonyms

        # Brands
        brands = get_all_text("db:international-brands/db:international-brand/db:name")
        result["brands"] = brands

        # Calculated properties
        calc_props = elem.find("db:calculated-properties", ns)
        if calc_props is not None:
            for prop in calc_props.findall("db:property", ns):
                kind = prop.find("db:kind", ns)
                value = prop.find("db:value", ns)
                if kind is not None and value is not None and kind.text and value.text:
                    prop_name = kind.text.strip().lower().replace(" ", "_")
                    result[f"calc_{prop_name}"] = value.text.strip()

        # Experimental properties
        exp_props = elem.find("db:experimental-properties", ns)
        if exp_props is not None:
            for prop in exp_props.findall("db:property", ns):
                kind = prop.find("db:kind", ns)
                value = prop.find("db:value", ns)
                if kind is not None and value is not None and kind.text and value.text:
                    prop_name = kind.text.strip().lower().replace(" ", "_")
                    result[f"exp_{prop_name}"] = value.text.strip()

        # External identifiers
        ext_ids = []
        for ext_id in elem.findall("db:external-identifiers/db:external-identifier", ns):
            resource = ext_id.find("db:resource", ns)
            identifier = ext_id.find("db:identifier", ns)
            if resource is not None and identifier is not None:
                ext_ids.append({
                    "resource": resource.text.strip() if resource.text else "",
                    "identifier": identifier.text.strip() if identifier.text else "",
                })
        result["external_ids"] = ext_ids

        # Categories (ATC codes, etc.)
        categories = []
        for cat in elem.findall("db:categories/db:category", ns):
            category = cat.find("db:category", ns)
            mesh_id = cat.find("db:mesh-id", ns)
            if category is not None and category.text:
                categories.append({
                    "category": category.text.strip(),
                    "mesh_id": mesh_id.text.strip() if mesh_id is not None and mesh_id.text else None,
                })
        result["categories"] = categories

        # ATC codes
        atc_codes = get_all_text("db:atc-codes/db:atc-code/@code")
        result["atc_codes"] = atc_codes

        # Targets
        targets = self._parse_targets(elem, "db:targets/db:target", "target")
        enzymes = self._parse_targets(elem, "db:enzymes/db:enzyme", "enzyme")
        carriers = self._parse_targets(elem, "db:carriers/db:carrier", "carrier")
        transporters = self._parse_targets(elem, "db:transporters/db:transporter", "transporter")

        result["targets"] = targets
        result["enzymes"] = enzymes
        result["carriers"] = carriers
        result["transporters"] = transporters

        # Drug interactions
        interactions = []
        for interaction in elem.findall("db:drug-interactions/db:drug-interaction", ns):
            db_id = interaction.find("db:drugbank-id", ns)
            name = interaction.find("db:name", ns)
            desc = interaction.find("db:description", ns)
            if db_id is not None and db_id.text:
                interactions.append({
                    "drugbank_id": db_id.text.strip(),
                    "name": name.text.strip() if name is not None and name.text else None,
                    "description": desc.text.strip() if desc is not None and desc.text else None,
                })
        result["drug_interactions"] = interactions

        # Food interactions
        food_interactions = get_all_text("db:food-interactions/db:food-interaction")
        result["food_interactions"] = food_interactions

        return result

    def _parse_targets(self, elem: ET.Element, path: str, target_type: str) -> list[dict]:
        """Parse target elements (targets, enzymes, carriers, transporters)."""
        ns = self.NS
        targets = []

        for target in elem.findall(path, ns):
            target_data = {
                "target_type": target_type,
                "id": None,
                "name": None,
                "gene_name": None,
                "organism": None,
                "actions": [],
                "known_action": False,
                "uniprot_id": None,
                "polypeptide_name": None,
                "polypeptide_sequence": None,
            }

            # Basic info
            target_id = target.find("db:id", ns)
            name = target.find("db:name", ns)
            organism = target.find("db:organism", ns)
            known_action = target.find("db:known-action", ns)

            target_data["id"] = target_id.text.strip() if target_id is not None and target_id.text else None
            target_data["name"] = name.text.strip() if name is not None and name.text else None
            target_data["organism"] = organism.text.strip() if organism is not None and organism.text else None
            target_data["known_action"] = known_action is not None and known_action.text == "yes"

            # Actions
            for action in target.findall("db:actions/db:action", ns):
                if action.text:
                    target_data["actions"].append(action.text.strip())

            # Polypeptide info
            polypeptide = target.find("db:polypeptide", ns)
            if polypeptide is not None:
                pp_name = polypeptide.find("db:name", ns)
                pp_gene = polypeptide.find("db:gene-name", ns)
                pp_seq = polypeptide.find("db:amino-acid-sequence", ns)

                target_data["polypeptide_name"] = pp_name.text.strip() if pp_name is not None and pp_name.text else None
                target_data["gene_name"] = pp_gene.text.strip() if pp_gene is not None and pp_gene.text else None
                target_data["polypeptide_sequence"] = pp_seq.text.strip() if pp_seq is not None and pp_seq.text else None

                # UniProt ID from external identifiers
                for ext_id in polypeptide.findall("db:external-identifiers/db:external-identifier", ns):
                    resource = ext_id.find("db:resource", ns)
                    identifier = ext_id.find("db:identifier", ns)
                    if resource is not None and resource.text == "UniProtKB" and identifier is not None:
                        target_data["uniprot_id"] = identifier.text.strip() if identifier.text else None
                        break

            targets.append(target_data)

        return targets

    async def get_drug_targets(self, drugbank_id: str) -> list[dict]:
        """
        Get targets for a drug.

        Args:
            drugbank_id: DrugBank ID

        Returns:
            List of target records
        """
        if not self._index_loaded:
            await self.load_index()

        # Try from DTI index first (from CSV)
        if drugbank_id in self._dti_index:
            return self._dti_index[drugbank_id]

        # Try from XML
        if self.has_xml:
            drug = await self._get_drug_from_xml(drugbank_id)
            if drug:
                targets = drug.get("targets", [])
                targets.extend(drug.get("enzymes", []))
                targets.extend(drug.get("carriers", []))
                targets.extend(drug.get("transporters", []))
                return targets

        return []

    async def search_drugs(
        self,
        query: str,
        limit: int = 25,
    ) -> list[dict]:
        """
        Search drugs by name.

        Args:
            query: Search query (drug name)
            limit: Maximum results

        Returns:
            List of matching drug records
        """
        if not self._index_loaded:
            await self.load_index()

        query_lower = query.lower()
        results = []

        # Exact match first
        if query_lower in self._name_index:
            for db_id in self._name_index[query_lower]:
                if db_id in self._drug_index:
                    results.append(self._drug_index[db_id])

        # Partial match
        for name, db_ids in self._name_index.items():
            if query_lower in name and name != query_lower:
                for db_id in db_ids:
                    if db_id in self._drug_index and self._drug_index[db_id] not in results:
                        results.append(self._drug_index[db_id])
                        if len(results) >= limit:
                            break
            if len(results) >= limit:
                break

        return results[:limit]

    async def iter_drugs(self, batch_size: int = 100) -> Iterator[dict]:
        """
        Iterate over all drugs.

        Args:
            batch_size: Not used, yields one at a time

        Yields:
            Drug data dicts
        """
        if not self._index_loaded:
            await self.load_index()

        for drugbank_id in self._drug_index:
            drug = await self.get_drug(drugbank_id)
            if drug:
                yield drug

    # =========================================================================
    # Cleanup
    # =========================================================================

    def clear_cache(self) -> None:
        """Clear in-memory index."""
        self._drug_index.clear()
        self._name_index.clear()
        self._dti_index.clear()
        self._structure_index.clear()
        self._index_loaded = False
        self._xml_tree = None
