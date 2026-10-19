import { useQuery, useQueryClient } from "@tanstack/react-query";
import { HttpError, request } from "./client";
import { Providers, User } from "./schemas";
import { z } from "zod";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await request(User, "/api/auth/me");
      } catch (error) {
        if (error instanceof HttpError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: () => request(Providers, "/api/auth/providers"), staleTime: Infinity });
}

export const login = (email: string, password: string) =>
  request(User, "/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });

export const signup = (email: string, password: string, display_name: string) =>
  request(User, "/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password, display_name }) });

export const logout = () => request(z.undefined(), "/api/auth/logout", { method: "POST" });

export function useLogout() {
  const client = useQueryClient();
  return async () => {
    await logout();
    client.clear();
    window.location.assign("/login");
  };
}
