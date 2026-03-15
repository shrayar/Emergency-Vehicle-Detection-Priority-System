// controllers/rsuController.js
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.join(__dirname, '..', 'logs', 'rsu_messages.log');

// simple append-json-line logger
function logEvent(obj) {
    const line = JSON.stringify({ ts: new Date().toISOString(), ...obj }) + '\n';
    fs.appendFileSync(LOG_FILE, line);
}

// Basic decision logic (placeholder).
// Later you will replace this to call TraCI or another service to actually change SUMO lights.
async function handleEvRequest(evMsg, io) {
    // Validate minimal fields
    if (!evMsg || !evMsg.ev_id || !evMsg.eta_seconds) {
        const err = { error: 'invalid_ev_message', details: evMsg };
        logEvent({ type: 'INVALID_EV_MSG', payload: err });
        throw new Error('Invalid EV message');
    }

    // Log incoming EV request
    logEvent({ type: 'EV_PRIORITY_REQ_RECEIVED', ev: evMsg });

    // Simple rule: if ETA < 15s, extend green by 10s; else if < 40s extend by 5s; else acknowledge
    const eta = Number(evMsg.eta_seconds);
    let action = { type: 'RSU_RESPONSE', tls_id: evMsg.next_tls || null, action: 'ack', duration: 0, reason: '' };

    if (eta <= 15) {
        action.action = 'extend_green';
        action.duration = 10;
        action.reason = 'EV arriving soon';
    } else if (eta <= 40) {
        action.action = 'extend_green';
        action.duration = 5;
        action.reason = 'EV expected';
    } else {
        action.action = 'ack';
        action.duration = 0;
        action.reason = 'ETA too large';
    }

    action.timestamp = new Date().toISOString();

    // Log decision
    logEvent({ type: 'RSU_DECISION', ev_id: evMsg.ev_id, decision: action });

    // Broadcast the EV request and RSU decision to all connected dashboards/clients
    io.emit('ev_event', evMsg);
    io.emit('rsu_decision', action);

    // Future integration point:
    // - Here you will call TraCI or a bridge to apply the action on SUMO (e.g., extend phase)
    // - Save command to a command-queue file or push to a local API that TraCI reads
    // Example placeholder:
    // applyTlsAction(action);

    return action;
}

module.exports = { handleEvRequest, logEvent };
