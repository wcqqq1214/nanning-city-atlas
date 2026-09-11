import type { LucideProps } from 'lucide-react';

/** A suspension bridge drawn on the same 24 px grid as the surrounding icons. */
export function BridgeIcon({
  size = 24,
  strokeWidth = 2,
  ...props
}: LucideProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M2 16h20M6 4v16M18 4v16" />
      <path d="M2 11Q4 11 6 5Q12 17 18 5Q20 11 22 11M9 10v6M12 11v5M15 10v6" />
    </svg>
  );
}
