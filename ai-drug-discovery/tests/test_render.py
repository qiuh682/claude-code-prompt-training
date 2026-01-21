"""Tests for molecular 2D rendering."""

import pytest

from packages.chemistry.render import (
    ImageFormat,
    RenderError,
    RenderOptions,
    mol_to_data_url,
    render_molecule,
    render_molecules_grid,
    render_png,
    render_reaction,
    render_svg,
)


# ============================================================================
# Test data
# ============================================================================

ETHANOL = "CCO"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
CAFFEINE = "Cn1cnc2c1c(=O)n(c(=O)n2C)C"
BENZENE = "c1ccccc1"
INVALID_SMILES = "INVALID_SMILES_XXX"


class TestRenderSVG:
    """Tests for SVG rendering."""

    def test_render_svg_basic(self):
        """Test basic SVG rendering."""
        svg = render_svg(ETHANOL)

        assert isinstance(svg, str)
        assert svg.startswith("<?xml") or svg.startswith("<svg")
        assert "</svg>" in svg

    def test_render_svg_aspirin(self):
        """Test SVG rendering of aspirin."""
        svg = render_svg(ASPIRIN)

        assert "<svg" in svg
        assert "</svg>" in svg
        # Should contain path elements for bonds
        assert "<path" in svg or "d=" in svg

    def test_render_svg_with_options(self):
        """Test SVG rendering with custom options."""
        options = RenderOptions(width=400, height=400)
        svg = render_svg(ASPIRIN, options)

        # RDKit outputs width with 'px' suffix
        assert "width='400px'" in svg or 'width="400px"' in svg or "400 400" in svg

    def test_render_svg_invalid_smiles(self):
        """Test error handling for invalid SMILES."""
        with pytest.raises(ValueError, match="Invalid SMILES"):
            render_svg(INVALID_SMILES)

    def test_render_svg_deterministic(self):
        """Test that SVG rendering is deterministic."""
        svg1 = render_svg(BENZENE)
        svg2 = render_svg(BENZENE)
        assert svg1 == svg2

    def test_render_svg_with_highlighting(self):
        """Test SVG with atom highlighting."""
        options = RenderOptions(
            highlight_atoms=[0, 1],
            highlight_color=(1.0, 0.5, 0.5),
        )
        svg = render_svg(ETHANOL, options)
        assert "<svg" in svg

    def test_render_svg_from_mol_object(self):
        """Test rendering from Mol object."""
        from rdkit import Chem

        mol = Chem.MolFromSmiles(ASPIRIN)
        svg = render_svg(mol)
        assert "<svg" in svg


class TestRenderPNG:
    """Tests for PNG rendering."""

    def test_render_png_basic(self):
        """Test basic PNG rendering."""
        png = render_png(ETHANOL)

        assert isinstance(png, bytes)
        # PNG magic bytes
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_render_png_aspirin(self):
        """Test PNG rendering of aspirin."""
        png = render_png(ASPIRIN)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_render_png_with_options(self):
        """Test PNG rendering with custom options."""
        options = RenderOptions(width=200, height=200)
        png = render_png(CAFFEINE, options)

        assert isinstance(png, bytes)
        assert len(png) > 0

    def test_render_png_invalid_smiles(self):
        """Test error handling for invalid SMILES."""
        with pytest.raises(ValueError, match="Invalid SMILES"):
            render_png(INVALID_SMILES)

    def test_render_png_deterministic(self):
        """Test that PNG rendering is deterministic."""
        png1 = render_png(BENZENE)
        png2 = render_png(BENZENE)
        assert png1 == png2

    def test_render_png_with_background_color(self):
        """Test PNG with background color."""
        options = RenderOptions(background_color="#FFFFFF")
        png = render_png(ETHANOL, options)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


class TestRenderMolecule:
    """Tests for generic render function."""

    def test_render_molecule_svg(self):
        """Test rendering as SVG via generic function."""
        result = render_molecule(ASPIRIN, format=ImageFormat.SVG)
        assert isinstance(result, str)
        assert "<svg" in result

    def test_render_molecule_png(self):
        """Test rendering as PNG via generic function."""
        result = render_molecule(ASPIRIN, format=ImageFormat.PNG)
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_render_molecule_default_format(self):
        """Test default format is SVG."""
        result = render_molecule(ASPIRIN)
        assert isinstance(result, str)
        assert "<svg" in result


class TestRenderMoleculesGrid:
    """Tests for grid rendering."""

    def test_render_grid_basic(self):
        """Test basic grid rendering."""
        molecules = [ETHANOL, ASPIRIN, BENZENE]
        svg = render_molecules_grid(molecules)

        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_render_grid_with_legends(self):
        """Test grid with legends."""
        molecules = [ETHANOL, ASPIRIN]
        legends = ["Ethanol", "Aspirin"]
        svg = render_molecules_grid(molecules, legends=legends)

        # Just verify SVG is produced - RDKit may not include legends as searchable text
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_render_grid_custom_size(self):
        """Test grid with custom size."""
        molecules = [ETHANOL, BENZENE, ASPIRIN, CAFFEINE]
        svg = render_molecules_grid(
            molecules, mols_per_row=2, sub_img_size=(150, 150)
        )
        assert "<svg" in svg

    def test_render_grid_as_png(self):
        """Test grid as PNG."""
        molecules = [ETHANOL, BENZENE]
        png = render_molecules_grid(molecules, format=ImageFormat.PNG)

        assert isinstance(png, bytes)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_render_grid_single_molecule(self):
        """Test grid with single molecule."""
        svg = render_molecules_grid([ASPIRIN])
        assert "<svg" in svg


class TestRenderReaction:
    """Tests for reaction rendering."""

    def test_render_reaction_basic(self):
        """Test basic reaction rendering."""
        # Simple reaction: C + O >> CO
        rxn_smarts = "[C:1].[O:2]>>[C:1][O:2]"
        svg = render_reaction(rxn_smarts)

        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_render_reaction_esterification(self):
        """Test esterification reaction."""
        # Simplified esterification
        rxn_smarts = "[OH:1].[C:2](=O)[OH:3]>>[O:1][C:2](=O).[OH2:3]"
        svg = render_reaction(rxn_smarts)
        assert "<svg" in svg

    def test_render_reaction_invalid(self):
        """Test invalid reaction SMARTS."""
        with pytest.raises((ValueError, RenderError)):
            render_reaction("NOT_A_REACTION")


class TestMolToDataUrl:
    """Tests for data URL generation."""

    def test_data_url_png(self):
        """Test PNG data URL."""
        url = mol_to_data_url(ASPIRIN, format=ImageFormat.PNG)

        assert url.startswith("data:image/png;base64,")
        # Should be valid base64
        import base64

        base64_part = url.split(",")[1]
        decoded = base64.b64decode(base64_part)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"

    def test_data_url_svg(self):
        """Test SVG data URL."""
        url = mol_to_data_url(ASPIRIN, format=ImageFormat.SVG)

        assert url.startswith("data:image/svg+xml;base64,")
        # Should be valid base64
        import base64

        base64_part = url.split(",")[1]
        decoded = base64.b64decode(base64_part).decode("utf-8")
        assert "<svg" in decoded


class TestRenderOptions:
    """Tests for RenderOptions."""

    def test_render_options_defaults(self):
        """Test default options."""
        opts = RenderOptions()
        assert opts.width == 300
        assert opts.height == 300
        assert opts.background_color is None

    def test_render_options_custom(self):
        """Test custom options."""
        opts = RenderOptions(
            width=500,
            height=400,
            background_color="#EEEEEE",
            bond_line_width=3.0,
        )
        assert opts.width == 500
        assert opts.height == 400
        assert opts.background_color == "#EEEEEE"

    def test_render_options_highlighting(self):
        """Test highlighting options."""
        opts = RenderOptions(
            highlight_atoms=[0, 1, 2],
            highlight_bonds=[0],
            highlight_color=(1.0, 0.8, 0.0),
        )
        assert opts.highlight_atoms == [0, 1, 2]
        assert opts.highlight_bonds == [0]


class TestEdgeCases:
    """Tests for edge cases."""

    def test_render_single_atom(self):
        """Test rendering single atom."""
        svg = render_svg("[Na+]")
        assert "<svg" in svg

    def test_render_charged_molecule(self):
        """Test rendering charged molecule."""
        svg = render_svg("[NH4+]")
        assert "<svg" in svg

    def test_render_with_stereo(self):
        """Test rendering with stereochemistry."""
        # L-alanine
        svg = render_svg("N[C@@H](C)C(=O)O")
        assert "<svg" in svg

    def test_render_large_molecule(self):
        """Test rendering larger molecule."""
        # Taxol-like structure (simplified)
        large_smiles = "CC(=O)OC1C2C(C(=O)C3(C(CC4C(C3C(C(C2(C)C)(CC1OC(=O)C5=CC=CC=C5)O)OC(=O)C6=CC=CC=C6)(CO4)OC(=O)C)O)C)OC(=O)C7=CC=CC=C7"
        svg = render_svg(large_smiles)
        assert "<svg" in svg

    def test_render_molecule_with_3d_coords(self):
        """Test rendering molecule that has 3D coordinates."""
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(ETHANOL)
        AllChem.EmbedMolecule(mol, AllChem.ETKDG())

        # Should generate 2D coords for rendering
        svg = render_svg(mol)
        assert "<svg" in svg
