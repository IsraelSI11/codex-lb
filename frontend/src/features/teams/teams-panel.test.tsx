import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { TeamsPanel } from "./teams-panel";

describe("TeamsPanel", () => {
  it("shows an empty report with filters and hides mutations for readers", async () => {
    renderWithProviders(<TeamsPanel canWrite={false} />);
    expect(
      await screen.findByText("No usage in this period."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("From")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create team" }),
    ).not.toBeInTheDocument();
  });
  it("creates a team and uses the shared editors", async () => {
    const user = userEvent.setup();
    let created = false;
    server.use(
      http.post("/api/teams/", async ({ request }) => {
        expect(await request.json()).toEqual({ name: "Backend" });
        created = true;
        return HttpResponse.json({
          id: "backend",
          name: "Backend",
          assignedAccountIds: null,
          assignedSourceIds: null,
          memberUserIds: [],
          limits: [],
        });
      }),
    );
    renderWithProviders(<TeamsPanel canWrite />);
    await screen.findByText("No usage in this period.");
    await user.click(
      screen.getByText("Team members · Eligible resources · Shared budgets"),
    );
    await user.type(screen.getByPlaceholderText("Team name"), "Backend");
    await user.click(screen.getByRole("button", { name: "Create team" }));
    await waitFor(() => expect(created).toBe(true));
    expect(
      screen.getByRole("button", { name: "Save team" }),
    ).toBeInTheDocument();
  });
  it("surfaces load errors", async () => {
    server.use(
      http.get("/api/teams/", () =>
        HttpResponse.json(
          {
            error: { code: "unavailable", message: "Team service unavailable" },
          },
          { status: 503 },
        ),
      ),
    );
    renderWithProviders(<TeamsPanel canWrite={false} />);
    expect(
      await screen.findByText("Team service unavailable"),
    ).toBeInTheDocument();
  });
});

it("keeps membership conflict visible and saves an explicitly empty account scope", async () => {
  const user = userEvent.setup();
  const team = {
    id: "default",
    name: "Default",
    assignedAccountIds: null,
    assignedSourceIds: null,
    memberUserIds: ["ana"],
    limits: [],
  };
  let saved: unknown;
  server.use(
    http.get("/api/teams/", () => HttpResponse.json([team])),
    http.get("/api/teams/developers", () =>
      HttpResponse.json([{ id: "ana", name: "Ana", status: "active" }]),
    ),
    http.delete("/api/teams/default/members/ana", () =>
      HttpResponse.json(
        {
          error: {
            code: "conflict",
            message: "Deactivate active team keys first",
          },
        },
        { status: 409 },
      ),
    ),
    http.patch("/api/teams/default", async ({ request }) => {
      saved = await request.json();
      return HttpResponse.json(team);
    }),
  );
  renderWithProviders(<TeamsPanel canWrite />);
  await screen.findByText("No usage in this period.");
  await user.click(
    screen.getByText("Team members · Eligible resources · Shared budgets"),
  );
  await user.click(screen.getByRole("button", { name: "Remove member" }));
  expect(
    await screen.findByText("Deactivate active team keys first"),
  ).toBeInTheDocument();
  await user.click(
    screen.getByRole("checkbox", { name: "Upstream accounts · Unrestricted" }),
  );
  await user.click(screen.getByRole("button", { name: "Save team" }));
  await waitFor(() =>
    expect(saved).toEqual({
      name: "Default",
      assignedAccountIds: [],
      assignedSourceIds: null,
      limits: [],
    }),
  );
});

it("sends team and developer filters and rejects an inverted date range", async () => {
  const user = userEvent.setup();
  let filters = "";
  server.use(
    http.get("/api/teams/developers", () =>
      HttpResponse.json([{ id: "ana", name: "Ana", status: "active" }]),
    ),
    http.get("/api/teams/usage", ({ request }) => {
      filters = new URL(request.url).search;
      return HttpResponse.json({
        start: "2026-01-01",
        end: "2026-02-01",
        teams: [],
        developers: [],
        breakdown: [],
        unassigned: [],
      });
    }),
  );
  renderWithProviders(<TeamsPanel canWrite={false} />);
  await screen.findByText("No usage in this period.");
  await user.selectOptions(screen.getByLabelText("Team"), "default");
  await user.selectOptions(screen.getByLabelText("Developer"), "ana");
  await waitFor(() => {
    expect(filters).toContain("team_id=default");
    expect(filters).toContain("developer_id=ana");
  });
  await user.clear(screen.getByLabelText("From"));
  expect(
    await screen.findByText("Choose a start date before the end date."),
  ).toBeInTheDocument();
});
