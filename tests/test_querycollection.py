from os.path import join
from shutil import rmtree
from tempfile import mkdtemp
from types import ModuleType
from typing import List, Union

import h5py
import pytest

from deeprankcore.domain import edgestorage as Efeat
from deeprankcore.domain import nodestorage as Nfeat
from deeprankcore.domain.aminoacidlist import alanine, phenylalanine
from deeprankcore.features import components, contact, surfacearea
from deeprankcore.query import (ProteinProteinInterfaceResidueQuery, Query,
                                QueryCollection,
                                SingleResidueVariantResidueQuery)
from deeprankcore.tools.target import compute_targets

def _querycollection_tester( # pylint: disable = too-many-locals, dangerous-default-value
    query_type: str,
    n_queries: int = 3,
    feature_modules: Union[ModuleType, List[ModuleType]] = [components, contact], 
    cpu_count: int = 1, 
    combine_output: bool = True,
):
    """
    Generic function to test QueryCollection class.

    Args:
        query_type (str): query type to be generated. It accepts only 'ppi' (ProteinProteinInterface) or 'var' (SingleResidueVariant).
            Defaults to 'ppi'.
        n_queries (int): number of queries to be generated.
        feature_modules: module or list of feature modules (from deeprankcore.features) to be passed to process.
            Defaults to components and contact, which are the defaults for `query.process` 
        cpu_count (int): number of cpus to be used during the queries processing.
        combine_output (bool): boolean for combining the hdf5 files generated by the processes.
            By default, the hdf5 files generated are combined into one, and then deleted.
    """

    if query_type == 'ppi':
        queries = [ProteinProteinInterfaceResidueQuery(
                        str("tests/data/pdb/3C8P/3C8P.pdb"),
                        "A",
                        "B",
                        pssm_paths={"A": "tests/data/pssm/3C8P/3C8P.A.pdb.pssm", "B": "tests/data/pssm/3C8P/3C8P.B.pdb.pssm"},
                    ) for _ in range(n_queries)]
    elif query_type == 'var':
        queries = [SingleResidueVariantResidueQuery(
                        str("tests/data/pdb/101M/101M.pdb"),
                        "A",
                        None, # placeholder
                        insertion_code= None,
                        wildtype_amino_acid= alanine,
                        variant_amino_acid= phenylalanine,
                        pssm_paths={"A": str("tests/data/pssm/101M/101M.A.pdb.pssm")},
                    ) for _ in range(n_queries)]
    else:
        raise ValueError("Please insert a valid type (either ppi or var).")

    output_directory = mkdtemp()
    prefix = join(output_directory, "test-process-queries")
    collection = QueryCollection()

    for idx in range(n_queries):
        if query_type == 'var':
            queries[idx]._residue_number = idx + 1 # pylint: disable=protected-access
            collection.add(queries[idx])
        else:
            collection.add(queries[idx], warn_duplicate=False)

    output_paths = collection.process(prefix, feature_modules, cpu_count, combine_output)
    assert len(output_paths) > 0

    graph_names = []
    for path in output_paths:
        with h5py.File(path, "r") as f5:
            graph_names += list(f5.keys())

    for query in collection.queries:
        query_id = query.get_query_id()
        assert query_id in graph_names, f"missing in output: {query_id}"

    return collection, output_directory, output_paths


def _assert_correct_modules(output_paths: str, features: Union[str, List[str]], absent: str):
    """Helper function to assert inclusion of correct features

    Args:
        output_paths (str): output_paths as returned from _querycollection_tester
        features (Union[str, List[str]]): feature(s) that should be present
        absent (str): feature that should be absent
    """
    
    if isinstance(features,str):
        features = [features]

    with h5py.File(output_paths[0], "r") as f5:
        missing = []
        for feat in features:
            try:
                if feat == Efeat.DISTANCE:
                    _ = f5[list(f5.keys())[0]][f"{Efeat.EDGE}/{feat}"]
                else:
                    _ = f5[list(f5.keys())[0]][f"{Nfeat.NODE}/{feat}"]
            except KeyError:
                missing.append(feat)
            if missing:
                raise KeyError(f'The following feature(s) were not created: {missing}.')
        
        with pytest.raises(KeyError):
            _ = f5[list(f5.keys())[0]][f"{Nfeat.NODE}/{absent}"]


def test_querycollection_process():
    """
    Tests processing method of QueryCollection class.
    """

    for query_type in ['ppi', 'var']:
        n_queries = 3
        n_queries = 3

        collection, output_directory, _ = _querycollection_tester(query_type, n_queries=n_queries)
        
        assert isinstance(collection.queries, list)
        assert len(collection.queries) == n_queries
        for query in collection.queries:
            assert issubclass(type(query), Query)

        rmtree(output_directory)


def test_querycollection_process_single_feature_module():
    """
    Tests processing for generating from a single feature module for following input types: ModuleType, List[ModuleType] str, List[str]
    """

    for query_type in ['ppi', 'var']:
        for testcase in [surfacearea, [surfacearea], 'surfacearea', ['surfacearea']]:
            _, output_directory, output_paths = _querycollection_tester(query_type, feature_modules=testcase)
            _assert_correct_modules(output_paths, Nfeat.BSA, Nfeat.HSE)
            rmtree(output_directory)


def test_querycollection_process_all_features_modules():
    """
    Tests processing for generating all features.
    """

    one_feature_from_each_module = [Nfeat.RESTYPE, Nfeat.PSSM, Efeat.DISTANCE, Nfeat.HSE, Nfeat.SECSTRUCT, Nfeat.BSA, Nfeat.IRCTOTAL]        

    _, output_directory, output_paths = _querycollection_tester('ppi', feature_modules='all')
    _assert_correct_modules(output_paths, one_feature_from_each_module, 'dummy_feature')
    rmtree(output_directory)
    
    _, output_directory, output_paths = _querycollection_tester('var', feature_modules='all')
    _assert_correct_modules(output_paths, one_feature_from_each_module[:-1], Nfeat.IRCTOTAL)
    rmtree(output_directory)
    

def test_querycollection_process_default_features_modules():
    """
    Tests processing for generating all features.
    """

    for query_type in ['ppi', 'var']:

        _, output_directory, output_paths = _querycollection_tester(query_type)
        _assert_correct_modules(output_paths, [Nfeat.RESTYPE, Efeat.DISTANCE], Nfeat.HSE)
        rmtree(output_directory)


def test_querycollection_process_combine_output_true():
    """
    Tests processing for combining hdf5 files into one.
    """

    for query_type in ['ppi', 'var']:
        modules = [surfacearea, components]

        _, output_directory_t, output_paths_t = _querycollection_tester(query_type, feature_modules=modules)

        _, output_directory_f, output_paths_f = _querycollection_tester(query_type, feature_modules=modules, combine_output = False, cpu_count=2)

        assert len(output_paths_t) == 1

        keys_t = {}
        with h5py.File(output_paths_t[0],'r') as file_t:
            for key, value in file_t.items():
                keys_t[key] = value

        keys_f = {}
        for output_path in output_paths_f:
            with h5py.File(output_path,'r') as file_f:
                for key, value in file_f.items():
                    keys_f[key] = value

        assert keys_t == keys_f

        rmtree(output_directory_t)
        rmtree(output_directory_f)


def test_querycollection_process_combine_output_false():
    """
    Tests processing for keeping all generated hdf5 files .
    """

    for query_type in ['ppi', 'var']:

        cpu_count = 2
        combine_output = False
        modules = [surfacearea, components]

        _, output_directory, output_paths = _querycollection_tester(query_type, feature_modules=modules, 
                                                                    cpu_count = cpu_count, combine_output = combine_output)

        assert len(output_paths) == cpu_count

        rmtree(output_directory)


def test_querycollection_duplicates_add():
    """
    Tests add method of QueryCollection class.
    """
    ref_path = "tests/data/ref/1ATN/1ATN.pdb"
    pssm_path1 = "tests/data/pssm/1ATN/1ATN.A.pdb.pssm"
    pssm_path2 = "tests/data/pssm/1ATN/1ATN.B.pdb.pssm"
    chain_id1 = "A"
    chain_id2 = "B"
    pdb_paths = [
        "tests/data/pdb/1ATN/1ATN_1w.pdb",
        "tests/data/pdb/1ATN/1ATN_1w.pdb",
        "tests/data/pdb/1ATN/1ATN_1w.pdb",
        "tests/data/pdb/1ATN/1ATN_2w.pdb",
        "tests/data/pdb/1ATN/1ATN_2w.pdb",
        "tests/data/pdb/1ATN/1ATN_3w.pdb"]

    queries = QueryCollection()

    for pdb_path in pdb_paths:
        # Append data points
        targets = compute_targets(pdb_path, ref_path)
        queries.add(ProteinProteinInterfaceResidueQuery(
            pdb_path = pdb_path,
            chain_id1 = chain_id1,
            chain_id2 = chain_id2,
            targets = targets,
            pssm_paths = {
                chain_id1: pssm_path1,
                chain_id2: pssm_path2
            }
        ))
        
    #check id naming for all pdb files
    model_ids = []
    for query in queries.queries:
        model_ids.append(query.model_id)
    model_ids.sort()
    
    assert model_ids == ['1ATN_1w', '1ATN_1w_2', '1ATN_1w_3', '1ATN_2w', '1ATN_2w_2', '1ATN_3w']
    assert queries.ids_count['residue-ppi:A-B:1ATN_1w'] == 3
    assert queries.ids_count['residue-ppi:A-B:1ATN_2w'] == 2
    assert queries.ids_count['residue-ppi:A-B:1ATN_3w'] == 1