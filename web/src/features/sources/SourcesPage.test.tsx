import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";

describe("sources", () => {
  it("lists each source's verdict, yield and cost per usable hour", async () => {
    mockApi();
    renderAt("/sources");
    expect(await screen.findByRole("link", { name: "audiobooks" })).toHaveAttribute("href", "/items?source=audiobooks");
    expect(screen.getByText("ingest: 2 of 3 sampled files usable")).toHaveAttribute("data-tone", "kept");
    expect(screen.getByText("$0.02")).toBeInTheDocument();
    expect(screen.getByText("nothing kept")).toBeInTheDocument();
    expect(screen.getByText("not scored")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /12 Declared synthetic/ })).toBeInTheDocument();
  });

  it("has an empty state", async () => {
    mockApi((p) => (p === "/api/sources" ? { status: 200, body: [] } : undefined));
    renderAt("/sources");
    expect(await screen.findByText("No sources yet")).toBeInTheDocument();
  });
});
