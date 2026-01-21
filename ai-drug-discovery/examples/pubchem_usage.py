"""
PubChem Connector Usage Examples.

Demonstrates how to use the PubChem connector for common drug discovery tasks.
"""

import asyncio

from apps.api.connectors.pubchem import (
    PubChemClient,
    PubChemConnector,
    PubChemNormalizer,
    SearchType,
)


async def example_search_by_name():
    """Search compounds by name."""
    async with PubChemConnector() as connector:
        # Simple search returns CIDs
        result = await connector.search_compounds("aspirin")

        print(f"Found {result.total_count} CIDs for 'aspirin'")
        print(f"First 5 CIDs: {result.cids[:5]}")


async def example_search_with_details():
    """Search and get full compound details."""
    async with PubChemConnector() as connector:
        result = await connector.search_by_name(
            "ibuprofen",
            limit=3,
            include_synonyms=True,
        )

        print(f"Found {result.total_count} compounds for 'ibuprofen'")

        for compound in result.compounds:
            print(f"\nCID: {compound.cid}")
            print(f"  Name: {compound.title or compound.iupac_name}")
            print(f"  SMILES: {compound.canonical_smiles}")
            print(f"  MW: {compound.molecular_weight}")
            print(f"  Synonyms: {len(compound.synonyms)} total")
            if compound.synonyms:
                print(f"    First 3: {compound.synonyms[:3]}")


async def example_search_by_smiles():
    """Search by SMILES string."""
    async with PubChemConnector() as connector:
        # Caffeine SMILES
        smiles = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"

        result = await connector.search_by_smiles(smiles, limit=5)

        print(f"Found {result.total_count} compounds for caffeine SMILES")
        for compound in result.compounds:
            print(f"  CID {compound.cid}: {compound.iupac_name or 'N/A'}")


async def example_get_compound():
    """Get a single compound by CID."""
    async with PubChemConnector() as connector:
        # Aspirin CID
        compound = await connector.get_compound(2244)

        print(f"Compound: CID {compound.cid}")
        print(f"  Title: {compound.title}")
        print(f"  IUPAC: {compound.iupac_name}")
        print(f"  SMILES: {compound.canonical_smiles}")
        print(f"  InChIKey: {compound.inchikey}")
        print(f"  Formula: {compound.molecular_formula}")
        print(f"  MW: {compound.molecular_weight}")
        print(f"  XLogP: {compound.xlogp}")
        print(f"  TPSA: {compound.tpsa}")
        print(f"  HBD: {compound.hbond_donor_count}")
        print(f"  HBA: {compound.hbond_acceptor_count}")
        print(f"  Rotatable Bonds: {compound.rotatable_bond_count}")


async def example_get_properties():
    """Get computed properties for a compound."""
    async with PubChemConnector() as connector:
        # Metformin CID
        props = await connector.get_properties(4091)

        print(f"Properties for CID {props.cid}:")
        print(f"  Molecular Weight: {props.molecular_weight}")
        print(f"  XLogP: {props.xlogp}")
        print(f"  TPSA: {props.tpsa}")
        print(f"  Complexity: {props.complexity}")
        print(f"  HBD: {props.hbond_donor_count}")
        print(f"  HBA: {props.hbond_acceptor_count}")
        print(f"  Rotatable Bonds: {props.rotatable_bond_count}")
        print(f"  Heavy Atoms: {props.heavy_atom_count}")
        print(f"  RO5 Violations: {props.ro5_violations}")


async def example_get_properties_dict():
    """Get raw properties as dictionary."""
    async with PubChemConnector() as connector:
        props = await connector.get_properties_dict(2244)

        print("Raw properties dictionary:")
        for key, value in sorted(props.items()):
            print(f"  {key}: {value}")


async def example_get_bioassays():
    """Get bioassay data for a compound."""
    async with PubChemConnector() as connector:
        # Get bioassays for aspirin
        result = await connector.get_bioassays(
            2244,
            active_only=True,  # Only where aspirin was active
            limit=10,
        )

        print(f"Bioassay data for CID 2244 (Aspirin):")
        print(f"  Total assays: {result.total_assays}")
        print(f"  Total activities: {result.total_activities}")

        print("\nAssays:")
        for assay in result.assays[:3]:
            print(f"  AID {assay.aid}: {assay.name or 'N/A'}")
            print(f"    Type: {assay.assay_type.value}")
            print(f"    Target: {assay.target_name or 'N/A'}")

        print("\nActivities:")
        for activity in result.activities[:5]:
            print(f"  AID {activity.aid}: {activity.outcome.value}")
            if activity.activity_value:
                print(f"    Value: {activity.activity_value} {activity.activity_unit or ''}")


async def example_get_assay_details():
    """Get detailed assay information."""
    async with PubChemConnector() as connector:
        # Example assay AID
        assay = await connector.get_assay(1259313)

        print(f"Assay: AID {assay.aid}")
        print(f"  Name: {assay.name}")
        print(f"  Type: {assay.assay_type.value}")
        print(f"  Target: {assay.target_name}")
        print(f"  Target Gene ID: {assay.target_gene_id}")
        print(f"  Source: {assay.source_name}")
        if assay.description:
            print(f"  Description: {assay.description[:200]}...")


async def example_cross_references():
    """Get cross-references to other databases."""
    async with PubChemConnector() as connector:
        # Aspirin CID
        cid = 2244

        chembl_id = await connector.get_chembl_id(cid)
        cas_number = await connector.get_cas_number(cid)

        print(f"Cross-references for CID {cid}:")
        print(f"  ChEMBL ID: {chembl_id or 'Not found'}")
        print(f"  CAS Number: {cas_number or 'Not found'}")


async def example_batch_compounds():
    """Get multiple compounds in batch."""
    async with PubChemConnector() as connector:
        cids = [2244, 3672, 5988, 5281, 4091]  # Aspirin, Ibuprofen, Sucrose, Caffeine, Metformin

        compounds = await connector.get_compounds_batch(cids)

        print(f"Batch retrieved {len(compounds)} compounds:")
        for compound in compounds:
            print(f"  CID {compound.cid}: {compound.title or compound.iupac_name or 'N/A'}")
            print(f"    MW: {compound.molecular_weight}")


async def example_streaming():
    """Stream compounds for bulk operations."""
    async with PubChemConnector() as connector:
        # Search and stream results
        count = 0

        async for compound in connector.iter_search_results(
            "kinase inhibitor",
            max_results=20,
            batch_size=5,
        ):
            count += 1
            if count <= 3:
                print(f"  Streamed CID {compound.cid}: MW={compound.molecular_weight}")

        print(f"  ... total streamed: {count}")


async def example_low_level_client():
    """Use the low-level client directly."""
    async with PubChemClient() as client:
        # Direct API call for CIDs
        cids = await client.search_cids("name", "acetaminophen")
        print(f"Found CIDs: {cids[:5]}")

        # Get properties
        if cids:
            props = await client.get_properties(
                cids[0],
                ["MolecularWeight", "XLogP", "TPSA"],
            )
            print(f"Properties: {props}")

        # Normalize manually
        normalizer = PubChemNormalizer()
        if cids:
            raw = await client.get_properties(cids[0])
            compound = normalizer.normalize_compound_from_properties(raw)
            print(f"Normalized: CID {compound.cid}, MW={compound.molecular_weight}")


async def main():
    """Run all examples."""
    print("=" * 60)
    print("PubChem Connector Usage Examples")
    print("=" * 60)

    print("\n1. Search by Name")
    print("-" * 40)
    await example_search_by_name()

    print("\n2. Search with Full Details")
    print("-" * 40)
    await example_search_with_details()

    print("\n3. Search by SMILES")
    print("-" * 40)
    await example_search_by_smiles()

    print("\n4. Get Single Compound")
    print("-" * 40)
    await example_get_compound()

    print("\n5. Get Properties (Normalized)")
    print("-" * 40)
    await example_get_properties()

    print("\n6. Get Properties (Raw Dict)")
    print("-" * 40)
    await example_get_properties_dict()

    print("\n7. Get Bioassays")
    print("-" * 40)
    await example_get_bioassays()

    print("\n8. Get Assay Details")
    print("-" * 40)
    await example_get_assay_details()

    print("\n9. Cross-References")
    print("-" * 40)
    await example_cross_references()

    print("\n10. Batch Compounds")
    print("-" * 40)
    await example_batch_compounds()

    print("\n11. Streaming for Bulk Operations")
    print("-" * 40)
    await example_streaming()

    print("\n12. Low-Level Client Usage")
    print("-" * 40)
    await example_low_level_client()

    print("\n" + "=" * 60)
    print("Examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
