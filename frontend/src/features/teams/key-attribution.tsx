import { useId } from "react";
import { useTranslation } from "react-i18next";
import { AlertMessage } from "@/components/alert-message";
import { useDevelopers, useTeams } from "./hooks";

type Props = {
  teamId: string;
  ownerUserId: string | null;
  onChange: (teamId: string, ownerUserId: string | null) => void;
  readOnly?: boolean;
};
export function KeyAttribution({
  teamId,
  ownerUserId,
  onChange,
  readOnly = false,
}: Props) {
  const { t } = useTranslation();
  const id = useId();
  const teams = useTeams();
  const developers = useDevelopers();
  const team = teams.data?.find((row) => row.id === teamId);
  const invalidDeveloper = Boolean(
    ownerUserId && team && developers.data &&
    (!team.memberUserIds.includes(ownerUserId) ||
      !developers.data.some((row) => row.id === ownerUserId && row.status === "active")),
  );
  const membershipError = invalidDeveloper ? t("teams.invalidDeveloper") : "";
  return (
    <div className="space-y-3">
      {teams.isError || developers.isError ? (
        <AlertMessage variant="error">{t("teams.loadError")}</AlertMessage>
      ) : null}
      <div className="space-y-1">
        <label htmlFor={`${id}-team`} className="text-sm font-medium">
          {t("teams.team")}
        </label>
        <select
          id={`${id}-team`}
          className="h-9 w-full rounded-md border bg-background px-3 text-sm"
          disabled={readOnly || teams.isPending}
          value={teamId}
          onChange={(event) => onChange(event.target.value, ownerUserId)}
        >
          {!teams.data ? (
            <option value={teamId}>
              {teamId === "default" ? "Default" : teamId}
            </option>
          ) : null}
          {teams.data?.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <label htmlFor={`${id}-developer`} className="text-sm font-medium">
          {t("teams.developer")}
        </label>
        <select
          id={`${id}-developer`}
          className="h-9 w-full rounded-md border bg-background px-3 text-sm"
          disabled={readOnly || developers.isPending}
          aria-invalid={invalidDeveloper || undefined}
          aria-describedby={invalidDeveloper ? `${id}-membership-error` : undefined}
          ref={(element) => { element?.setCustomValidity(membershipError); }}
          value={ownerUserId ?? ""}
          onChange={(event) => onChange(teamId, event.target.value || null)}
        >
          {ownerUserId && developers.data && !developers.data.some((row) => row.id === ownerUserId) ? (
            <option value={ownerUserId}>{ownerUserId}</option>
          ) : null}
          <option value="">{t("teams.shared")}</option>
          {developers.data
            ?.filter(
              (row) =>
                row.id === ownerUserId ||
                (row.status === "active" &&
                  team?.memberUserIds.includes(row.id)),
            )
            .map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
        </select>
      </div>
      {invalidDeveloper ? (
        <p id={`${id}-membership-error`} className="text-sm text-destructive">{membershipError}</p>
      ) : null}
      {readOnly ? (
        <p className="text-xs text-muted-foreground">{t("teams.immutable")}</p>
      ) : null}
    </div>
  );
}
