// Minimal shadcn-style primitives (owned in-repo, Tailwind v4). Kept tiny on purpose.
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[--radius] border bg-[--color-surface] shadow-sm", className)}
      {...p}
    />
  );
}

const btn = cva(
  "inline-flex items-center justify-center gap-2 rounded-[--radius] text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[--color-brand]",
  {
    variants: {
      variant: {
        primary: "bg-[--color-brand] text-[--color-brand-fg] hover:opacity-90",
        ghost: "hover:bg-[--color-surface-2] text-[--color-fg]",
        outline: "border border-[--color-border] hover:bg-[--color-surface-2]",
      },
      size: { sm: "h-8 px-3", md: "h-9 px-4", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);
export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof btn> {}
export function Button({ className, variant, size, ...p }: ButtonProps) {
  return <button className={cn(btn({ variant, size }), className)} {...p} />;
}

export function Badge({ className, ...p }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
        className,
      )}
      {...p}
    />
  );
}

export function StatLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] uppercase tracking-wider text-[--color-muted]">{children}</div>;
}
