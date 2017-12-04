import { WS_CLOSED } from "./actionTypes";
import { wsUpdateFile, wsRemoveFile } from "./files/actions";
import { wsUpdateJob, wsRemoveJob } from "./jobs/actions";
import { wsUpdateSample, wsRemoveSample, wsUpdateAnalysis, wsRemoveAnalysis } from "./samples/actions";
import { wsUpdateStatus } from "./status/actions";


const documentUpdaters = {
    analyses: wsUpdateAnalysis,
    files: wsUpdateFile,
    jobs: wsUpdateJob,
    samples: wsUpdateSample,
    status: wsUpdateStatus
};

const documentRemovers = {
    analyses: wsRemoveAnalysis,
    files: wsRemoveFile,
    jobs: wsRemoveJob,
    samples: wsRemoveSample
};

export default function WSConnection (dispatch) {

    // The Redux store's dispatch method.
    this.dispatch = dispatch;

    // When a websocket message is received, this method is called with the message as the sole argument. Every message
    // has a property "operation" that tells the dispatcher what to do. Illegal operation names will throw an error.
    this.handle = (message) => {
        const iface = message.interface;
        const operation = message.operation;

        window.console.log(`${iface}.${operation}`);

        if (operation === "update" && documentUpdaters.hasOwnProperty(iface)) {
            return dispatch(documentUpdaters[iface](message.data))
        }

        if (operation === "remove" && documentRemovers.hasOwnProperty(iface)) {
            return dispatch(documentRemovers[iface](message.data))
        }
    };

    this.establishConnection = () => {

        const protocol = window.location.protocol === "https:" ? "wss" : "ws";

        this.connection = new window.WebSocket(`${protocol}://${window.location.host}/ws`);

        this.connection.onmessage = (event) => {
            this.handle(JSON.parse(event.data));
        };

        this.connection.onclose = () => {
            this.dispatch({
                type: WS_CLOSED
            });
        };
    };
}