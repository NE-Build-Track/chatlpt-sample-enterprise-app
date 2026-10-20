import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { login, useProviders } from "@/api/auth";
import { HttpError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthShell } from "./AuthShell";
import { localPath, signInError } from "./paths";

export function LoginPage() {
  const [params] = useSearchParams();
  const next = localPath(params.get("next"));
  const navigate = useNavigate();
  const client = useQueryClient();
  const providers = useProviders();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(signInError(params.get("error")));
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      client.setQueryData(["me"], user);
      navigate(next, { replace: true });
    } catch (e) {
      setError(e instanceof HttpError ? e.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Sign in to continue" next={next}>
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy}>Sign in</Button>
      </form>
      {providers.data?.allow_signup !== false && (
        <p className="text-center text-sm text-muted-foreground">
          No account? <Link className="underline" to={`/signup?next=${encodeURIComponent(next)}`}>Sign up</Link>
        </p>
      )}
    </AuthShell>
  );
}
