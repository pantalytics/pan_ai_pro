/** @odoo-module */
// Copyright 2025-2026 Pantalytics B.V. All rights reserved.
// SPDX-License-Identifier: Elastic-2.0
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

/**
 * A component's props: Owl 3 sets `this.props` only through `useProps(spec)`
 * in setup (and ships the `t` type helpers); Owl 2 sets it by itself.
 * `spec` is a function of `t`, so it is never built on Owl 2.
 */
export function declareProps(component, spec) {
    if (owl.useProps) {
        component.props = owl.useProps(spec(owl.t));
    }
}

/** The store's thread model: `mail.thread` on 20, `Thread` on 19. */
export function threadModel(store) {
    return store["mail.thread"] || store.Thread;
}

/** A thread's channel type: on 20 it sits on the channel, on 19 on the thread. */
export function channelType(thread) {
    return thread?.channel?.channel_type ?? thread?.channel_type;
}

/**
 * A thread's parent channel, when it is a thread under a message in a team
 * channel: on 20 it sits on the channel, on 19 on the thread.
 */
export function parentChannel(thread) {
    return thread?.channel?.parent_channel_id ?? thread?.parent_channel_id;
}

/**
 * An action's icon: 20 names a Material symbol ("add"), 19 a Font Awesome
 * class ("fa fa-fw fa-plus"). A Material name on 19 renders nothing.
 */
export function actionIcon(material, fa) {
    return owl.proxy ? material : fa;
}
