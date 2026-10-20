// Where to go after signing in: a path on this site, or "/". Mirrors the server's check (D26):
// browsers read "\" as "/" and drop tabs and newlines, so "/\evil.com" means "//evil.com", another site.
export function localPath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/")) return "/";
  if ([...value].some((ch) => ch.charCodeAt(0) < 0x20 || ch.charCodeAt(0) === 0x7f)) return "/";
  const candidate = value.replaceAll("\\", "/");
  if (candidate.startsWith("//")) return "/";
  return candidate;
}

// What the login page says when a Google or GitHub sign-in came back with ?error=<reason>.
export const SIGN_IN_ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled.",
  expired: "That sign-in took too long, or was started in another browser. Try again.",
  mismatch: "That sign-in was not started here. Try again.",
  provider_error: "Google or GitHub did not finish the sign-in. Try again in a moment.",
  unverified_email: "That Google or GitHub account has no verified email address.",
  disabled: "This account is disabled.",
  signup_closed: "There is no account for that email, and sign-up is closed.",
};

export function signInError(reason: string | null): string | null {
  if (!reason) return null;
  return SIGN_IN_ERRORS[reason] ?? "Sign-in failed. Try again.";
}
