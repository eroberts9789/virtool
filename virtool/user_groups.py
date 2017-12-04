import pymongo

import virtool.user
import virtool.user_permissions
import virtool.utils


def processor(document):
    return virtool.utils.base_processor(document)


def merge_group_permissions(groups):
    """
    Return a :class:`dict` of permissions that will be inherited by a user belonging to all the passed ``groups``.

    :param groups: a list of group documents.
    :return: a dict keyed by permission names with boolean values indicating the state of the permission

    """
    permission_dict = {permission_name: False for permission_name in virtool.user_permissions.PERMISSIONS}

    for permission_name in virtool.user_permissions.PERMISSIONS:
        for group in groups:
            try:
                if group["permissions"][permission_name]:
                    permission_dict[permission_name] = True
            except KeyError:
                permission_dict[permission_name] = False

    return permission_dict


async def update_member_users(db, group_id, remove=False):
    groups = await db.groups.find().to_list(None)

    async for user in db.users.find({"groups": group_id}, ["groups", "permissions", "primary_group"]):
        if remove:
            user["groups"].remove(group_id)

        new_permissions = merge_group_permissions([group for group in groups if group["_id"] in user["groups"]])

        # Skip updating this user if their group membership and permissions haven't changed.
        if not remove and new_permissions == user["permissions"]:
            continue

        update_dict = {
            "$set": {
                "permissions": new_permissions
            }
        }

        if user["primary_group"] == group_id:
            update_dict["$set"]["primary_group"] = ""

        if remove:
            update_dict["$pull"] = {
                "groups": group_id
            }

        document = await db.users.find_one_and_update(
            {"_id": user["_id"]},
            update_dict,
            return_document=pymongo.ReturnDocument.AFTER,
            projection=["groups", "permissions"]
        )

        await virtool.user.update_sessions_and_keys(db, user["_id"], document["groups"], document["permissions"])