// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { addToCart, api, claimOffer, fetchHolds, fetchTickets, fetchWaitlist, joinWaitlist, releaseHold } from "./api";
import { DEFAULT_HOLD_MINUTES, DEFAULT_OFFER_WINDOW_MINUTES } from "./format";
import type { CartPayload, Hold, ReturnOffer, WaitlistEntry, WalletTicket } from "./types";

export interface TimedHold extends Hold {
  /** Local ms epoch, stamped from seconds_remaining at fetch time. */
  deadline: number;
}

export interface TimedOffer extends ReturnOffer {
  deadline: number;
}

interface LiveState {
  holds: TimedHold[];
  holdsLoaded: boolean;
  /** The venue's hold and return-offer windows, as /api/holds reports them. */
  holdMinutes: number;
  offerWindowMinutes: number;
  waitlist: WaitlistEntry[];
  offers: TimedOffer[];
  tickets: WalletTicket[];
  refreshHolds: () => void;
  refreshWaitlist: () => void;
  refreshTickets: () => void;
  hold: (productId: string, quantity: number) => Promise<boolean>;
  join: (productId: string, quantity: number) => Promise<number | null>;
  claim: (offerId: string) => Promise<boolean>;
  release: (holdId: string) => Promise<void>;
}

const LiveContext = createContext<LiveState>({
  holds: [],
  holdsLoaded: false,
  holdMinutes: DEFAULT_HOLD_MINUTES,
  offerWindowMinutes: DEFAULT_OFFER_WINDOW_MINUTES,
  waitlist: [],
  offers: [],
  tickets: [],
  refreshHolds: () => {},
  refreshWaitlist: () => {},
  refreshTickets: () => {},
  hold: async () => false,
  join: async () => null,
  claim: async () => false,
  release: async () => {},
});

export function useLive(): LiveState {
  return useContext(LiveContext);
}

export function useCountdown(deadline: number | null): number | null {
  const [seconds, setSeconds] = useState<number | null>(() =>
    deadline == null ? null : Math.max(0, Math.round((deadline - Date.now()) / 1000)),
  );
  useEffect(() => {
    if (deadline == null) {
      setSeconds(null);
      return;
    }
    const tick = () => setSeconds(Math.max(0, Math.round((deadline - Date.now()) / 1000)));
    tick();
    const interval = window.setInterval(tick, 500);
    return () => window.clearInterval(interval);
  }, [deadline]);
  return seconds;
}

function stamp<T extends { seconds_remaining: number }>(rows: T[], at: number) {
  return rows.map((row) => ({ ...row, deadline: at + row.seconds_remaining * 1000 }));
}

export function LiveProvider({
  ready,
  onCartUpdate,
  children,
}: {
  ready: boolean;
  /** The cart is a view of the holds, so a holds read refreshes it too. */
  onCartUpdate: (cart: CartPayload) => void;
  children: ReactNode;
}) {
  const [holds, setHolds] = useState<TimedHold[]>([]);
  const [holdsLoaded, setHoldsLoaded] = useState(false);
  const [holdMinutes, setHoldMinutes] = useState(DEFAULT_HOLD_MINUTES);
  const [offerWindowMinutes, setOfferWindowMinutes] = useState(DEFAULT_OFFER_WINDOW_MINUTES);
  const [waitlist, setWaitlist] = useState<WaitlistEntry[]>([]);
  const [offers, setOffers] = useState<TimedOffer[]>([]);
  const [tickets, setTickets] = useState<WalletTicket[]>([]);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // A failed read (null) keeps the last good state; the next poll or deadline retries it.
  const refreshHolds = useCallback(() => {
    if (!ready) return;
    void fetchHolds().then((fresh) => {
      if (!aliveRef.current || fresh === null) return;
      setHolds(stamp(fresh.holds, Date.now()));
      if (fresh.hold_minutes) setHoldMinutes(fresh.hold_minutes);
      if (fresh.offer_window_minutes) setOfferWindowMinutes(fresh.offer_window_minutes);
      setHoldsLoaded(true);
    });
    void api.fetchCart<CartPayload>().then((cart) => {
      if (aliveRef.current && cart) onCartUpdate(cart);
    });
  }, [ready, onCartUpdate]);

  const refreshWaitlist = useCallback(() => {
    if (!ready) return;
    void fetchWaitlist().then((fresh) => {
      if (!aliveRef.current || fresh === null) return;
      setWaitlist(fresh.entries);
      setOffers(stamp(fresh.offers, Date.now()));
    });
  }, [ready]);

  const refreshTickets = useCallback(() => {
    if (!ready) return;
    void fetchTickets().then((fresh) => {
      if (aliveRef.current && fresh !== null) setTickets(fresh);
    });
  }, [ready]);

  // The waitlist polls fastest so return offers show up promptly; the wallet polls on
  // the entry-code rotation period.
  useEffect(() => {
    if (!ready) return;
    refreshHolds();
    refreshWaitlist();
    refreshTickets();
    const holdsPoll = window.setInterval(refreshHolds, 30000);
    const waitlistPoll = window.setInterval(refreshWaitlist, 10000);
    const ticketsPoll = window.setInterval(refreshTickets, 60000);
    return () => {
      window.clearInterval(holdsPoll);
      window.clearInterval(waitlistPoll);
      window.clearInterval(ticketsPoll);
    };
  }, [ready, refreshHolds, refreshWaitlist, refreshTickets]);

  // Read again just after the soonest deadline passes.
  useEffect(() => {
    const deadlines = [...holds, ...offers].map((row) => row.deadline);
    if (!deadlines.length) return;
    const soonest = Math.min(...deadlines);
    const timer = window.setTimeout(
      () => {
        refreshHolds();
        refreshWaitlist();
      },
      Math.max(250, soonest - Date.now() + 800),
    );
    return () => window.clearTimeout(timer);
  }, [holds, offers, refreshHolds, refreshWaitlist]);

  const hold = useCallback(
    async (productId: string, quantity: number) => {
      if (!ready) return false;
      const cart = await addToCart(productId, quantity);
      if (cart) onCartUpdate(cart);
      refreshHolds();
      return cart !== null;
    },
    [ready, onCartUpdate, refreshHolds],
  );

  const join = useCallback(
    async (productId: string, quantity: number) => {
      if (!ready) return null;
      const position = await joinWaitlist(productId, quantity);
      refreshWaitlist();
      return position;
    },
    [ready, refreshWaitlist],
  );

  const claim = useCallback(
    async (offerId: string) => {
      if (!ready) return false;
      const claimed = await claimOffer(offerId);
      refreshWaitlist();
      refreshHolds();
      return claimed !== null;
    },
    [ready, refreshWaitlist, refreshHolds],
  );

  const release = useCallback(
    async (holdId: string) => {
      if (!ready) return;
      await releaseHold(holdId);
      refreshHolds();
    },
    [ready, refreshHolds],
  );

  const value = useMemo(
    () => ({
      holds,
      holdsLoaded,
      holdMinutes,
      offerWindowMinutes,
      waitlist,
      offers,
      tickets,
      refreshHolds,
      refreshWaitlist,
      refreshTickets,
      hold,
      join,
      claim,
      release,
    }),
    [
      holds,
      holdsLoaded,
      waitlist,
      offers,
      tickets,
      refreshHolds,
      refreshWaitlist,
      refreshTickets,
      hold,
      join,
      claim,
      release,
    ],
  );

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}
