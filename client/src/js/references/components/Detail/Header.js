import { endsWith } from "lodash-es";
import React from "react";
import { connect } from "react-redux";
import { pushState } from "../../../app/actions";
import { Icon, ViewHeader, ViewHeaderAttribution, ViewHeaderIcons, ViewHeaderTitle } from "../../../base";
import { checkReferenceRight } from "../../selectors";

export const ReferenceDetailHeaderIcon = ({ canModify, isRemote, onEdit }) => {
    if (isRemote) {
        return <Icon color="grey" name="lock" />;
    }

    if (canModify) {
        return <Icon color="orange" name="pencil-alt" tip="Edit" onClick={onEdit} />;
    }

    return null;
};

export const ReferenceDetailHeader = ({
    canModify,
    createdAt,
    isRemote,
    name,
    showIcons,
    userId,
    onEdit,
    onExport
}) => {
    let icons;

    if (showIcons) {
        icons = (
            <ViewHeaderIcons>
                <ReferenceDetailHeaderIcon canModify={canModify} isRemote={isRemote} onEdit={onEdit} />
                <Icon color="purple" name="download" onClick={onExport} />
            </ViewHeaderIcons>
        );
    }

    return (
        <ViewHeader title={name}>
            <ViewHeaderTitle>
                {name}
                {icons}
            </ViewHeaderTitle>
            <ViewHeaderAttribution time={createdAt} user={userId} />
        </ViewHeader>
    );
};

export const mapStateToProps = state => {
    const { name, remotes_from, created_at, user } = state.references.detail;
    return {
        name,
        canModify: checkReferenceRight(state, "modify"),
        createdAt: created_at,
        isRemote: !!remotes_from,
        showIcons: endsWith(state.router.location.pathname, "/manage"),
        userId: user.id
    };
};

export const mapDispatchToProps = dispatch => ({
    onEdit: () => {
        dispatch(pushState({ editReference: true }));
    },

    onExport: () => {
        dispatch(pushState({ exportReference: true }));
    }
});

export default connect(mapStateToProps, mapDispatchToProps)(ReferenceDetailHeader);
