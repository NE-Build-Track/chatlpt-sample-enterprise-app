import type { ReactNode } from "react";
import { useProviders } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

const LABELS: Record<string, string> = { google: "Continue with Google", github: "Continue with GitHub" };

export function AuthShell({ title, children, next }: { title: string; children: ReactNode; next: string }) {
  const providers = useProviders();
  const list = providers.data?.providers ?? [];
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">ChatLPT</h1>
          <p className="text-sm text-muted-foreground">{title}</p>
        </div>
        {list.length > 0 && (
          <div className="space-y-2">
            {list.map((p) => (
              <Button key={p} variant="outline" className="w-full" asChild>
                <a href={`/api/auth/oauth/${p}/start?next=${encodeURIComponent(next)}`}>{LABELS[p] ?? `Continue with ${p}`}</a>
              </Button>
            ))}
            <div className="flex items-center gap-3 py-1 text-xs text-muted-foreground">
              <Separator className="flex-1" /> or <Separator className="flex-1" />
            </div>
          </div>
        )}
        {children}
      </div>
    </main>
  );
}
