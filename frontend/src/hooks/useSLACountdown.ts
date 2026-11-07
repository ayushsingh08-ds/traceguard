import { useEffect, useState } from "react";
import { SLABadgeState } from "../types/incident";

interface SLACountdownResult {
  remainingSeconds: number;
  formattedText: string;
  badgeState: SLABadgeState;
}

export function useSLACountdown(
  deadlineIso: string,
  isResolved: boolean = false
): SLACountdownResult {
  const calculateRemaining = () => {
    const deadlineTime = new Date(deadlineIso).getTime();
    const now = Date.now();
    return Math.floor((deadlineTime - now) / 1000);
  };

  const [remainingSeconds, setRemainingSeconds] = useState<number>(calculateRemaining);

  useEffect(() => {
    if (isResolved) return;

    // Isolated interval keeps 1-second ticks scoped to individual badges,
    // avoiding expensive full-table component re-renders.
    const interval = setInterval(() => {
      setRemainingSeconds(calculateRemaining());
    }, 1000);

    return () => clearInterval(interval);
  }, [deadlineIso, isResolved]);

  if (isResolved) {
    return {
      remainingSeconds: 0,
      formattedText: "Resolved",
      badgeState: "healthy",
    };
  }

  const isBreached = remainingSeconds <= 0;
  const absSec = Math.abs(remainingSeconds);
  const hours = Math.floor(absSec / 3600);
  const minutes = Math.floor((absSec % 3600) / 60);
  const seconds = absSec % 60;

  const pad = (n: number) => n.toString().padStart(2, "0");
  const timeString = hours > 0 ? `${hours}h ${pad(minutes)}m ${pad(seconds)}s` : `${pad(minutes)}m ${pad(seconds)}s`;

  if (isBreached) {
    return {
      remainingSeconds,
      formattedText: `-${timeString} BREACH`,
      badgeState: "breached",
    };
  }

  // Warning state triggers when under 5 minutes remain
  const isWarning = remainingSeconds <= 300;
  return {
    remainingSeconds,
    formattedText: timeString,
    badgeState: isWarning ? "warning" : "healthy",
  };
}

