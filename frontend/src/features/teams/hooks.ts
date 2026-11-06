import { useQuery } from "@tanstack/react-query";
import { listDevelopers, listTeams } from "./api";
export const useTeams = (enabled = true) =>
  useQuery({ queryKey: ["teams"], queryFn: listTeams, enabled });
export const useDevelopers = (enabled = true) =>
  useQuery({ queryKey: ["team-developers"], queryFn: listDevelopers, enabled });
