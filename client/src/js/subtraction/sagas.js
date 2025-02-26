import { push } from "connected-react-router";
import { put, takeLatest, throttle } from "redux-saga/effects";
import { pushState } from "../app/actions";
import {
    CREATE_SUBTRACTION,
    EDIT_SUBTRACTION,
    FIND_SUBTRACTIONS,
    GET_SUBTRACTION,
    SHORTLIST_SUBTRACTIONS,
    REMOVE_SUBTRACTION
} from "../app/actionTypes";
import { apiCall, pushFindTerm } from "../utils/sagas";
import * as subtractionAPI from "./api";

export function* findSubtractions(action) {
    yield apiCall(subtractionAPI.find, action, FIND_SUBTRACTIONS);
    yield pushFindTerm(action.term);
}

export function* getSubtraction(action) {
    yield apiCall(subtractionAPI.get, action, GET_SUBTRACTION);
}

export function* createSubtraction(action) {
    yield apiCall(subtractionAPI.create, action, CREATE_SUBTRACTION, {});
    yield put(pushState({ createSubtraction: false }));
}

export function* shortlistSubtractions(action) {
    yield apiCall(subtractionAPI.shortlist, action, SHORTLIST_SUBTRACTIONS);
}

export function* editSubtraction(action) {
    yield apiCall(subtractionAPI.edit, action, EDIT_SUBTRACTION);
    yield put(pushState({ editSubtraction: false }));
}

export function* removeSubtraction(action) {
    yield apiCall(subtractionAPI.remove, action, REMOVE_SUBTRACTION);
    yield put(push("/subtraction"));
}

export function* watchSubtraction() {
    yield throttle(500, CREATE_SUBTRACTION.REQUESTED, createSubtraction);
    yield takeLatest(FIND_SUBTRACTIONS.REQUESTED, findSubtractions);
    yield takeLatest(GET_SUBTRACTION.REQUESTED, getSubtraction);
    yield takeLatest(SHORTLIST_SUBTRACTIONS.REQUESTED, shortlistSubtractions);
    yield takeLatest(EDIT_SUBTRACTION.REQUESTED, editSubtraction);
    yield throttle(300, REMOVE_SUBTRACTION.REQUESTED, removeSubtraction);
}
