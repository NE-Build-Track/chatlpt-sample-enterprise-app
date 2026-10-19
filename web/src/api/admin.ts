import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";
import { User, UserRow } from "./schemas";

export function useAdminUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => request(z.array(UserRow), "/api/admin/users"),
    refetchInterval: (query) => (query.state.data?.some((r) => (r.totals?.wholesale_pending ?? 0) > 0) ? 15_000 : false),
  });
}

export function useSetDisabled() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, disabled }: { id: string; disabled: boolean }) =>
      request(User, `/api/admin/users/${id}/disabled`, { method: "POST", body: JSON.stringify({ disabled }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}
