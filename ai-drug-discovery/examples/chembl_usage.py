"""
ChEMBL Connector Usage Examples.

Demonstrates how to use the ChEMBL connector for common drug discovery tasks.
"""

import asyncio

from apps.api.connectors.chembl import (
    ChEMBLClient,
    ChEMBLConnector,
    ChEMBLNormalizer,
)


async def example_get_compound():
    """Fetch a single compound by ChEMBL ID."""
    async with ChEMBLConnector() as connector:
        # Aspirin
        compound = await connector.get_compound("CHEMBL25")

        print(f"Compound: {compound.chembl_id}")
        print(f"  Name: {compound.pref_name}")
        print(f"  SMILES: {compound.canonical_smiles}")
        print(f"  MW: {compound.molecular_weight}")
        print(f"  LogP: {compound.alogp}")
        print(f"  Max Phase: {compound.max_phase}")


async def example_search_by_target():
    """Find active compounds for a target (e.g., EGFR)."""
    async with ChEMBLConnector() as connector:
        # EGFR (Epidermal Growth Factor Receptor)
        result = await connector.search_compounds_by_target(
            "CHEMBL203",
            min_pchembl=6.0,  # pChEMBL >= 6 (IC50 < 1 µM)
            limit=10,
        )

        print(f"Found {result.total_count} compounds for EGFR")
        print(f"Showing top {len(result.compounds)}:")

        for compound in result.compounds:
            print(f"  {compound.chembl_id}: {compound.pref_name or 'N/A'}")


async def example_get_bioactivities():
    """Get bioactivity data for a target."""
    async with ChEMBLConnector() as connector:
        # Get IC50 and Ki values for EGFR
        result = await connector.get_bioactivities_by_target(
            "CHEMBL203",
            activity_types=["IC50", "Ki"],
            limit=20,
        )

        print(f"Found {result.total_count} bioactivities")

        for activity in result.bioactivities[:5]:
            print(
                f"  {activity.molecule_chembl_id}: "
                f"{activity.standard_type.value} = {activity.standard_value} "
                f"{activity.standard_units or ''} "
                f"(pChEMBL: {activity.pchembl_value or 'N/A'})"
            )


async def example_get_target():
    """Fetch target information."""
    async with ChEMBLConnector() as connector:
        target = await connector.get_target("CHEMBL203")

        print(f"Target: {target.chembl_id}")
        print(f"  Name: {target.pref_name}")
        print(f"  UniProt: {target.uniprot_id}")
        print(f"  Gene: {target.gene_symbol}")
        print(f"  Type: {target.target_type}")
        print(f"  Organism: {target.organism}")


async def example_search_by_uniprot():
    """Search compounds by UniProt ID."""
    async with ChEMBLConnector() as connector:
        # Human EGFR UniProt ID
        result = await connector.search_compounds_by_uniprot(
            "P00533",
            min_pchembl=7.0,
            limit=5,
        )

        print(f"Found {result.total_count} compounds for UniProt P00533")
        for compound in result.compounds:
            print(f"  {compound.chembl_id}: {compound.canonical_smiles[:50]}...")


async def example_streaming_sync():
    """Stream bioactivities for bulk sync operations."""
    async with ChEMBLConnector() as connector:
        count = 0

        # Stream all bioactivities (useful for database sync)
        async for activity in connector.iter_bioactivities_by_target(
            "CHEMBL203",
            activity_types=["IC50"],
            max_results=100,  # Limit for demo
        ):
            count += 1
            if count <= 3:
                print(
                    f"  Streamed: {activity.molecule_chembl_id} - "
                    f"{activity.standard_value} {activity.standard_units}"
                )

        print(f"  ... total streamed: {count}")


async def example_low_level_client():
    """Use the low-level client directly for custom queries."""
    async with ChEMBLClient() as client:
        # Direct API call
        data = await client.get("/molecule/CHEMBL25.json")

        print(f"Raw response keys: {list(data.keys())}")

        # Normalize manually
        normalizer = ChEMBLNormalizer()
        compound = normalizer.normalize_compound(data)

        print(f"Normalized: {compound.chembl_id} - {compound.pref_name}")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("ChEMBL Connector Usage Examples")
    print("=" * 60)

    print("\n1. Get Single Compound")
    print("-" * 40)
    await example_get_compound()

    print("\n2. Search Compounds by Target")
    print("-" * 40)
    await example_search_by_target()

    print("\n3. Get Bioactivities")
    print("-" * 40)
    await example_get_bioactivities()

    print("\n4. Get Target Information")
    print("-" * 40)
    await example_get_target()

    print("\n5. Search by UniProt ID")
    print("-" * 40)
    await example_search_by_uniprot()

    print("\n6. Streaming for Bulk Sync")
    print("-" * 40)
    await example_streaming_sync()

    print("\n7. Low-Level Client Usage")
    print("-" * 40)
    await example_low_level_client()

    print("\n" + "=" * 60)
    print("Examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
