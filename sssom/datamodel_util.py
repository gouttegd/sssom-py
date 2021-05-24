"""
Converts sssom meta tsv to linkml
"""

from sssom.sssom_document import MappingSetDocument
import yaml
from dataclasses import dataclass, field
from typing import Optional, Set, List, Union, Dict, Any
import pandas as pd
from sssom.sssom_datamodel import Entity, slots
import logging
from io import StringIO
from .sssom_document import MappingSetDocument


@dataclass
class MappingSetDataFrame:
    """
    A collection of mappings represented as a DataFrame, together with additional metadata
    """

    df: pd.DataFrame = None  ## Mappings
    prefixmap: Dict[str, str] = None  ## maps CURIE prefixes to URI bases
    metadata: Optional[Dict[str, str]] = None  ## header metadata excluding prefixes


@dataclass
class EntityPair:
    """
    A tuple of entities.

    Note that (e1,e2) == (e2,e1)
    """
    subject_entity: Entity
    object_entity: Entity

    def __hash__(self):
        if self.subject_entity.id <= self.object_entity.id:
            t = self.subject_entity.id, self.object_entity.id
        else:
            t = self.object_entity.id, self.subject_entity.id
        return hash(t)


@dataclass
class MappingSetDiff:
    """
    represents a difference between two mapping sets

    Currently this is limited to diffs at the level of entity-pairs.
    For example, if file1 has A owl:equivalentClass B, and file2 has A skos:closeMatch B,
    this is considered a mapping in common.
    """
    unique_tuples1: Optional[Set[str]] = None
    unique_tuples2: Optional[Set[str]] = None
    common_tuples: Optional[Set[str]] = None

    combined_dataframe: Optional[pd.DataFrame] = None
    """
    Dataframe that combines with left and right dataframes with information injected into
    the comment column
    """


@dataclass
class MetaTSVConverter:
    """
    converts SSSOM/sssom_metadata.tsv
    DO NOT USE, NOW DEPRECATED!
    """

    df: Optional[pd.DataFrame] = None

    def load(self, filename) -> None:
        """
        loads from folder
        :return:
        """
        #self.df = pd.read_csv(filename, sep="\t", comment="#").fillna("")
        self.df = read_pandas(filename)


    def convert(self) -> Dict[str, Any]:
        # note that 'mapping' is both a metaproperty and a property of this model...
        slots = {
            'mappings': {
                'description': 'Contains a list of mapping objects',
                'range': 'mapping',
                'multivalued': True
            },
            'id': {
                'description': 'CURIE or IRI identifier',
                'identifier': True
            }
        }
        classes = {
            'mapping set': {
                'description': 'Represents a set of mappings',
                'slots': ['mappings']
            },
            'mapping': {
                'description': 'Represents an individual mapping between a pair of entities',
                'slots': [],
                'class_uri': 'owl:Axiom'
            },
            'entity': {
                'description': 'Represents any entity that can be mapped, such as an OWL class or SKOS concept',
                'mappings': [
                    'rdf:Resource'
                ],
                'slots': ['id']
            }
        }
        obj = {
            'id': 'http://w3id.org/sssom',
            'description': 'Datamodel for Simple Standard for Sharing Ontology Mappings (SSSOM)',
            'imports': [
                'linkml:types'
            ],
            'prefixes': {
                'linkml': 'https://w3id.org/linkml/',
                'sssom': 'http://w3id.org/sssom/',

            },
            'see_also': ['https://github.com/OBOFoundry/SSSOM'],
            'default_curi_maps': ['semweb_context'],
            'default_prefix': 'sssom',
            'slots': slots,
            'classes': classes
        }
        for _, row in self.df.iterrows():
            id = row['Element ID']
            if id == 'ID':
                continue
            id = id.replace("sssom:", "")
            dt = row['Datatype']
            if dt == 'xsd:double':
                dt = 'double'
            elif id.endswith('_id') or id.endswith('match_field'):
                dt = 'entity'
            else:
                dt = 'string'

            slot = {
                'description': row['Description']
            }
            ep = row['Equivalent property']
            if ep != "":
                slot['mappings'] = [ep]
            if row['Required'] == 1:
                slot['required'] = True

            slot['range'] = dt
            slots[id] = slot
            slot_uri = None
            if id == 'subject_id':
                slot_uri = 'owl:annotatedSource'
            elif id == 'object_id':
                slot_uri = 'owl:annotatedTarget'
            elif id == 'predicate_id':
                slot_uri = 'owl:annotatedProperty'
            if slot_uri is not None:
                slot['slot_uri'] = slot_uri
            scope = row['Scope']
            if 'G' in scope:
                classes['mapping set']['slots'].append(id)
            if 'L' in scope:
                classes['mapping']['slots'].append(id)
        return obj

    def convert_and_save(self, fn: str) -> None:
        obj = self.convert()
        with open(fn, 'w') as stream:
            yaml.safe_dump(obj, stream, sort_keys=False)


@dataclass
class MappingSetDataFrame:
    """
    A collection of mappings represented as a DataFrame, together with additional metadata
    """
    df: pd.DataFrame = None  ## Mappings
    prefixmap: Dict[str, str] = None  ## maps CURIE prefixes to URI bases
    metadata: Optional[Dict[str, str]] = None  ## header metadata excluding prefixes


def get_file_extension(filename: str) -> str:
    parts = filename.split(".")
    if len(parts) > 0:
        f_format = parts[-1]
        return f_format
    else:
        raise Exception(f'Cannot guess format from {filename}')


def read_csv(filename, comment='#', sep=','):
    with open(filename, 'rb') as f:
        lines = "".join([line for line in f
                        if not line.startswith(comment)])
    return pd.read_csv(StringIO(lines), sep=sep)


def read_metadata(filename):
    """
    Reading metadata file (yaml) that is supplied separately from a tsv
    :param filename: location of file
    :return: two objects, a metadata and a curie_map object
    """
    meta = {}
    curie_map = {}
    with open(filename, 'r') as stream:
        try:
            m = yaml.safe_load(stream)
            if "curie_map" in m:
                curie_map = m['curie_map']
            m.pop('curie_map', None)
            meta = m
        except yaml.YAMLError as exc:
            print(exc)
    return meta, curie_map


def read_pandas(filename: str, sep='\t') -> pd.DataFrame:
    """
    wrapper to pd.read_csv that handles comment lines correctly
    :param filename:
    :param sep: File separator in pandas (\t or ,)
    :return:
    """
    if not sep:
        extension = get_file_extension(filename)
        sep = "\t"
        if extension == "tsv":
            sep = "\t"
        elif extension == "csv":
            sep = ","
        else:
            logging.warning(f"Cannot automatically determine table format, trying tsv.")

    # from tempfile import NamedTemporaryFile
    # with NamedTemporaryFile("r+") as tmp:
    #    with open(filename, "r") as f:
    #        for line in f:
    #            if not line.startswith('#'):
    #                tmp.write(line + "\n")
    #    tmp.seek(0)
    return read_csv(filename, comment='#', sep=sep).fillna("")


def extract_global_metadata(msdoc: MappingSetDocument):
    meta = {'curie_map': msdoc.curie_map}
    ms_meta = msdoc.mapping_set
    for key in [slot for slot in dir(slots) if not callable(getattr(slots, slot)) and not slot.startswith("__")]:
        slot = getattr(slots, key).name
        if slot not in ["mappings"] and slot in ms_meta:
            if ms_meta[slot]:
                meta[key] = ms_meta[slot]
    return meta


def to_mapping_set_dataframe(doc: MappingSetDocument) -> MappingSetDataFrame:
    ###
    # convert MappingSetDocument into MappingSetDataFrame
    ###
    data = []
    for mapping in doc.mapping_set.mappings:
        mdict = mapping.__dict__
        m = {}
        for key in mdict:
            if mdict[key]:
                m[key] = mdict[key]
        data.append(m)
    df = pd.DataFrame(data=data)
    meta = extract_global_metadata(doc)
    msdf = MappingSetDataFrame(df=df, prefixmap=doc.curie_map, metadata=meta)
    return msdf

# to_mapping_set_document is in parser.py in order to avoid circular import errors
