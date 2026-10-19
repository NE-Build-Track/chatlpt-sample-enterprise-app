import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";
import { User, UserRow } from "./schemas";

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin", "users"], queryFn: () => request(z.array(UserRow), "/api/admin/users") });
}

export function useSetDisabled() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, disabled }: { id: string; disabled: boolean }) =>
      request(User, `/api/admin/users/${id}/disabled`, { method: "POST", body: JSON.stringify({ disabled }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
}
