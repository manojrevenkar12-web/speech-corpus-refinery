import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";

describe("overview", () => {
  it("shows usable hours, where the rest went, and what was never fetched", async () => {
    mockApi();
    renderAt("/");
    expect((await screen.findAllByText("2.2 min"))[0]).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /kept of 16.3 min analysed/ })).toBeInTheDocument();
    expect(screen.getByText("Duplicate of a better copy")).toBeInTheDocument();
    expect(screen.getByText("Too noisy (segments)")).toBeInTheDocument();
    expect(screen.getByText(/Rejected before decoding.*licence not usable \(8 files\)/)).toBeInTheDocument();
    expect(screen.getByText("TDM rights reserved")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "12 held for review" })).toHaveAttribute("href", "/review");
    expect(screen.getByText(/Intact: 3 entries/)).toBeInTheDocument();
  });

  it("has an empty state before anything is crawled", async () => {
    mockApi((p) => (p === "/api/overview" ? { status: 200, body: { files: 0 } } : undefined));
    renderAt("/");
    expect(await screen.findByText("Nothing crawled yet")).toBeInTheDocument();
  });

  it("asks for a key on 401 and recovers with it", async () => {
    mockApi((_p, init) => (new Headers(init?.headers).get("Authorization") === "Bearer viewer-key-0123456789" ? undefined : { status: 401, body: { detail: "missing or unknown API key" } }));
    const user = userEvent.setup();
    renderAt("/");
    await user.type(await screen.findByLabelText("API key"), "viewer-key-0123456789");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findAllByText("2.2 min"))[0]).toBeInTheDocument();
    sessionStorage.clear();
  });

  it("explains a failure and retries", async () => {
    let fail = true;
    mockApi((p) => (p === "/api/overview" && fail ? { status: 500, body: { detail: "database unavailable" } } : undefined));
    const user = userEvent.setup();
    renderAt("/");
    expect(await screen.findByText("database unavailable")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getAllByRole("button", { name: "Try again" })[0]!);
    expect((await screen.findAllByText("2.2 min"))[0]).toBeInTheDocument();
  });
});
