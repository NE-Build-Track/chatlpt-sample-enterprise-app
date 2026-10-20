import { type FormEvent, type ReactNode, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { claimDetails, claimNew, keepAccount } from "@/api/auth";
import { HttpError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { localPath } from "./paths";

const PROVIDERS: Record<string, string> = { google: "Google", github: "GitHub" };

// D26: Google or GitHub proved this email, but a ChatLPT password account already uses it. Its
// password keeps that account (and its history); otherwise a new account replaces it.
export function ClaimPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const details = useQuery({ queryKey: ["claim"], queryFn: claimDetails, retry: false });
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function finish(action: () => ReturnType<typeof claimNew>) {
    setBusy(true);
    setError(null);
    try {
      const done = await action();
      client.setQueryData(["me"], done.user);
      navigate(localPath(done.next), { replace: true });
    } catch (e) {
      setError(e instanceof HttpError ? e.message : "that did not work; try again");
    } finally {
      setBusy(false);
    }
  }

  function keep(event: FormEvent) {
    event.preventDefault();
    void finish(() => keepAccount(password));
  }

  if (details.isError) {
    return (
      <Shell>
        <p className="text-sm text-muted-foreground">This sign-in expired.</p>
        <Button asChild className="w-full"><Link to="/login">Sign in again</Link></Button>
      </Shell>
    );
  }
  const provider = PROVIDERS[details.data?.provider ?? ""] ?? "Your provider";
  return (
    <Shell>
      <p className="text-sm text-muted-foreground">
        {provider} confirmed <span className="font-medium text-foreground">{details.data?.email ?? "your email"}</span>,
        and a ChatLPT account with a password already uses it.
      </p>
      <form onSubmit={keep} className="space-y-3">
        <div className="space-y-2">
          <Label htmlFor="password">Enter that account's password to keep its history</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy || !details.data}>Keep that account</Button>
      </form>
      <div className="space-y-2 text-center">
        <p className="text-xs text-muted-foreground">Not yours, or no password? A new account takes over the address, and the old one is closed.</p>
        <Button variant="outline" className="w-full" disabled={busy || !details.data} onClick={() => void finish(claimNew)}>
          Continue with a new account
        </Button>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">ChatLPT</h1>
          <p className="text-sm text-muted-foreground">This email already has an account</p>
        </div>
        {children}
      </div>
    </main>
  );
}
