import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertMessage } from "@/components/alert-message";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AccountMultiSelect } from "@/features/api-keys/components/account-multi-select";
import { ModelSourceMultiSelect } from "@/features/model-sources/components/model-source-multi-select";
import { LimitRulesEditor } from "@/features/api-keys/components/limit-rules-editor";
import { type LimitRuleCreate } from "@/features/api-keys/schemas";
import { getErrorMessageOrNull } from "@/utils/errors";
import { formatCompactNumber, formatCurrency } from "@/utils/formatters";
import {
  addMember,
  createTeam,
  deleteTeam,
  getReport,
  removeMember,
  updateTeam,
  type Developer,
  type Team,
} from "./api";
import { useDevelopers, useTeams } from "./hooks";

const selectClass = "h-9 w-full rounded-md border bg-background px-3 text-sm";

function TeamEditor({
  team,
  developers,
}: {
  team: Team;
  developers: Developer[];
}) {
  const { t } = useTranslation();
  const id = useId();
  const queryClient = useQueryClient();
  const [name, setName] = useState(team.name);
  const [accounts, setAccounts] = useState(team.assignedAccountIds);
  const [sources, setSources] = useState(team.assignedSourceIds);
  const [limits, setLimits] = useState<LimitRuleCreate[]>(team.limits);
  const [member, setMember] = useState("");
  const mutation = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
      await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
  const run = (action: () => Promise<unknown>) => mutation.mutate(action);
  return (
    <div className="space-y-5 border-t pt-5">
      {mutation.error ? (
        <AlertMessage variant="error">
          {getErrorMessageOrNull(mutation.error)}
        </AlertMessage>
      ) : null}
      <fieldset className="space-y-5" disabled={mutation.isPending}>
        <div className="max-w-md space-y-1">
          <label htmlFor={`${id}-name`} className="text-sm font-medium">
            {t("teams.name")}
          </label>
          <Input
            id={`${id}-name`}
            value={name}
            maxLength={128}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-4">
            <h3 className="font-medium">{t("teams.resources")}</h3>
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={accounts === null}
                  onChange={(event) =>
                    setAccounts(event.target.checked ? null : [])
                  }
                />
                {t("teams.accounts")} · {t("teams.unrestricted")}
              </label>
              {accounts !== null ? (
                <AccountMultiSelect value={accounts} onChange={setAccounts} />
              ) : null}
            </div>
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={sources === null}
                  onChange={(event) =>
                    setSources(event.target.checked ? null : [])
                  }
                />
                {t("teams.sources")} · {t("teams.unrestricted")}
              </label>
              {sources !== null ? (
                <ModelSourceMultiSelect value={sources} onChange={setSources} />
              ) : null}
            </div>
          </div>
          <div className="space-y-3">
            <h3 className="font-medium">{t("teams.limits")}</h3>
            <p className="text-xs text-muted-foreground">
              {t("teams.budgetHelp")}
            </p>
            <LimitRulesEditor rules={limits} onChange={setLimits} />
            {team.limits.map((rule) => (
              <p key={rule.id} className="text-xs tabular-nums">
                {t(`apis.keyInfo.limitTypes.${rule.limitType}`)} ·{" "}
                {rule.limitType === "cost_usd"
                  ? formatCurrency(rule.currentValue / 1_000_000)
                  : formatCompactNumber(rule.currentValue)}{" "}
                /{" "}
                {rule.limitType === "cost_usd"
                  ? formatCurrency(rule.maxValue / 1_000_000)
                  : formatCompactNumber(rule.maxValue)}{" "}
                · {new Date(rule.resetAt).toLocaleString()}
              </p>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!name.trim() || mutation.isPending}
            onClick={() =>
              run(() =>
                updateTeam(team.id, {
                  name,
                  assignedAccountIds: accounts,
                  assignedSourceIds: sources,
                  limits,
                }),
              )
            }
          >
            {t("teams.save")}
          </Button>
          <Button
            variant="outline"
            onClick={() =>
              run(() =>
                updateTeam(team.id, {
                  name,
                  assignedAccountIds: accounts,
                  assignedSourceIds: sources,
                  limits,
                  resetUsage: true,
                }),
              )
            }
          >
            {t("teams.reset")}
          </Button>
          {team.id !== "default" ? (
            <Button
              variant="destructive"
              onClick={() => run(() => deleteTeam(team.id))}
            >
              {t("teams.delete")}
            </Button>
          ) : null}
        </div>
        <div className="space-y-3">
          <h3 className="font-medium">{t("teams.members")}</h3>
          <p className="text-xs text-muted-foreground">
            {t("teams.membersHelp")}
          </p>
          <ul className="divide-y">
            {team.memberUserIds.map((userId) => (
              <li
                key={userId}
                className="flex items-center justify-between gap-3 py-2 text-sm"
              >
                <span>
                  {developers.find((row) => row.id === userId)?.name ?? userId}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => run(() => removeMember(team.id, userId))}
                >
                  {t("teams.remove")}
                </Button>
              </li>
            ))}
          </ul>
          <div className="flex max-w-lg flex-wrap gap-2">
            <select
              aria-label={t("teams.developer")}
              className={`${selectClass} flex-1`}
              value={member}
              onChange={(event) => setMember(event.target.value)}
            >
              <option value="">{t("teams.developer")}</option>
              {developers
                .filter(
                  (row) =>
                    row.status === "active" &&
                    !team.memberUserIds.includes(row.id),
                )
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
            </select>
            <Button
              variant="outline"
              disabled={!member || mutation.isPending}
              onClick={() => run(() => addMember(team.id, member))}
            >
              {t("teams.add")}
            </Button>
          </div>
        </div>
      </fieldset>
    </div>
  );
}

export function TeamsPanel({ canWrite }: { canWrite: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const teams = useTeams();
  const developers = useDevelopers();
  const [selected, setSelected] = useState("default");
  const [name, setName] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [developerFilter, setDeveloperFilter] = useState("");
  const [start, setStart] = useState(() =>
    new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10),
  );
  const [end, setEnd] = useState(() =>
    new Date(Date.now() + 86400000).toISOString().slice(0, 10),
  );
  const validRange = Boolean(start && end && start < end);
  const report = useQuery({
    queryKey: ["team-usage", start, end, teamFilter, developerFilter],
    queryFn: () =>
      getReport(
        new Date(start).toISOString(),
        new Date(end).toISOString(),
        teamFilter,
        developerFilter,
      ),
    enabled: validRange,
  });
  const create = useMutation({
    mutationFn: createTeam,
    onSuccess: async (team) => {
      setSelected(team.id);
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
  });
  const team =
    teams.data?.find((row) => row.id === selected) ?? teams.data?.[0];
  const teamName = (id: string | null) =>
    teams.data?.find((row) => row.id === id)?.name ?? id;
  const developerName = (id: string | null) =>
    developers.data?.find((row) => row.id === id)?.name ??
    id ??
    t("teams.unassigned");
  const error = teams.error || developers.error || report.error || create.error;
  return (
    <section
      className="space-y-5 rounded-xl border bg-card p-4 sm:p-6"
      aria-label={t("teams.title")}
    >
      <h2 className="text-lg font-semibold">{t("teams.title")}</h2>
      {error ? (
        <AlertMessage variant="error">
          {getErrorMessageOrNull(error)}
        </AlertMessage>
      ) : null}
      {teams.isPending ? <p role="status">{t("common.loading")}</p> : null}
      {canWrite && teams.data ? (
        <details>
          <summary className="cursor-pointer text-sm font-medium">
            {t("teams.members")} · {t("teams.resources")} · {t("teams.limits")}
          </summary>
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-40 flex-1 space-y-1 text-sm">
                {t("teams.team")}
                <select
                  className={selectClass}
                  value={team?.id ?? ""}
                  onChange={(event) => setSelected(event.target.value)}
                >
                  {teams.data.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>
              <form
                className="flex flex-wrap gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  create.mutate(name);
                }}
              >
                <Input
                  aria-label={t("teams.name")}
                  placeholder={t("teams.name")}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={128}
                  required
                />
                <Button
                  disabled={!name.trim() || create.isPending}
                  variant="outline"
                >
                  {t("teams.create")}
                </Button>
              </form>
            </div>
            {team ? (
              <TeamEditor
                key={team.id}
                team={team}
                developers={developers.data ?? []}
              />
            ) : null}
          </div>
        </details>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1 text-sm">
          {t("teams.start")}
          <Input
            type="date"
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </label>
        <label className="space-y-1 text-sm">
          {t("teams.end")}
          <Input
            type="date"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </label>
        <label className="space-y-1 text-sm">
          {t("teams.team")}
          <select
            className={selectClass}
            value={teamFilter}
            onChange={(event) => setTeamFilter(event.target.value)}
          >
            <option value="">{t("teams.allTeams")}</option>
            {teams.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          {t("teams.developer")}
          <select
            className={selectClass}
            value={developerFilter}
            onChange={(event) => setDeveloperFilter(event.target.value)}
          >
            <option value="">{t("teams.allDevelopers")}</option>
            {developers.data?.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!validRange ? (
        <AlertMessage variant="error">{t("teams.invalidRange")}</AlertMessage>
      ) : report.isPending ? (
        <p role="status">{t("teams.loading")}</p>
      ) : report.data?.breakdown.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("teams.empty")}</p>
      ) : null}
      {report.data
        ? [
            { title: t("teams.team"), rows: report.data.teams },
            { title: t("teams.developer"), rows: report.data.developers },
            { title: t("teams.breakdown"), rows: report.data.breakdown },
          ]
            .filter((group) => group.rows.length > 0)
            .map((group) => (
              <div key={group.title} className="space-y-2">
                <h3 className="font-medium">{group.title}</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="py-2">{group.title}</th>
                        <th className="p-2 text-right">
                          {t("teams.requests")}
                        </th>
                        <th className="p-2 text-right">{t("teams.tokens")}</th>
                        <th className="p-2 text-right">{t("teams.cost")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.rows.map((row) => (
                        <tr
                          key={`${row.teamId ?? ""}:${row.ownerUserId ?? ""}`}
                          className="border-b last:border-0"
                        >
                          <td className="py-2">
                            {row.teamId
                              ? teamName(row.teamId)
                              : developerName(row.ownerUserId)}
                            {group.rows === report.data.breakdown
                              ? ` / ${developerName(row.ownerUserId)}`
                              : ""}
                          </td>
                          <td className="p-2 text-right tabular-nums">
                            {formatCompactNumber(row.requestCount)}
                          </td>
                          <td className="p-2 text-right tabular-nums">
                            {formatCompactNumber(row.totalTokens)}
                          </td>
                          <td className="p-2 text-right tabular-nums">
                            {formatCurrency(row.totalCostUsd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))
        : null}
    </section>
  );
}
