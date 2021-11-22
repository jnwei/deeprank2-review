from time import time
import logging

import numpy
import torch
from pdb2sql import pdb2sql, interface as get_interface

from deeprank_gnn.models.structure import Atom, Residue, Chain, Structure, AtomicElement
from deeprank_gnn.domain.amino_acid import amino_acids
from deeprank_gnn.models.pair import Pair


_log = logging.getLogger(__name__)


def _add_atom_to_residue(atom, residue):

    for other_atom in residue.atoms:
        if other_atom.name == atom.name:
            # Don't allow two atoms with the same name, pick the highest occupancy
            if other_atom.occupancy < atom.occupancy:
                other_atom.change_altloc(atom)
                return

    # not there yet, add it
    residue.add_atom(atom)


def get_structure(pdb, id_):
    """ Builds a structure from rows in a pdb file
        Args:
            pdb (pdb2sql object): the pdb structure that we're investigating
            id (str): unique id for the pdb structure
        Returns (Structure): the structure object, giving access to chains, residues, atoms
    """

    amino_acids_by_code = {amino_acid.three_letter_code: amino_acid for amino_acid in amino_acids}
    elements_by_name = {element.name: element for element in AtomicElement}

    # We need these intermediary dicts to keep track of which residues and chains have already been created.
    chains = {}
    residues = {}

    structure = Structure(id_)

    # Iterate over the atom output from pdb2sql
    for row in pdb.get("x,y,z,rowID,name,altLoc,occ,element,chainID,resSeq,resName,iCode", model=0):

        x, y, z, atom_number, atom_name, altloc, occupancy, element, chain_id, residue_number, residue_name, insertion_code = row

        # Make sure not to take the same atom twice.
        if altloc is not None and altloc != "" and altloc != "A":
            continue

        # We use None to indicate that the residue has no insertion code.
        if insertion_code == "":
            insertion_code = None

        # The amino acid is only valid when we deal with protein residues.
        if residue_name in amino_acids_by_code:
            amino_acid = amino_acids_by_code[residue_name]
        else:
            amino_acid = None

        # Turn the x,y,z into a vector:
        atom_position = numpy.array([x, y, z])

        # Init chain.
        if chain_id not in chains:

            chain = Chain(structure, chain_id)
            chains[chain_id] = chain
            structure.add_chain(chain)
        else:
            chain = chains[chain_id]

        # Init residue.
        residue_id = (chain_id, residue_number, insertion_code)
        if residue_id not in residues:

            residue = Residue(chain, residue_number, amino_acid, insertion_code)
            residues[residue_id] = residue
            chain.add_residue(residue)
        else:
            residue = residues[residue_id]

        # Init atom.
        atom = Atom(residue, atom_name, elements_by_name[element], atom_position, occupancy)
        _add_atom_to_residue(atom, residue)

    return structure


def _get_shortest_distance(residue1, residue2, atomic_distance_table):

    shortest_distance = 1e99
    for atom1 in residue1.atoms:
        for atom2 in residue2.atoms:
            distance = atomic_distance_table[atom1, atom2]
            if distance < shortest_distance:
                shortest_distance = distance

    return shortest_distance


def get_residue_contact_pairs(environment, pdb_ac, chain_id1, chain_id2, distance_cutoff):

    # load the structure
    pdb_path = environment.get_pdb_path(pdb_ac)

    pdb = pdb2sql(pdb_path)
    try:
        structure = get_structure(pdb, pdb_ac)
    finally:
        pdb._close()

    # Find out which residues are pairs
    interface = get_interface(pdb_path)
    try:
        contact_residues = interface.get_contact_residues(cutoff=distance_cutoff,
                                                          chain1=chain_id1, chain2=chain_id2,
                                                          return_contact_pairs=True)
    finally:
        interface._close()

    # Map to residue objects
    residue_pairs = set([])
    for residue_key1 in contact_residues:
        residue_chain_id1, residue_number1, residue_name1 = residue_key1

        chain1 = structure.get_chain(residue_chain_id1)

        residue1 = None
        for residue in chain1.residues:
            if residue.number == residue_number1 and residue.amino_acid is not None and residue.amino_acid.three_letter_code == residue_name1:
                residue1 = residue
                break
        else:
            raise ValueError("Not found: {} {} {} {}".format(pdb_ac, residue_chain_id1, residue_number1, residue_name1))

        for residue_chain_id2, residue_number2, residue_name2 in contact_residues[residue_key1]:

            chain2 = structure.get_chain(residue_chain_id2)

            residue2 = None
            for residue in chain2.residues:
                if residue.number == residue_number2 and residue.amino_acid is not None and residue.amino_acid.three_letter_code == residue_name2:
                    residue2 = residue
                    break
            else:
                raise ValueError("Not found: {} {} {} {}".format(pdb_ac, residue_chain_id2, residue_number2, residue_name2))

            residue_pairs.add(Pair(residue1, residue2))

    return residue_pairs
