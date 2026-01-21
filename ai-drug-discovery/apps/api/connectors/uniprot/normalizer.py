"""
UniProt data normalizer.

Transforms raw UniProt API responses into normalized schemas.
This layer is separate from HTTP fetching for:
- Testability (mock raw data, test normalization)
- Reusability (normalize data from files, other sources)
- Maintainability (API changes only affect this layer)
"""

import logging
import re
from datetime import datetime
from typing import Any

from apps.api.connectors.uniprot.schemas import (
    CrossReference,
    DiseaseAssociation,
    DrugInteraction,
    FeatureType,
    FunctionAnnotation,
    GeneInfo,
    OrganismInfo,
    ProteinExistence,
    ProteinName,
    ReviewStatus,
    SequenceFeature,
    SubcellularLocation,
    TargetSearchHit,
    TargetSummary,
    UniProtTarget,
)

logger = logging.getLogger(__name__)


class UniProtNormalizer:
    """
    Normalizes raw UniProt API responses to typed schemas.

    Usage:
        normalizer = UniProtNormalizer()

        # Normalize full entry
        raw_entry = await client.get_entry("P00533")
        target = normalizer.normalize_target(raw_entry)

        # Normalize search results
        raw_results = await client.search("kinase")
        hits = normalizer.normalize_search_results(raw_results)
    """

    # =========================================================================
    # Mappings
    # =========================================================================

    PROTEIN_EXISTENCE_MAP = {
        "1: Evidence at protein level": ProteinExistence.EVIDENCE_AT_PROTEIN_LEVEL,
        "2: Evidence at transcript level": ProteinExistence.EVIDENCE_AT_TRANSCRIPT_LEVEL,
        "3: Inferred from homology": ProteinExistence.INFERRED_FROM_HOMOLOGY,
        "4: Predicted": ProteinExistence.PREDICTED,
        "5: Uncertain": ProteinExistence.UNCERTAIN,
    }

    FEATURE_TYPE_MAP = {
        "Domain": FeatureType.DOMAIN,
        "Binding site": FeatureType.BINDING_SITE,
        "Active site": FeatureType.ACTIVE_SITE,
        "Metal binding": FeatureType.METAL_BINDING,
        "Site": FeatureType.SITE,
        "Modified residue": FeatureType.MODIFIED_RESIDUE,
        "Lipidation": FeatureType.LIPIDATION,
        "Glycosylation site": FeatureType.GLYCOSYLATION,
        "Disulfide bond": FeatureType.DISULFIDE_BOND,
        "Transmembrane": FeatureType.TRANSMEMBRANE,
        "Signal peptide": FeatureType.SIGNAL,
        "Propeptide": FeatureType.PROPEPTIDE,
        "Chain": FeatureType.CHAIN,
        "Region": FeatureType.REGION,
        "Motif": FeatureType.MOTIF,
        "Compositional bias": FeatureType.COMPOSITIONAL_BIAS,
        "Coiled coil": FeatureType.COILED_COIL,
        "Helix": FeatureType.HELIX,
        "Beta strand": FeatureType.STRAND,
        "Turn": FeatureType.TURN,
    }

    # =========================================================================
    # Main Target Normalization
    # =========================================================================

    def normalize_target(self, raw: dict) -> UniProtTarget:
        """
        Normalize a UniProt entry to UniProtTarget.

        Args:
            raw: Raw entry data from UniProt API

        Returns:
            Normalized UniProtTarget
        """
        # Extract basic info
        accession = raw.get("primaryAccession", "")
        entry_name = raw.get("uniProtkbId")

        # Review status
        entry_type = raw.get("entryType", "")
        if "Swiss-Prot" in entry_type:
            review_status = ReviewStatus.REVIEWED
        else:
            review_status = ReviewStatus.UNREVIEWED

        # Protein existence
        protein_existence = None
        pe_str = raw.get("proteinExistence")
        if pe_str:
            protein_existence = self.PROTEIN_EXISTENCE_MAP.get(pe_str)

        # Extract sections
        protein_name = self._extract_protein_name(raw)
        gene_info = self._extract_gene_info(raw)
        organism = self._extract_organism(raw)

        # Sequence
        sequence_data = raw.get("sequence", {})
        sequence = sequence_data.get("value")
        sequence_length = sequence_data.get("length")
        sequence_mass = sequence_data.get("molWeight")
        sequence_checksum = sequence_data.get("crc64")

        # Comments/annotations
        comments = raw.get("comments", [])
        function = self._extract_function(comments)
        catalytic_activity = self._extract_catalytic_activity(comments)
        pathway = self._extract_pathway(comments)
        subcellular_locations = self._extract_subcellular_locations(comments)
        disease_associations = self._extract_diseases(comments)

        # Features
        features = raw.get("features", [])
        domains = self._extract_features(features, ["Domain"])
        binding_sites = self._extract_features(features, ["Binding site"])
        active_sites = self._extract_features(features, ["Active site"])
        other_features = self._extract_features(
            features,
            ["Metal binding", "Site", "Modified residue", "Transmembrane"],
        )

        # Keywords
        keywords = [kw.get("name", "") for kw in raw.get("keywords", [])]

        # Cross-references
        xrefs = raw.get("uniProtKBCrossReferences", [])
        pdb_ids = self._extract_xref_ids(xrefs, "PDB")
        chembl_id = self._extract_first_xref_id(xrefs, "ChEMBL")
        drugbank_drugs = self._extract_drugbank(xrefs)
        ensembl_gene_id = self._extract_first_xref_id(xrefs, "Ensembl")
        refseq_ids = self._extract_xref_ids(xrefs, "RefSeq")
        protein_families = self._extract_protein_families(xrefs)
        go_terms = self._extract_go_terms(xrefs)

        # Metadata
        entry_audit = raw.get("entryAudit", {})
        created_at = self._parse_date(entry_audit.get("firstPublicDate"))
        modified_at = self._parse_date(entry_audit.get("lastAnnotationUpdateDate"))
        version = entry_audit.get("entryVersion")

        return UniProtTarget(
            uniprot_id=accession,
            entry_name=entry_name,
            review_status=review_status,
            protein_existence=protein_existence,
            protein_name=protein_name,
            gene=gene_info,
            organism=organism,
            sequence=sequence,
            sequence_length=sequence_length,
            sequence_mass=sequence_mass,
            sequence_checksum=sequence_checksum,
            function=function,
            catalytic_activity=catalytic_activity,
            pathway=pathway,
            subcellular_locations=subcellular_locations,
            domains=domains,
            binding_sites=binding_sites,
            active_sites=active_sites,
            other_features=other_features,
            keywords=keywords,
            go_terms=go_terms,
            protein_families=protein_families,
            disease_associations=disease_associations,
            pdb_ids=pdb_ids[:50],  # Limit
            chembl_id=chembl_id,
            drugbank_drugs=drugbank_drugs[:20],
            ensembl_gene_id=ensembl_gene_id,
            refseq_ids=refseq_ids[:10],
            created_at=created_at,
            modified_at=modified_at,
            version=version,
        )

    def normalize_targets(self, raw_list: list[dict]) -> list[UniProtTarget]:
        """Normalize a list of UniProt entries."""
        return [self.normalize_target(r) for r in raw_list]

    # =========================================================================
    # Search Result Normalization
    # =========================================================================

    def normalize_search_hit(self, raw: dict) -> TargetSearchHit:
        """
        Normalize a single search result hit.

        Args:
            raw: Raw search hit data

        Returns:
            Normalized TargetSearchHit
        """
        # Get protein name
        protein_name = None
        pn_data = raw.get("proteinDescription", {})
        rec_name = pn_data.get("recommendedName", {})
        if rec_name:
            full_name = rec_name.get("fullName", {})
            protein_name = full_name.get("value") if isinstance(full_name, dict) else full_name

        # Get gene name
        gene_name = None
        genes = raw.get("genes", [])
        if genes:
            gene_name = genes[0].get("geneName", {}).get("value")

        # Get organism
        organism = None
        org_data = raw.get("organism", {})
        if org_data:
            organism = org_data.get("scientificName")

        # Review status
        entry_type = raw.get("entryType", "")
        review_status = (
            ReviewStatus.REVIEWED
            if "Swiss-Prot" in entry_type
            else ReviewStatus.UNREVIEWED
        )

        return TargetSearchHit(
            uniprot_id=raw.get("primaryAccession", ""),
            entry_name=raw.get("uniProtkbId"),
            protein_name=protein_name,
            gene_name=gene_name,
            organism=organism,
            review_status=review_status,
            sequence_length=raw.get("sequence", {}).get("length"),
        )

    def normalize_search_results(self, raw: dict) -> list[TargetSearchHit]:
        """
        Normalize search results to list of hits.

        Args:
            raw: Raw search response

        Returns:
            List of TargetSearchHit objects
        """
        results = raw.get("results", [])
        return [self.normalize_search_hit(r) for r in results]

    def normalize_target_summary(self, raw: dict) -> TargetSummary:
        """
        Normalize to simplified TargetSummary.

        Args:
            raw: Raw entry or search hit data

        Returns:
            TargetSummary object
        """
        # Handle both full entries and search results
        accession = raw.get("primaryAccession", "")
        entry_name = raw.get("uniProtkbId")

        # Protein name
        protein_name = None
        pn_data = raw.get("proteinDescription", {})
        rec_name = pn_data.get("recommendedName", {})
        if rec_name:
            full_name = rec_name.get("fullName", {})
            protein_name = full_name.get("value") if isinstance(full_name, dict) else full_name

        # Gene symbol
        gene_symbol = None
        genes = raw.get("genes", [])
        if genes:
            gene_symbol = genes[0].get("geneName", {}).get("value")

        # Organism
        org_data = raw.get("organism", {})
        organism = org_data.get("scientificName", "Unknown")
        tax_id = org_data.get("taxonId")

        # Sequence length
        sequence_length = raw.get("sequence", {}).get("length")

        # Review status
        entry_type = raw.get("entryType", "")
        review_status = (
            ReviewStatus.REVIEWED
            if "Swiss-Prot" in entry_type
            else ReviewStatus.UNREVIEWED
        )

        # Cross-refs
        xrefs = raw.get("uniProtKBCrossReferences", [])
        chembl_id = self._extract_first_xref_id(xrefs, "ChEMBL")
        pdb_ids = self._extract_xref_ids(xrefs, "PDB")

        return TargetSummary(
            uniprot_id=accession,
            entry_name=entry_name,
            protein_name=protein_name,
            gene_symbol=gene_symbol,
            organism=organism,
            tax_id=tax_id,
            sequence_length=sequence_length,
            review_status=review_status,
            chembl_id=chembl_id,
            pdb_count=len(pdb_ids),
        )

    # =========================================================================
    # Helper Methods - Protein Name
    # =========================================================================

    def _extract_protein_name(self, raw: dict) -> ProteinName:
        """Extract protein naming information."""
        pn_data = raw.get("proteinDescription", {})

        recommended_name = None
        short_names = []
        alternative_names = []
        ec_numbers = []

        # Recommended name
        rec_name = pn_data.get("recommendedName", {})
        if rec_name:
            full_name = rec_name.get("fullName", {})
            recommended_name = (
                full_name.get("value") if isinstance(full_name, dict) else full_name
            )
            short_names = [
                sn.get("value", "") for sn in rec_name.get("shortNames", [])
            ]
            ec_numbers = [
                ec.get("value", "") for ec in rec_name.get("ecNumbers", [])
            ]

        # Alternative names
        for alt_name in pn_data.get("alternativeNames", []):
            full_name = alt_name.get("fullName", {})
            name = full_name.get("value") if isinstance(full_name, dict) else full_name
            if name:
                alternative_names.append(name)
            for sn in alt_name.get("shortNames", []):
                if sn.get("value"):
                    alternative_names.append(sn["value"])

        # Submitted names (for unreviewed entries)
        for sub_name in pn_data.get("submissionNames", []):
            full_name = sub_name.get("fullName", {})
            name = full_name.get("value") if isinstance(full_name, dict) else full_name
            if name and not recommended_name:
                recommended_name = name

        return ProteinName(
            recommended_name=recommended_name,
            short_names=short_names,
            alternative_names=alternative_names,
            ec_numbers=ec_numbers,
        )

    # =========================================================================
    # Helper Methods - Gene Info
    # =========================================================================

    def _extract_gene_info(self, raw: dict) -> GeneInfo:
        """Extract gene information."""
        genes = raw.get("genes", [])
        if not genes:
            return GeneInfo()

        gene = genes[0]
        name = None
        synonyms = []
        orf_names = []
        ordered_locus_names = []

        # Primary gene name
        gene_name = gene.get("geneName", {})
        name = gene_name.get("value")

        # Synonyms
        for syn in gene.get("synonyms", []):
            if syn.get("value"):
                synonyms.append(syn["value"])

        # ORF names
        for orf in gene.get("orfNames", []):
            if orf.get("value"):
                orf_names.append(orf["value"])

        # Ordered locus names
        for oln in gene.get("orderedLocusNames", []):
            if oln.get("value"):
                ordered_locus_names.append(oln["value"])

        return GeneInfo(
            name=name,
            synonyms=synonyms,
            orf_names=orf_names,
            ordered_locus_names=ordered_locus_names,
        )

    # =========================================================================
    # Helper Methods - Organism
    # =========================================================================

    def _extract_organism(self, raw: dict) -> OrganismInfo:
        """Extract organism information."""
        org_data = raw.get("organism", {})

        return OrganismInfo(
            scientific_name=org_data.get("scientificName", "Unknown"),
            common_name=org_data.get("commonName"),
            tax_id=org_data.get("taxonId"),
            lineage=org_data.get("lineage", []),
        )

    # =========================================================================
    # Helper Methods - Comments/Annotations
    # =========================================================================

    def _extract_function(self, comments: list[dict]) -> list[FunctionAnnotation]:
        """Extract function annotations from comments."""
        functions = []
        for comment in comments:
            if comment.get("commentType") == "FUNCTION":
                for text in comment.get("texts", []):
                    functions.append(
                        FunctionAnnotation(
                            text=text.get("value", ""),
                            evidence=text.get("evidences", []),
                        )
                    )
        return functions

    def _extract_catalytic_activity(self, comments: list[dict]) -> list[str]:
        """Extract catalytic activity descriptions."""
        activities = []
        for comment in comments:
            if comment.get("commentType") == "CATALYTIC ACTIVITY":
                reaction = comment.get("reaction", {})
                name = reaction.get("name")
                if name:
                    activities.append(name)
        return activities

    def _extract_pathway(self, comments: list[dict]) -> list[str]:
        """Extract pathway information."""
        pathways = []
        for comment in comments:
            if comment.get("commentType") == "PATHWAY":
                for text in comment.get("texts", []):
                    pathways.append(text.get("value", ""))
        return pathways

    def _extract_subcellular_locations(
        self, comments: list[dict]
    ) -> list[SubcellularLocation]:
        """Extract subcellular location annotations."""
        locations = []
        for comment in comments:
            if comment.get("commentType") == "SUBCELLULAR LOCATION":
                for subloc in comment.get("subcellularLocations", []):
                    loc = subloc.get("location", {})
                    locations.append(
                        SubcellularLocation(
                            location=loc.get("value", ""),
                            topology=subloc.get("topology", {}).get("value"),
                            orientation=subloc.get("orientation", {}).get("value"),
                        )
                    )
        return locations

    def _extract_diseases(self, comments: list[dict]) -> list[DiseaseAssociation]:
        """Extract disease associations."""
        diseases = []
        for comment in comments:
            if comment.get("commentType") == "DISEASE":
                disease = comment.get("disease", {})
                if disease:
                    diseases.append(
                        DiseaseAssociation(
                            disease_name=disease.get("diseaseId", ""),
                            disease_id=disease.get("diseaseCrossReference", {}).get(
                                "id"
                            ),
                            description=disease.get("description"),
                            evidence=disease.get("evidences", [{}])[0].get("source")
                            if disease.get("evidences")
                            else None,
                        )
                    )
        return diseases

    # =========================================================================
    # Helper Methods - Features
    # =========================================================================

    def _extract_features(
        self, features: list[dict], types: list[str]
    ) -> list[SequenceFeature]:
        """Extract specific feature types."""
        result = []
        for feature in features:
            feat_type = feature.get("type")
            if feat_type in types:
                location = feature.get("location", {})
                start = location.get("start", {}).get("value")
                end = location.get("end", {}).get("value")

                result.append(
                    SequenceFeature(
                        type=self.FEATURE_TYPE_MAP.get(feat_type, feat_type),
                        description=feature.get("description"),
                        start=start,
                        end=end,
                        evidence=feature.get("evidences", [{}])[0].get("source")
                        if feature.get("evidences")
                        else None,
                    )
                )
        return result

    # =========================================================================
    # Helper Methods - Cross-References
    # =========================================================================

    def _extract_xref_ids(self, xrefs: list[dict], database: str) -> list[str]:
        """Extract IDs for a specific database."""
        ids = []
        for xref in xrefs:
            if xref.get("database") == database:
                xref_id = xref.get("id")
                if xref_id:
                    ids.append(xref_id)
        return ids

    def _extract_first_xref_id(self, xrefs: list[dict], database: str) -> str | None:
        """Extract first ID for a specific database."""
        ids = self._extract_xref_ids(xrefs, database)
        return ids[0] if ids else None

    def _extract_drugbank(self, xrefs: list[dict]) -> list[DrugInteraction]:
        """Extract DrugBank drug interactions."""
        drugs = []
        for xref in xrefs:
            if xref.get("database") == "DrugBank":
                drugs.append(
                    DrugInteraction(
                        drugbank_id=xref.get("id", ""),
                        drug_name=None,  # Not available in cross-ref
                    )
                )
        return drugs

    def _extract_protein_families(self, xrefs: list[dict]) -> list[str]:
        """Extract protein family classifications."""
        families = []

        # InterPro
        for xref in xrefs:
            if xref.get("database") == "InterPro":
                props = xref.get("properties", [])
                for prop in props:
                    if prop.get("key") == "EntryName":
                        families.append(f"InterPro:{prop.get('value', '')}")

        # Pfam
        for xref in xrefs:
            if xref.get("database") == "Pfam":
                props = xref.get("properties", [])
                for prop in props:
                    if prop.get("key") == "EntryName":
                        families.append(f"Pfam:{prop.get('value', '')}")

        return families[:20]  # Limit

    def _extract_go_terms(self, xrefs: list[dict]) -> list[str]:
        """Extract GO term annotations."""
        go_terms = []
        for xref in xrefs:
            if xref.get("database") == "GO":
                go_id = xref.get("id", "")
                props = xref.get("properties", [])
                term_name = ""
                for prop in props:
                    if prop.get("key") == "GoTerm":
                        term_name = prop.get("value", "")
                        break
                if go_id:
                    go_terms.append(f"{go_id}:{term_name}")
        return go_terms[:50]  # Limit

    # =========================================================================
    # Helper Methods - Utilities
    # =========================================================================

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse UniProt date string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return None
