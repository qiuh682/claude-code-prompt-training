"""
UniProt Connector Usage Examples.

Demonstrates how to use the UniProt connector for target profiling
in drug discovery workflows.
"""

import asyncio

from apps.api.connectors.uniprot import (
    UniProtClient,
    UniProtConnector,
    UniProtNormalizer,
)


async def example_get_target():
    """Fetch a target by UniProt accession."""
    async with UniProtConnector() as connector:
        # EGFR (Epidermal Growth Factor Receptor) - common cancer target
        target = await connector.get_target("P00533")

        print(f"Target: {target.uniprot_id} ({target.entry_name})")
        print(f"  Protein: {target.protein_name.recommended_name}")
        print(f"  Gene: {target.gene.name}")
        print(f"  Organism: {target.organism.scientific_name}")
        print(f"  Review Status: {target.review_status.value}")
        print(f"  Sequence Length: {target.sequence_length} aa")
        print(f"  Keywords: {', '.join(target.keywords[:5])}...")


async def example_get_target_annotations():
    """Get detailed annotations for target profiling."""
    async with UniProtConnector() as connector:
        target = await connector.get_target("P00533")

        print(f"\nAnnotations for {target.display_name}:")

        # Function
        print("\nFunction:")
        for func in target.function[:2]:
            print(f"  {func.text[:200]}...")

        # Domains
        print("\nDomains:")
        for domain in target.domains[:5]:
            print(f"  {domain.description}: {domain.start}-{domain.end}")

        # Active sites
        print("\nActive Sites:")
        for site in target.active_sites[:3]:
            print(f"  {site.description}: position {site.start}")

        # Subcellular location
        print("\nSubcellular Location:")
        for loc in target.subcellular_locations[:3]:
            print(f"  {loc.location}")

        # Disease associations
        print("\nDisease Associations:")
        for disease in target.disease_associations[:3]:
            print(f"  {disease.disease_name}")


async def example_get_cross_references():
    """Get cross-references to other databases."""
    async with UniProtConnector() as connector:
        target = await connector.get_target("P00533")

        print(f"\nCross-references for {target.uniprot_id}:")
        print(f"  ChEMBL ID: {target.chembl_id}")
        print(f"  PDB structures: {len(target.pdb_ids)} ({', '.join(target.pdb_ids[:5])}...)")
        print(f"  DrugBank drugs: {len(target.drugbank_drugs)}")
        print(f"  Ensembl Gene: {target.ensembl_gene_id}")

        # Protein families
        print(f"\nProtein Families:")
        for family in target.protein_families[:5]:
            print(f"  {family}")


async def example_get_sequence():
    """Get protein sequence."""
    async with UniProtConnector() as connector:
        sequence = await connector.get_sequence("P00533")

        print(f"Sequence length: {len(sequence)} aa")
        print(f"First 60 residues: {sequence[:60]}...")
        print(f"Last 60 residues: ...{sequence[-60:]}")


async def example_get_fasta():
    """Get sequence in FASTA format."""
    async with UniProtConnector() as connector:
        fasta = await connector.get_fasta("P00533")

        lines = fasta.split("\n")
        print(f"FASTA header: {lines[0]}")
        print(f"Sequence lines: {len(lines) - 1}")


async def example_search_targets():
    """Search targets by query."""
    async with UniProtConnector() as connector:
        result = await connector.search_targets(
            "kinase AND organism_id:9606",
            limit=10,
            reviewed_only=True,
        )

        print(f"Found {result.total_count} targets for 'kinase human'")
        print(f"Has more: {result.has_more}")

        for hit in result.hits[:5]:
            print(f"  {hit.uniprot_id}: {hit.protein_name} ({hit.gene_name})")


async def example_search_by_gene():
    """Search by gene symbol."""
    async with UniProtConnector() as connector:
        result = await connector.search_by_gene(
            "BRAF",
            organism_id=connector.HUMAN,
            reviewed_only=True,
        )

        print(f"Found {result.total_count} results for gene 'BRAF'")

        for hit in result.hits:
            print(f"  {hit.uniprot_id}: {hit.protein_name}")
            print(f"    Organism: {hit.organism}")


async def example_search_human_gene():
    """Convenience method for human genes."""
    async with UniProtConnector() as connector:
        # Get TP53 (tumor suppressor)
        target = await connector.search_human_gene("TP53")

        if target:
            print(f"Found: {target.uniprot_id}")
            print(f"  Protein: {target.protein_name.recommended_name}")
            print(f"  EC Numbers: {target.protein_name.ec_numbers}")
            print(f"  Keywords: {', '.join(target.keywords[:5])}")
        else:
            print("Not found")


async def example_search_by_protein_name():
    """Search by protein name."""
    async with UniProtConnector() as connector:
        result = await connector.search_by_protein_name(
            "insulin receptor",
            organism_id=connector.HUMAN,
            limit=5,
        )

        print(f"Found {result.total_count} results for 'insulin receptor'")

        for hit in result.hits:
            print(f"  {hit.uniprot_id}: {hit.protein_name}")


async def example_search_by_ec_number():
    """Search enzymes by EC number."""
    async with UniProtConnector() as connector:
        # EC 2.7.10.1 = Receptor tyrosine kinases
        result = await connector.search_by_ec_number(
            "2.7.10.1",
            organism_id=connector.HUMAN,
            limit=10,
        )

        print(f"Found {result.total_count} receptor tyrosine kinases")

        for hit in result.hits[:5]:
            print(f"  {hit.uniprot_id}: {hit.gene_name} - {hit.protein_name}")


async def example_get_target_categories():
    """Get common drug target categories."""
    async with UniProtConnector() as connector:
        # Human kinases
        kinases = await connector.get_human_kinases(limit=10)
        print(f"\nHuman Kinases (showing 10 of many):")
        for hit in kinases[:5]:
            print(f"  {hit.gene_name}: {hit.protein_name}")

        # Human GPCRs
        gpcrs = await connector.get_human_gpcrs(limit=10)
        print(f"\nHuman GPCRs (showing 10 of many):")
        for hit in gpcrs[:5]:
            print(f"  {hit.gene_name}: {hit.protein_name}")


async def example_uniprot_to_chembl():
    """Map UniProt IDs to ChEMBL IDs."""
    async with UniProtConnector() as connector:
        uniprot_ids = ["P00533", "P04626", "P08069", "P12931"]

        mapping = await connector.uniprot_to_chembl(uniprot_ids)

        print("UniProt -> ChEMBL mapping:")
        for uid, chembl_id in mapping.items():
            print(f"  {uid} -> {chembl_id or 'N/A'}")


async def example_batch_targets():
    """Get multiple targets in batch."""
    async with UniProtConnector() as connector:
        uniprot_ids = ["P00533", "P04626", "P08069"]

        targets = await connector.get_targets_batch(uniprot_ids)

        print(f"Fetched {len(targets)} targets:")
        for target in targets:
            print(f"  {target.uniprot_id}: {target.display_name}")
            print(f"    Gene: {target.gene_symbol}")
            print(f"    PDB structures: {len(target.pdb_ids)}")


async def example_streaming():
    """Stream search results for bulk operations."""
    async with UniProtConnector() as connector:
        count = 0

        async for hit in connector.iter_search_results(
            "kinase AND organism_id:9606",
            reviewed_only=True,
            max_results=20,
        ):
            count += 1
            if count <= 3:
                print(f"  Streamed: {hit.uniprot_id} - {hit.gene_name}")

        print(f"  ... total streamed: {count}")


async def example_low_level_client():
    """Use the low-level client directly."""
    async with UniProtClient() as client:
        # Direct search
        results = await client.search(
            "EGFR AND organism_id:9606 AND reviewed:true",
            size=3,
        )

        print(f"Raw results count: {len(results.get('results', []))}")

        # Get entry
        entry = await client.get_entry("P00533")
        print(f"Entry type: {entry.get('entryType')}")

        # Normalize manually
        normalizer = UniProtNormalizer()
        target = normalizer.normalize_target(entry)
        print(f"Normalized: {target.display_name}")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("UniProt Connector Usage Examples")
    print("=" * 60)

    print("\n1. Get Target by UniProt ID")
    print("-" * 40)
    await example_get_target()

    print("\n2. Get Target Annotations")
    print("-" * 40)
    await example_get_target_annotations()

    print("\n3. Get Cross-References")
    print("-" * 40)
    await example_get_cross_references()

    print("\n4. Get Protein Sequence")
    print("-" * 40)
    await example_get_sequence()

    print("\n5. Get FASTA")
    print("-" * 40)
    await example_get_fasta()

    print("\n6. Search Targets")
    print("-" * 40)
    await example_search_targets()

    print("\n7. Search by Gene Symbol")
    print("-" * 40)
    await example_search_by_gene()

    print("\n8. Search Human Gene (Convenience)")
    print("-" * 40)
    await example_search_human_gene()

    print("\n9. Search by Protein Name")
    print("-" * 40)
    await example_search_by_protein_name()

    print("\n10. Search by EC Number")
    print("-" * 40)
    await example_search_by_ec_number()

    print("\n11. Drug Target Categories")
    print("-" * 40)
    await example_get_target_categories()

    print("\n12. UniProt to ChEMBL Mapping")
    print("-" * 40)
    await example_uniprot_to_chembl()

    print("\n13. Batch Target Fetch")
    print("-" * 40)
    await example_batch_targets()

    print("\n14. Streaming for Bulk Operations")
    print("-" * 40)
    await example_streaming()

    print("\n15. Low-Level Client Usage")
    print("-" * 40)
    await example_low_level_client()

    print("\n" + "=" * 60)
    print("Examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
