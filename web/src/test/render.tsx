import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { vi } from "vitest";

import { makeClient, routes } from "../app/App";
import * as fx from "./fixtures";

export type Responder = (path: string, init?: RequestInit) => { status: number; body: unknown } | undefined;

export function mockApi(override?: Responder) {
  const table: Array<[RegExp, unknown]> = [
    [/^\/api\/overview$/, fx.overview],
    [/^\/api\/sources$/, fx.sources],
    [/^\/api\/items\?/, { total: fx.items.length, items: fx.items }],
    [/^\/api\/items\/\d+$/, fx.detail],
    [/^\/api\/items\/\d+\/spectrogram/, fx.spectrogram],
    [/^\/api\/review\/queue/, fx.queue],
    [/^\/api\/reviews\/summary$/, fx.summary],
    [/^\/api\/reviews$/, { id: 1 }],
    [/^\/api\/items\/\d+\/resolve$/, { item_id: 9, state: "kept" }],
    [/^\/api\/releases$/, fx.releases],
    [/^\/api\/takedowns\/preview$/, { items: 17, segments: 22, kept_hours: 0.02, releases: ["v1"] }],
    [/^\/api\/takedowns$/, fx.takedowns],
  ];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const o = override?.(path, init);
    const hit = table.find(([re]) => re.test(path));
    const res = o ?? (hit ? { status: 200, body: hit[1] } : { status: 404, body: { detail: "no such path" } });
    return new Response(JSON.stringify(res.body), { status: res.status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function renderAt(path: string) {
  const client = makeClient();
  client.setDefaultOptions({ queries: { ...client.getDefaultOptions().queries, retry: false } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return { router, ...render(<QueryClientProvider client={client}><RouterProvider router={router} future={{ v7_startTransition: true }} /></QueryClientProvider>) };
}
