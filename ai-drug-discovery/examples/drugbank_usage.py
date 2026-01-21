"""
DrugBank Connector Usage Examples.

Demonstrates how to use the DrugBank connector for drug discovery workflows.

The connector supports two modes:
1. API mode - Requires DRUGBANK_API_KEY environment variable
2. Local mode - Requires DRUGBANK_DATA_PATH pointing to downloaded dataset

Set one of these environment variables before running:
- export DRUGBANK_API_KEY=your_api_key
- export DRUGBANK_DATA_PATH=/path/to/drugbank/data
"""

import asyncio
import os

from apps.api.connectors.drugbank import (
    DrugBankConnector,
    DrugBankLocalReader,
    DrugBankMode,
    NotConfiguredError,
)


async def example_check_status():
    """Check connector configuration status."""
    async with DrugBankConnector() as connector:
        status = await connector.get_status()

        print(f"Mode: {status.mode.value}")
        print(f"Is Configured: {status.is_configured}")
        print(f"API Available: {status.api_available}")
        print(f"Local Data Available: {status.local_data_available}")

        if status.local_data_path:
            print(f"Local Data Path: {status.local_data_path}")

        if status.drug_count:
            print(f"Drug Count: {status.drug_count}")

        if status.message:
            print(f"Message: {status.message}")


async def example_get_drug():
    """Get a drug by DrugBank ID."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        # Aspirin
        drug = await connector.get_drug("DB00945")

        print(f"Drug: {drug.drugbank_id}")
        print(f"  Name: {drug.name}")
        print(f"  Type: {drug.drug_type.value}")
        print(f"  Groups: {[g.value for g in drug.groups]}")
        print(f"  Is Approved: {drug.is_approved}")
        print(f"  CAS Number: {drug.cas_number}")
        print(f"  SMILES: {drug.canonical_smiles}")
        print(f"  Molecular Weight: {drug.molecular_weight}")

        if drug.mechanism_of_action:
            print(f"  Mechanism: {drug.mechanism_of_action[:100]}...")


async def example_get_drug_targets():
    """Get drug-target interactions."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        # Imatinib (Gleevec) - BCR-ABL inhibitor
        result = await connector.get_drug_targets("DB00619")

        print(f"DTIs for {result.drug_name or result.drugbank_id}:")
        print(f"  Total interactions: {result.total_count}")

        for dti in result.interactions[:5]:
            print(f"\n  Target: {dti.target_name}")
            print(f"    Type: {dti.target_type.value}")
            print(f"    UniProt: {dti.uniprot_id}")
            print(f"    Gene: {dti.gene_name}")
            print(f"    Action: {dti.action.value}")
            print(f"    Actions: {', '.join(dti.actions)}")


async def example_get_admet():
    """Get ADMET properties for a drug."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        admet = await connector.get_admet("DB00945")

        print("ADMET Properties for Aspirin:")
        print(f"  Absorption: {admet.absorption[:100] if admet.absorption else 'N/A'}...")
        print(f"  Protein Binding: {admet.protein_binding or 'N/A'}")
        print(f"  Half-life: {admet.half_life or 'N/A'}")
        print(f"  Metabolism: {admet.metabolism[:100] if admet.metabolism else 'N/A'}...")
        print(f"  Route of Elimination: {admet.route_of_elimination or 'N/A'}")
        print(f"  Toxicity: {admet.toxicity[:100] if admet.toxicity else 'N/A'}...")


async def example_search_drugs():
    """Search drugs by name."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        result = await connector.search_drugs("metformin", limit=5)

        print(f"Search results for 'metformin': {result.total_count} total")

        for hit in result.hits:
            print(f"\n  {hit.drugbank_id}: {hit.name}")
            print(f"    Type: {hit.drug_type.value}")
            print(f"    Groups: {[g.value for g in hit.groups]}")
            print(f"    MW: {hit.molecular_weight}")


async def example_get_drug_by_name():
    """Get drug by name."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        drug = await connector.get_drug_by_name("Atorvastatin")

        if drug:
            print(f"Found: {drug.drugbank_id} - {drug.name}")
            print(f"  Indication: {drug.indication[:150] if drug.indication else 'N/A'}...")
        else:
            print("Drug not found")


async def example_drug_categories():
    """Get drug categories and classifications."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        drug = await connector.get_drug("DB00945")

        print(f"Categories for {drug.name}:")
        for cat in drug.categories[:10]:
            print(f"  - {cat.category} (MeSH: {cat.mesh_id or 'N/A'})")

        if drug.atc_codes:
            print(f"\nATC Codes: {', '.join(drug.atc_codes)}")


async def example_cross_references():
    """Get cross-references to other databases."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        drug = await connector.get_drug("DB00945")

        print(f"Cross-references for {drug.name}:")
        print(f"  ChEMBL: {drug.chembl_id or 'N/A'}")
        print(f"  PubChem CID: {drug.pubchem_cid or 'N/A'}")
        print(f"  KEGG: {drug.kegg_id or 'N/A'}")
        print(f"  ChEBI: {drug.chebi_id or 'N/A'}")
        print(f"  PDB: {', '.join(drug.pdb_ids[:5]) if drug.pdb_ids else 'N/A'}")

        print(f"\nAll external IDs:")
        for ext in drug.external_ids[:10]:
            print(f"  {ext.resource}: {ext.identifier}")


async def example_drug_interactions():
    """Get drug-drug interactions."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        drug = await connector.get_drug("DB00945")

        print(f"Drug interactions for {drug.name}:")
        print(f"  Total: {len(drug.drug_interactions)}")

        for interaction in drug.drug_interactions[:5]:
            print(f"\n  With: {interaction.drug_name} ({interaction.drugbank_id})")
            if interaction.description:
                print(f"    {interaction.description[:100]}...")


async def example_batch_fetch():
    """Fetch multiple drugs in batch."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        drugbank_ids = ["DB00945", "DB00619", "DB00563", "DB00316"]

        drugs = await connector.get_drugs_batch(drugbank_ids)

        print(f"Fetched {len(drugs)} drugs:")
        for drug in drugs:
            print(f"  {drug.drugbank_id}: {drug.name} ({drug.drug_type.value})")


async def example_streaming():
    """Stream DTIs for multiple drugs."""
    async with DrugBankConnector() as connector:
        if not connector.is_configured:
            print("DrugBank not configured - skipping example")
            return

        drugbank_ids = ["DB00945", "DB00619"]
        count = 0

        async for dti in connector.iter_dtis(drugbank_ids):
            count += 1
            if count <= 5:
                print(f"  {dti.drugbank_id} -> {dti.target_name} ({dti.action.value})")

        print(f"  ... total streamed: {count}")


async def example_local_reader():
    """Use local reader directly (when data available)."""
    data_path = os.environ.get("DRUGBANK_DATA_PATH")

    if not data_path:
        print("DRUGBANK_DATA_PATH not set - skipping local reader example")
        return

    reader = DrugBankLocalReader(data_path)

    if not reader.is_available:
        print(f"Local data not found at {data_path}")
        return

    # Load index
    await reader.load_index()

    status = reader.get_status()
    print(f"Local Data Status:")
    print(f"  Path: {status['data_path']}")
    print(f"  Has XML: {status['has_xml_database']}")
    print(f"  Has Structures CSV: {status['has_structures_csv']}")
    print(f"  Has DTI CSV: {status['has_dti_csv']}")
    print(f"  Drug Count: {status['drug_count']}")

    # Get a drug
    drug = await reader.get_drug("DB00945")
    if drug:
        print(f"\nDrug from local: {drug.get('name')}")

    # Search
    results = await reader.search_drugs("aspirin", limit=5)
    print(f"\nSearch results: {len(results)} drugs")


async def example_not_configured_handling():
    """Handle not configured state gracefully."""
    # Create connector without any config
    connector = DrugBankConnector(api_key=None, data_path=None)

    status = await connector.get_status()
    print(f"Mode: {status.mode.value}")

    if status.mode == DrugBankMode.NOT_CONFIGURED:
        print("DrugBank not configured!")
        print("Options:")
        print("  1. Set DRUGBANK_API_KEY for API access")
        print("  2. Set DRUGBANK_DATA_PATH for local dataset")
        print("  3. Download data from https://go.drugbank.com/releases")

    try:
        await connector.get_drug("DB00945")
    except NotConfiguredError as e:
        print(f"\nExpected error: {e}")

    await connector.close()


async def main():
    """Run all examples."""
    print("=" * 60)
    print("DrugBank Connector Usage Examples")
    print("=" * 60)

    print("\n1. Check Configuration Status")
    print("-" * 40)
    await example_check_status()

    print("\n2. Get Drug by ID")
    print("-" * 40)
    await example_get_drug()

    print("\n3. Get Drug-Target Interactions")
    print("-" * 40)
    await example_get_drug_targets()

    print("\n4. Get ADMET Properties")
    print("-" * 40)
    await example_get_admet()

    print("\n5. Search Drugs")
    print("-" * 40)
    await example_search_drugs()

    print("\n6. Get Drug by Name")
    print("-" * 40)
    await example_get_drug_by_name()

    print("\n7. Drug Categories")
    print("-" * 40)
    await example_drug_categories()

    print("\n8. Cross-References")
    print("-" * 40)
    await example_cross_references()

    print("\n9. Drug-Drug Interactions")
    print("-" * 40)
    await example_drug_interactions()

    print("\n10. Batch Fetch")
    print("-" * 40)
    await example_batch_fetch()

    print("\n11. Streaming DTIs")
    print("-" * 40)
    await example_streaming()

    print("\n12. Local Reader (Direct)")
    print("-" * 40)
    await example_local_reader()

    print("\n13. Not Configured Handling")
    print("-" * 40)
    await example_not_configured_handling()

    print("\n" + "=" * 60)
    print("Examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
