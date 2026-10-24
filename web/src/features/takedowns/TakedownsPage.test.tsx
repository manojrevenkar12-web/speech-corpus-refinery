import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";

describe("takedowns", () => {
  it("previews the impact before anything is removed, then executes", async () => {
    const fetchMock = mockApi();
    const user = userEvent.setup();
    renderAt("/takedowns");
    await user.click(await screen.findByLabelText("A whole domain"));
    await user.type(screen.getByLabelText("Value"), "podcasts.example");
    await user.type(screen.getByLabelText(/Reason/), "Rights holder asked for removal");
    await user.click(screen.getByRole("button", { name: "Show what it would remove" }));
    expect(await screen.findByText(/Withdraws 17 files and 22 segments/)).toBeInTheDocument();
    expect(screen.getByText(/Contained in releases v1/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u) === "/api/takedowns" && (fetchMock.mock.calls.find(([x]) => String(x) === "/api/takedowns")![1] as RequestInit | undefined)?.method === "POST")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Take it down" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u) === "/api/takedowns" && (i as RequestInit | undefined)?.method === "POST")).toBe(true));
  });

  it("shows forbidden clearly for a viewer", async () => {
    mockApi((p, init) => (p === "/api/takedowns" && init?.method === "POST" ? { status: 403, body: { detail: "needs the admin role" } } : undefined));
    const user = userEvent.setup();
    renderAt("/takedowns");
    await user.type(await screen.findByLabelText("Value"), "https://x.example/a.mp3");
    await user.type(screen.getByLabelText(/Reason/), "Request");
    await user.click(screen.getByRole("button", { name: "Show what it would remove" }));
    await user.click(await screen.findByRole("button", { name: "Take it down" }));
    expect(await screen.findByText("needs the admin role")).toBeInTheDocument();
  });
});
