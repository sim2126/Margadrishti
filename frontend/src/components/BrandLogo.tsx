import type { SVGProps } from "react";
import { cn } from "@/lib/utils";

type BrandMarkProps = SVGProps<SVGSVGElement> & {
  decorative?: boolean;
};

/** Theme-aware Margadrishti road-vision mark. */
export function BrandMark({ className, decorative = false, ...props }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={cn("shrink-0", className)}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : "Margadrishti"}
      {...props}
    >
      <path
        d="M5 27h10l10 10v21M5 37h7l7 7v14"
        fill="none"
        stroke="var(--color-logo-road)"
        strokeWidth="6"
        strokeLinejoin="miter"
        strokeLinecap="square"
      />
      <path
        d="m14 28 11-11 7 7L48 8"
        fill="none"
        stroke="var(--color-logo-road)"
        strokeWidth="6"
        strokeLinejoin="miter"
        strokeLinecap="square"
      />
      <path d="m43 4 14-1-1 14Z" fill="var(--color-logo-road)" />
      <path
        d="M29 58V40L49 20"
        fill="none"
        stroke="var(--color-logo-teal)"
        strokeWidth="7"
        strokeLinejoin="miter"
        strokeLinecap="square"
      />
      <path d="m44 15 14-1-1 14Z" fill="var(--color-logo-teal)" />
      <path
        d="M39 58V43l13-13"
        fill="none"
        stroke="var(--color-logo-road)"
        strokeWidth="6"
        strokeLinejoin="miter"
        strokeLinecap="square"
      />
      <path d="m48 25 12-1-1 12Z" fill="var(--color-logo-road)" />
      <circle cx="59" cy="7" r="3.5" fill="var(--color-logo-saffron)" />
    </svg>
  );
}

