/** @odoo-module */
import * as owl from "@odoo/owl";

/**
 * One chat bundle on Odoo 19 (Owl 2, mail's Thread model) and Odoo 20
 * (Owl 3, mail's `mail.thread` record with a `channel`). Everything that
 * differs between the two sits here; the rest of the bundle is the same.
 */

// Owl 3 calls the reactive object `proxy` and tracks every read made during
// a render. Owl 2 calls it `reactive` and a component sees changes only
// through `useState`.
export const liveState = owl.proxy || owl.reactive;

export function useLive(obj) {
    return owl.useState ? owl.useState(obj) : obj;
}

/** The store's thread model: `mail.thread` on 20, `Thread` on 19. */
export function threadModel(store) {
    return store["mail.thread"] || store.Thread;
}

/** A thread's channel type: on 20 it sits on the channel, on 19 on the thread. */
export function channelType(thread) {
    return thread?.channel?.channel_type ?? thread?.channel_type;
}
