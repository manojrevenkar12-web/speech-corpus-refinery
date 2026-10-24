import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";
import { detail, queue } from "../../test/fixtures";
import { ramp } from "./Spectrogram";

describe("review", () => {
  it("lets a reviewer keep a held file, by button or by key", async () => {
    let resolved = false;
    const fetchMock = mockApi((p, init) => {
      if (p === "/api/items/9/resolve" && init?.method === "POST") resolved = true;
      if (p.startsWith("/api/review/queue") && resolved) return { status: 200, body: queue.slice(1) };
      if (p === "/api/items/10") return { status: 200, body: { ...detail, item: { ...detail.item, id: 10, url: queue[1]!.url } } };
      return undefined;
    });
    const user = userEvent.setup();
    renderAt("/review");
    expect(await screen.findByRole("button", { name: /Keep it/ })).toBeInTheDocument();
    expect(await screen.findByText("aind-000.mp3", { selector: "h2" })).toBeInTheDocument();
    await user.keyboard("k");
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u) === "/api/items/9/resolve" && (i as RequestInit).method === "POST")).toBe(true));
    const body = JSON.parse(String((fetchMock.mock.calls.find(([u]) => String(u) === "/api/items/9/resolve")![1] as RequestInit).body));
    expect(body.decision).toBe("keep");
    // the next held file comes up
    expect(await screen.findByText("aind-001.mp3", { selector: "h2" })).toBeInTheDocument();
  });

  it("shows measurements, segments with their decisions, and agreement so far", async () => {
    mockApi();
    renderAt("/review");
    expect(await screen.findByText(/podcast:license on the channel/)).toBeInTheDocument();
    expect(screen.getByText(/82% synthesizer/)).toBeInTheDocument();
    expect(await screen.findByText("Too noisy")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Play" })).toHaveLength(2);
    expect(screen.getByText("3 of 4")).toBeInTheDocument();
    expect(screen.getByText("30 to 95%")).toBeInTheDocument();
  });

  it("records a spot check on the rejections tab", async () => {
    const fetchMock = mockApi();
    const user = userEvent.setup();
    renderAt("/review");
    await user.click(await screen.findByRole("tab", { name: "Check rejections" }));
    await user.click(await screen.findByRole("button", { name: /Disagree/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u) === "/api/reviews")).toBe(true));
    const call = fetchMock.mock.calls.find(([u]) => String(u) === "/api/reviews")!;
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({ item_id: 9, verdict: "disagree" });
  });

  it("says when nothing is held", async () => {
    mockApi((p) => (p.startsWith("/api/review/queue") ? { status: 200, body: [] } : undefined));
    renderAt("/review");
    expect(await screen.findByText("Nothing is held")).toBeInTheDocument();
  });

  it("maps 0..1 onto the colour ramp", () => {
    const stops: Array<[number, number, number]> = [
      [0, 0, 0],
      [100, 100, 100],
      [200, 0, 0],
    ];
    expect(ramp(stops, 0)).toEqual([0, 0, 0]);
    expect(ramp(stops, 0.25)).toEqual([50, 50, 50]);
    expect(ramp(stops, 1)).toEqual([200, 0, 0]);
    expect(ramp(stops, 7)).toEqual([200, 0, 0]);
  });
});
