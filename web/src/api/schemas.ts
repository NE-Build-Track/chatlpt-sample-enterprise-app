import { z } from "zod";

// Mirrors src/chatlpt/contracts. Money and prices are decimal strings; never parse them as floats for math.
export const Money = z.object({ amount: z.string(), currency: z.literal("USD") });
export type Money = z.infer<typeof Money>;

export const User = z.object({
  id: z.string(),
  email: z.string(),
  display_name: z.string(),
  is_admin: z.boolean(),
  disabled: z.boolean(),
  created_at: z.string(),
  email_verified: z.boolean(),
});
export type User = z.infer<typeof User>;

export const ClaimDetails = z.object({ email: z.string(), provider: z.string() });
export const SignedIn = z.object({ user: User, next: z.string() });

export const TokenUsage = z.object({
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  reasoning_tokens: z.number().default(0),
  cached_prompt_tokens: z.number().default(0),
});
export type TokenUsage = z.infer<typeof TokenUsage>;

export const WholesaleCost = z.object({
  status: z.enum(["none", "pending", "delivered", "failed_after_payment", "uncertain", "unknown"]),
  amount: Money.nullable().optional(),
  failed: Money.nullable().optional(), // delivered replies: what the attempts it failed over from cost
  orchestrator_url: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type WholesaleCost = z.infer<typeof WholesaleCost>;

export const ToolCall = z.object({ id: z.string(), name: z.string(), arguments: z.record(z.string(), z.unknown()) });
export type ToolCall = z.infer<typeof ToolCall>;

export const GeneratedImage = z.object({
  id: z.string(),
  message_id: z.string(),
  conversation_id: z.string(),
  prompt: z.string(),
  image_size: z.string(),
  width: z.number(),
  height: z.number(),
  seed: z.number().nullable().optional(),
  content_type: z.string(),
  size_bytes: z.number(),
  job_id: z.string().nullable().optional(),
  orchestrator_url: z.string().nullable().optional(),
  retail: Money.nullable().optional(),
  wholesale: WholesaleCost.nullable().optional(),
  expired: z.boolean().default(false),
  created_at: z.string(),
});
export type GeneratedImage = z.infer<typeof GeneratedImage>;

export const Message = z.object({
  id: z.string(),
  conversation_id: z.string(),
  role: z.enum(["system", "user", "assistant", "tool"]),
  kind: z.enum(["text", "tool_call"]).default("text"),
  content: z.string(),
  reasoning: z.string().nullable().optional(),
  tool_calls: z.array(ToolCall).default([]),
  images: z.array(GeneratedImage).default([]),
  state: z.enum(["streaming", "complete", "failed", "uncertain"]).default("complete"),
  job_id: z.string().nullable().optional(),
  orchestrator_url: z.string().nullable().optional(),
  usage: TokenUsage.nullable().optional(),
  retail: Money.nullable().optional(),
  wholesale: WholesaleCost.nullable().optional(),
  finish_reason: z.string().nullable().optional(),
  continues_message_id: z.string().nullable().optional(),
  dropped_turns: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
  created_at: z.string(),
});
export type Message = z.infer<typeof Message>;

export const ThinkingLevel = z.enum(["off", "low", "medium", "high"]);
export type ThinkingLevel = z.infer<typeof ThinkingLevel>;

export const Conversation = z.object({
  id: z.string(),
  user_id: z.string(),
  title: z.string(),
  thinking: ThinkingLevel.default("medium"),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Conversation = z.infer<typeof Conversation>;

export const UsageTotals = z.object({
  user_id: z.string().nullable(),
  start: z.string(),
  end: z.string(),
  replies: z.number(),
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  reasoning_tokens: z.number(),
  retail: Money,
  wholesale: Money, // delivered network spend (D29)
  wholesale_pending: z.number(),
  images: z.number().default(0),
  wholesale_failed: Money, // paid, with no usable result: failed after payment plus uncertain
});
export type UsageTotals = z.infer<typeof UsageTotals>;

export const ConversationOut = z.object({ conversation: Conversation, messages: z.array(Message), totals: UsageTotals });
export type ConversationOut = z.infer<typeof ConversationOut>;

export const ModelInfo = z.object({ app: z.string(), model_id: z.string(), max_model_len: z.number(), observed_at: z.string() });
export const PriceTable = z.object({
  model: z.string(),
  vendor: z.string(),
  region: z.string(),
  currency: z.literal("USD"),
  input_per_m: z.string(),
  output_per_m: z.string(),
  cached_input_per_m: z.string().nullable(),
  thinking_output_per_m: z.string().nullable(),
  source_url: z.string(),
  observed_at: z.string(),
});
export const ModelOut = z.object({
  app: z.string(),
  chat_available: z.boolean(),
  reason: z.string().nullable(),
  images_available: z.boolean().default(false),
  image_app: z.string().nullable().optional(),
  model: ModelInfo.nullable(),
  prices: PriceTable,
});
export type ModelOut = z.infer<typeof ModelOut>;

export const Providers = z.object({ providers: z.array(z.string()), allow_signup: z.boolean() });
export type Providers = z.infer<typeof Providers>;

export const ReplyEvent = z.object({
  type: z.enum(["start", "reasoning", "content", "tool_call", "image", "usage", "done", "error"]),
  user_message: Message.nullable().optional(),
  image: GeneratedImage.nullable().optional(),
  dropped_turns: z.number().default(0),
  message: Message.nullable().optional(),
  text: z.string().default(""),
  error: z.string().nullable().optional(),
  retry_after_s: z.number().nullable().optional(),
});
export type ReplyEvent = z.infer<typeof ReplyEvent>;

export const UserRow = z.object({ user: User, totals: UsageTotals.nullable() });
export type UserRow = z.infer<typeof UserRow>;

export const ApiError = z.object({ error: z.string(), type: z.string().optional() });
