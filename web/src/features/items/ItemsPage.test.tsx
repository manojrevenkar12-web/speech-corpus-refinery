import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { detail } from "../../test/fixtures";
import { mockApi, renderAt } from "../../test/render";

describe("files", () => {
  it("filters by state and opens a file with its spectrogram and segments", async () => {
    const fetchMock = mockApi();
    const user = userEvent.setup();
    const { router } = renderAt("/items");
    expect(await screen.findByText("Choose a file")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("State"), "held");
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("state=held"))).toBe(true));
    await user.click(await screen.findByRole("button", { name: /ch1.mp3/ }));
    expect(router.state.location.search).toContain("item=7");
    expect(await screen.findByRole("img", { name: /Spectrogram/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Play segment 2.*rejected: noise/ })).toBeInTheDocument();
  });

  it("explains a file whose audio was deleted after a takedown", async () => {
    mockApi((p) => (/^\/api\/items\/\d+$/.test(p) ? { status: 200, body: { ...detail, audio_available: false } } : undefined));
    renderAt("/items?item=9");
    expect(await screen.findByText("No audio to show")).toBeInTheDocument();
    expect(screen.getByText("The audio was deleted after a takedown.")).toBeInTheDocument();
  });
});
