import { z } from "zod";
import { del, get, patch, post } from "@/lib/api-client";
import {
  LimitRuleCreateSchema,
  type LimitRuleCreate,
} from "@/features/api-keys/schemas";

export const TeamSchema = z.object({
  id: z.string(),
  name: z.string(),
  assignedAccountIds: z.array(z.string()).nullable(),
  assignedSourceIds: z.array(z.string()).nullable(),
  memberUserIds: z.array(z.string()),
  limits: z.array(
    LimitRuleCreateSchema.extend({
      id: z.number(),
      currentValue: z.number(),
      resetAt: z.string(),
    }),
  ),
});
export type Team = z.infer<typeof TeamSchema>;
const DeveloperSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.string(),
});
export type Developer = z.infer<typeof DeveloperSchema>;
const TotalSchema = z.object({
  teamId: z.string().nullable(),
  ownerUserId: z.string().nullable(),
  requestCount: z.number(),
  totalTokens: z.number(),
  cachedInputTokens: z.number(),
  totalCostUsd: z.number(),
});
export const ReportSchema = z.object({
  start: z.string(),
  end: z.string(),
  teams: z.array(TotalSchema),
  developers: z.array(TotalSchema),
  breakdown: z.array(TotalSchema),
  unassigned: z.array(TotalSchema),
});
export type TeamUpdate = {
  name: string;
  assignedAccountIds: string[] | null;
  assignedSourceIds: string[] | null;
  limits: LimitRuleCreate[];
  resetUsage?: boolean;
};
export const listTeams = () => get("/api/teams/", z.array(TeamSchema));
export const listDevelopers = () =>
  get("/api/teams/developers", z.array(DeveloperSchema));
export const createTeam = (name: string) =>
  post("/api/teams/", TeamSchema, { body: { name } });
export const updateTeam = (id: string, body: TeamUpdate) =>
  patch(`/api/teams/${encodeURIComponent(id)}`, TeamSchema, { body });
export const deleteTeam = (id: string) =>
  del(`/api/teams/${encodeURIComponent(id)}`);
export const addMember = (id: string, userId: string) =>
  post(`/api/teams/${encodeURIComponent(id)}/members`, TeamSchema, {
    body: { userId },
  });
export const removeMember = (id: string, userId: string) =>
  del(
    `/api/teams/${encodeURIComponent(id)}/members/${encodeURIComponent(userId)}`,
  );
export const getReport = (
  start: string,
  end: string,
  teamId: string,
  developerId: string,
) => {
  const params = new URLSearchParams({ start, end });
  if (teamId) params.set("team_id", teamId);
  if (developerId) params.set("developer_id", developerId);
  return get(`/api/teams/usage?${params}`, ReportSchema);
};
