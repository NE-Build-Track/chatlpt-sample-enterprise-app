import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";
import { Conversation, ConversationOut, ModelOut, type ThinkingLevel, UsageTotals } from "./schemas";

export const conversationKeys = {
  all: ["conversations"] as const,
  one: (id: string) => ["conversations", id] as const,
};

export function useConversations() {
  return useQuery({ queryKey: conversationKeys.all, queryFn: () => request(z.array(Conversation), "/api/conversations") });
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: conversationKeys.one(id ?? ""),
    queryFn: () => request(ConversationOut, `/api/conversations/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.messages.some((m) => m.wholesale?.status === "pending") ? 15_000 : false;
    },
  });
}

export function useCreateConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request(Conversation, "/api/conversations", { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: conversationKeys.all }),
  });
}

export function useRenameConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      request(Conversation, `/api/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
    onSuccess: () => client.invalidateQueries({ queryKey: conversationKeys.all }),
  });
}

export function useSetThinking() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, thinking }: { id: string; thinking: ThinkingLevel }) =>
      request(Conversation, `/api/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ thinking }) }),
    onSuccess: (_data, { id }) => {
      void client.invalidateQueries({ queryKey: conversationKeys.one(id) });
      void client.invalidateQueries({ queryKey: conversationKeys.all });
    },
  });
}

export function useDeleteConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => request(z.undefined(), `/api/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: conversationKeys.all }),
  });
}

export function useClearHistory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (olderThanDays: number | null) =>
      request(
        z.object({ deleted: z.number() }),
        olderThanDays === null ? "/api/conversations?all=true" : `/api/conversations?older_than_days=${olderThanDays}`,
        { method: "DELETE" },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: conversationKeys.all }),
  });
}

export function useModel() {
  return useQuery({ queryKey: ["model"], queryFn: () => request(ModelOut, "/api/model"), staleTime: 30_000 });
}

export function useMyUsage() {
  return useQuery({
    queryKey: ["usage", "me"],
    queryFn: () => request(UsageTotals, "/api/usage/me"),
    staleTime: 15_000,
    // Network costs arrive after the reply; keep polling the totals while any are pending.
    refetchInterval: (query) => (query.state.data?.wholesale_pending ? 15_000 : false),
  });
}
