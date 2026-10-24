import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt } from "../../test/render";

describe("releases", () => {
  it("shows each release with its speaker-disjoint splits and breakdowns", async () => {
    mockApi();
    renderAt("/releases");
    expect(await screen.findByRole("heading", { name: "v1" })).toBeInTheDocument();
    expect(screen.getByText(/train has 1 speaker\./)).toBeInTheDocument();
    expect(screen.getByText("By bandwidth tier")).toBeInTheDocument();
    expect(screen.getByTitle("SHA-256 of manifest.parquet")).toHaveTextContent("cdcd");
  });

  it("has an empty state", async () => {
    mockApi((p) => (p === "/api/releases" ? { status: 200, body: [] } : undefined));
    renderAt("/releases");
    expect(await screen.findByText("No release yet")).toBeInTheDocument();
  });
});
