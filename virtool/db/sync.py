"""
Synchronous helper functions for working with the database using pymongo. These are used in the jobs where asyncio is
not used.

"""
import json
from copy import deepcopy
from typing import Union

import dictdiffer
import pymongo

import virtool.history.utils
import virtool.otus.utils
import virtool.samples.utils


def get_active_index_ids(db, ref_id):
    """
    Get a list of the active index ids for the reference defined by the given `ref_id`.

    :param db: the application database object
    :type db: :class:`~pymongo.database.Database`

    :param ref_id: the id of the reference to list active index ids for
    :type ref_id: str

    :return: the ids of the active indexes for the reference
    :rtype: list

    """
    pipeline = [
        {
            "$match": {
                "ready": False,
                "reference.id": ref_id
            }
        },
        {
            "$group": {
                "_id": "$index.id"
            }
        }
    ]

    active_indexes = [a["_id"] for a in db.analyses.aggregate(pipeline)]

    active_indexes = set(active_indexes)

    current_index_id, _ = get_current_index_id_and_version(db, ref_id)

    active_indexes.add(current_index_id)

    unready_index = db.indexes.find_one({"ready": False})

    if unready_index:
        active_indexes.add(unready_index["_id"])

    try:
        active_indexes.remove("unbuilt")
    except KeyError:
        pass

    return list(active_indexes)


def get_current_index_id_and_version(db, ref_id):
    """
    Return the current index id and version number.

    :param db: the application database object
    :type db: :class:`~pymongo.database.Database`

    :param ref_id: the id of the reference to get the current index for
    :type ref_id: str

    :return: the index and version of the current index
    :rtype: Tuple[str, int]

    """
    document = db.indexes.find_one(
        {"reference.id": ref_id, "ready": True},
        sort=[("version", pymongo.DESCENDING)],
        projection=["_id", "version"]
    )

    if document is None:
        return None, -1

    return document["_id"], document["version"]


def join_otu(db, query, document=None):
    """
    Join the OTU specified by `query` and its sequences.

    :param db: the application database object
    :type db: :class:`~pymongo.database.Database`

    :param query: the id of the otu to join or a Mongo query.
    :type query: Union[dict,str]

    :param document: use this otu document as a basis for the join instead finding it using the otu id.
    :type document: dict

    :return: the joined otu document
    :rtype: dict
    """
    # Get the otu entry if a ``document`` parameter was not passed.
    document = document or db.otus.find_one(query)

    if document is None:
        return None

    sequences = list(db.sequences.find({"otu_id": document["_id"]}))

    # Merge the sequence entries into the otu entry.
    return virtool.otus.utils.merge_otu(document, sequences)


def patch_otu_to_version(db, settings: dict, otu_id: str, version: Union[str, int]) -> tuple:
    """
    Take a joined otu back in time to the passed ``version``. Uses the diffs in the change documents associated with
    the otu.

    :param db: the application database object
    :param settings: the application settings
    :param otu_id: the id of the otu to patch
    :param version: the version to patch to
    :return: the current joined otu, patched otu, and the ids of changes reverted in the process

    """
    # A list of history_ids reverted to produce the patched entry.
    reverted_history_ids = list()

    current = join_otu(db, otu_id) or dict()

    if "version" in current and current["version"] == version:
        return current, deepcopy(current), reverted_history_ids

    patched = deepcopy(current)

    # Sort the changes by descending timestamp.
    for change in db.history.find({"otu.id": otu_id}, sort=[("otu.version", -1)]):
        if change["otu"]["version"] == "removed" or change["otu"]["version"] > version:
            reverted_history_ids.append(change["_id"])

            if change["diff"] == "file":
                change["diff"] = read_diff_file(
                    settings["data_path"],
                    otu_id,
                    change["otu"]["version"]
                )

            if change["method_name"] == "remove":
                patched = change["diff"]

            elif change["method_name"] == "create":
                patched = None

            else:
                diff = dictdiffer.swap(change["diff"])
                patched = dictdiffer.patch(diff, patched)
        else:
            break

    if current == {}:
        current = None

    return current, patched, reverted_history_ids


def read_diff_file(data_path: str, otu_id: str, otu_version: Union[int, str]) -> dict:
    """
    Read a history diff file from disk.

    :param data_path: the application data path
    :param otu_id: the change's OTU ID
    :param otu_version: the change's OTU version
    :return: the diff

    """
    path = virtool.history.utils.join_diff_path(
        data_path,
        otu_id,
        otu_version
    )

    with open(path, "r") as f:
        return json.load(f, object_hook=virtool.history.utils.json_object_hook)


def recalculate_workflow_tags(db, sample_id: str):
    """
    Recalculate and apply workflow tags (eg. "ip", True) for a given sample.

    :param db: the application database client
    :param sample_id: the id of the sample to recalculate tags for

    """
    analyses = db.analyses.find({"sample.id": sample_id}, ["ready", "workflow"])

    update = virtool.samples.utils.calculate_workflow_tags(analyses)

    db.samples.update_one({"_id": sample_id}, {
        "$set": update
    })
