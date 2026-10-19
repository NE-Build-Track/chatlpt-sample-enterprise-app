import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useMe } from "@/api/auth";
import { Skeleton } from "@/components/ui/skeleton";

export function RequireUser({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <Skeleton className="h-6 w-40" />
      </div>
    );
  }
  if (!me.data) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  return <>{children}</>;
}
