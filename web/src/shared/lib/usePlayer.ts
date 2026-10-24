import { useCallback, useEffect, useRef, useState } from "react";

import { audioUrl } from "../api/client";

/** Plays one excerpt at a time; a second play stops the first. */
export function usePlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const stop = useCallback(() => {
    audio.current?.pause();
    audio.current = null;
    setPlaying(null);
  }, []);

  const play = useCallback(
    async (key: number, itemId: number, start?: number, end?: number) => {
      if (playing === key) {
        stop();
        return;
      }
      stop();
      setError(null);
      try {
        const src = await audioUrl(itemId, start, end);
        const a = new Audio(src);
        audio.current = a;
        setPlaying(key);
        a.onended = () => {
          URL.revokeObjectURL(src);
          setPlaying((p) => (p === key ? null : p));
        };
        await a.play();
      } catch (e) {
        setPlaying(null);
        setError(e instanceof Error ? e.message : "Could not play this audio.");
      }
    },
    [playing, stop],
  );

  useEffect(() => stop, [stop]);
  return { play, stop, playing, error };
}
