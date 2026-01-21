"""
Molecular 2D rendering using RDKit.

This module provides deterministic 2D depiction of molecules:
- SVG rendering (vector, scalable)
- PNG rendering (raster, fixed resolution)

Rendering is deterministic given the same molecule and parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rdkit.Chem import Mol


class ImageFormat(str, Enum):
    """Supported image formats."""

    SVG = "svg"
    PNG = "png"


@dataclass(frozen=True)
class RenderOptions:
    """Options for molecule rendering."""

    width: int = 300
    height: int = 300
    background_color: str | None = None  # None = transparent, or hex color
    bond_line_width: float = 2.0
    atom_label_font_size: int = 12
    add_atom_indices: bool = False
    add_stereo_annotation: bool = True
    highlight_atoms: list[int] | None = None
    highlight_bonds: list[int] | None = None
    highlight_color: tuple[float, float, float] | None = None  # RGB 0-1


class RenderError(Exception):
    """Error during molecule rendering."""

    pass


def _get_mol(mol_or_smiles: "Mol | str") -> "Mol":
    """Convert SMILES to Mol if needed."""
    from rdkit import Chem

    if isinstance(mol_or_smiles, str):
        mol = Chem.MolFromSmiles(mol_or_smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {mol_or_smiles}")
        return mol
    return mol_or_smiles


def _prepare_mol_for_drawing(mol: "Mol") -> "Mol":
    """Prepare molecule for 2D drawing (add 2D coords if needed)."""
    from rdkit.Chem import AllChem

    # Work on a copy to avoid modifying the original
    mol = type(mol)(mol)  # Make a copy

    # Generate 2D coordinates if not present
    if mol.GetNumConformers() == 0:
        AllChem.Compute2DCoords(mol)
    else:
        # Check if existing conformer is 2D (all z=0) or 3D
        conf = mol.GetConformer()
        is_2d = all(abs(conf.GetAtomPosition(i).z) < 0.01 for i in range(mol.GetNumAtoms()))
        if not is_2d:
            # Has 3D coords, generate 2D for drawing
            AllChem.Compute2DCoords(mol)

    return mol


def _configure_drawer(drawer, options: RenderOptions) -> None:
    """Apply render options to drawer."""
    draw_opts = drawer.drawOptions()

    draw_opts.bondLineWidth = options.bond_line_width
    draw_opts.minFontSize = options.atom_label_font_size
    draw_opts.maxFontSize = options.atom_label_font_size
    draw_opts.addAtomIndices = options.add_atom_indices
    draw_opts.addStereoAnnotation = options.add_stereo_annotation

    if options.background_color:
        # Parse hex color to RGBA tuple
        hex_color = options.background_color.lstrip("#")
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        draw_opts.setBackgroundColour((r, g, b, 1.0))


def render_svg(
    mol_or_smiles: "Mol | str",
    options: RenderOptions | None = None,
) -> str:
    """
    Render molecule as SVG string.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        options: Rendering options

    Returns:
        SVG content as string
    """
    try:
        from rdkit.Chem.Draw import rdMolDraw2D

        mol = _get_mol(mol_or_smiles)
        mol = _prepare_mol_for_drawing(mol)

        if options is None:
            options = RenderOptions()

        drawer = rdMolDraw2D.MolDraw2DSVG(options.width, options.height)
        _configure_drawer(drawer, options)

        # Handle highlighting
        highlight_atoms = options.highlight_atoms or []
        highlight_bonds = options.highlight_bonds or []
        highlight_atom_colors = {}
        highlight_bond_colors = {}

        if options.highlight_color and (highlight_atoms or highlight_bonds):
            # Use tuple for color (RGB or RGBA)
            color = (*options.highlight_color, 1.0) if len(options.highlight_color) == 3 else options.highlight_color
            highlight_atom_colors = {i: color for i in highlight_atoms}
            highlight_bond_colors = {i: color for i in highlight_bonds}

        drawer.DrawMolecule(
            mol,
            highlightAtoms=highlight_atoms,
            highlightBonds=highlight_bonds,
            highlightAtomColors=highlight_atom_colors if highlight_atom_colors else {},
            highlightBondColors=highlight_bond_colors if highlight_bond_colors else {},
        )
        drawer.FinishDrawing()

        return drawer.GetDrawingText()

    except ValueError:
        raise
    except Exception as e:
        raise RenderError(f"Failed to render SVG: {e}") from e


def render_png(
    mol_or_smiles: "Mol | str",
    options: RenderOptions | None = None,
) -> bytes:
    """
    Render molecule as PNG bytes.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        options: Rendering options

    Returns:
        PNG image as bytes
    """
    try:
        from rdkit.Chem.Draw import rdMolDraw2D

        mol = _get_mol(mol_or_smiles)
        mol = _prepare_mol_for_drawing(mol)

        if options is None:
            options = RenderOptions()

        drawer = rdMolDraw2D.MolDraw2DCairo(options.width, options.height)
        _configure_drawer(drawer, options)

        # Handle highlighting
        highlight_atoms = options.highlight_atoms or []
        highlight_bonds = options.highlight_bonds or []
        highlight_atom_colors = {}
        highlight_bond_colors = {}

        if options.highlight_color and (highlight_atoms or highlight_bonds):
            # Use tuple for color (RGB or RGBA)
            color = (*options.highlight_color, 1.0) if len(options.highlight_color) == 3 else options.highlight_color
            highlight_atom_colors = {i: color for i in highlight_atoms}
            highlight_bond_colors = {i: color for i in highlight_bonds}

        drawer.DrawMolecule(
            mol,
            highlightAtoms=highlight_atoms,
            highlightBonds=highlight_bonds,
            highlightAtomColors=highlight_atom_colors if highlight_atom_colors else {},
            highlightBondColors=highlight_bond_colors if highlight_bond_colors else {},
        )
        drawer.FinishDrawing()

        return drawer.GetDrawingText()

    except ValueError:
        raise
    except Exception as e:
        raise RenderError(f"Failed to render PNG: {e}") from e


def render_molecule(
    mol_or_smiles: "Mol | str",
    format: ImageFormat = ImageFormat.SVG,
    options: RenderOptions | None = None,
) -> str | bytes:
    """
    Render molecule in specified format.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        format: Output format (SVG or PNG)
        options: Rendering options

    Returns:
        SVG string or PNG bytes depending on format
    """
    if format == ImageFormat.SVG:
        return render_svg(mol_or_smiles, options)
    elif format == ImageFormat.PNG:
        return render_png(mol_or_smiles, options)
    else:
        raise ValueError(f"Unknown image format: {format}")


def render_molecules_grid(
    molecules: list["Mol | str"],
    mols_per_row: int = 4,
    sub_img_size: tuple[int, int] = (200, 200),
    legends: list[str] | None = None,
    format: ImageFormat = ImageFormat.SVG,
) -> str | bytes:
    """
    Render multiple molecules in a grid layout.

    Args:
        molecules: List of RDKit Mol objects or SMILES strings
        mols_per_row: Number of molecules per row
        sub_img_size: Size of each molecule image (width, height)
        legends: Optional labels for each molecule
        format: Output format (SVG or PNG)

    Returns:
        SVG string or PNG bytes
    """
    try:
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D

        mols = []
        for m in molecules:
            mol = _get_mol(m)
            mol = _prepare_mol_for_drawing(mol)
            mols.append(mol)

        if legends is None:
            legends = [""] * len(mols)

        # Calculate grid size
        n_rows = (len(mols) + mols_per_row - 1) // mols_per_row
        grid_width = mols_per_row * sub_img_size[0]
        grid_height = n_rows * sub_img_size[1]

        if format == ImageFormat.SVG:
            drawer = rdMolDraw2D.MolDraw2DSVG(grid_width, grid_height, *sub_img_size)
        else:
            drawer = rdMolDraw2D.MolDraw2DCairo(grid_width, grid_height, *sub_img_size)

        drawer.DrawMolecules(mols, legends=legends)
        drawer.FinishDrawing()

        return drawer.GetDrawingText()

    except ValueError:
        raise
    except Exception as e:
        raise RenderError(f"Failed to render molecule grid: {e}") from e


def render_reaction(
    reaction_smarts: str,
    options: RenderOptions | None = None,
) -> str:
    """
    Render a reaction from SMARTS notation as SVG.

    Args:
        reaction_smarts: Reaction SMARTS string
        options: Rendering options

    Returns:
        SVG string
    """
    try:
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D

        rxn = AllChem.ReactionFromSmarts(reaction_smarts)
        if rxn is None:
            raise ValueError(f"Invalid reaction SMARTS: {reaction_smarts}")

        if options is None:
            options = RenderOptions(width=600, height=200)

        drawer = rdMolDraw2D.MolDraw2DSVG(options.width, options.height)
        drawer.DrawReaction(rxn)
        drawer.FinishDrawing()

        return drawer.GetDrawingText()

    except ValueError:
        raise
    except Exception as e:
        raise RenderError(f"Failed to render reaction: {e}") from e


def mol_to_data_url(
    mol_or_smiles: "Mol | str",
    format: ImageFormat = ImageFormat.PNG,
    options: RenderOptions | None = None,
) -> str:
    """
    Render molecule and return as data URL for embedding in HTML/Markdown.

    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        format: Output format
        options: Rendering options

    Returns:
        Data URL string (e.g., "data:image/png;base64,...")
    """
    import base64

    if format == ImageFormat.SVG:
        svg = render_svg(mol_or_smiles, options)
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"
    else:
        png = render_png(mol_or_smiles, options)
        encoded = base64.b64encode(png).decode("ascii")
        return f"data:image/png;base64,{encoded}"
