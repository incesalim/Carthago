import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge conditional class names and resolve Tailwind conflicts.
 * The one styling helper every design-system component routes through.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
