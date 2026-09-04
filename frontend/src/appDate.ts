// The "app date": the calendar day the app believes it is.
//
// Normally this is simply today. During the testing phase a tester can step
// the date forward or back from the Home screen (see the date stepper there)
// so a week of daily exercise, the daily medal, Alira's reminders and the
// re-assessment day can be walked through in minutes instead of days. Every
// screen that asks "what is today?" goes through this module, and the server
// receives the same date (`as_of`) so its care plan agrees with the app.
//
// The override is kept in memory for synchronous callers and persisted in
// storage so it survives reloads; `loadAppDateOverride()` hydrates it once.

import { storage } from "@/src/utils/storage";

const APP_DATE_KEY = "rehyn_app_date_override_v1";

let overrideDate: string | null = null;
let hydrated = false;
const listeners = new Set<(date: string | null) => void>();

export function formatLocalDate(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function isCalendarDate(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(value);
}

/** Parse a YYYY-MM-DD string as a local calendar day (noon, to dodge DST edges). */
export function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split("-").map((part) => Number.parseInt(part, 10));
  return new Date(year, (month || 1) - 1, day || 1, 12, 0, 0, 0);
}

export async function loadAppDateOverride(): Promise<string | null> {
  if (hydrated) return overrideDate;
  const saved = await storage.getItem<string>(APP_DATE_KEY, "");
  overrideDate = isCalendarDate(saved) ? saved : null;
  hydrated = true;
  return overrideDate;
}

export function getAppDateOverride(): string | null {
  return overrideDate;
}

export async function setAppDateOverride(date: string | null): Promise<void> {
  overrideDate = isCalendarDate(date) ? date : null;
  hydrated = true;
  if (overrideDate) await storage.setItem(APP_DATE_KEY, overrideDate);
  else await storage.removeItem(APP_DATE_KEY);
  listeners.forEach((listener) => listener(overrideDate));
}

export function subscribeAppDate(listener: (date: string | null) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Today's calendar date as the app sees it (YYYY-MM-DD). */
export function appDateString(): string {
  return overrideDate || formatLocalDate(new Date());
}

/** "Now" as the app sees it: the app date with the real time of day. */
export function appNow(): Date {
  if (!overrideDate) return new Date();
  const real = new Date();
  const shifted = parseLocalDate(overrideDate);
  shifted.setHours(real.getHours(), real.getMinutes(), real.getSeconds(), real.getMilliseconds());
  return shifted;
}

/** The app date moved by a number of days (YYYY-MM-DD). */
export function shiftedAppDate(days: number): string {
  const base = parseLocalDate(appDateString());
  base.setDate(base.getDate() + days);
  return formatLocalDate(base);
}

/** Query-string suffix telling the server which date the app is showing. */
export function appDateQuery(prefix: "?" | "&" = "?"): string {
  return overrideDate ? `${prefix}as_of=${encodeURIComponent(overrideDate)}` : "";
}

export function isAppDateOverridden(): boolean {
  return Boolean(overrideDate) && overrideDate !== formatLocalDate(new Date());
}
