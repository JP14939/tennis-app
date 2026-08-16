/**
 * Web implementation — renders a native HTML5 <video> element directly.
 * React Native Web doesn't reliably host expo-av inside flex containers,
 * so we bypass it entirely and use the DOM API.
 *
 * Exposes the same async interface as expo-av's Video ref:
 *   playAsync(), pauseAsync(), setPositionAsync(ms), setRateAsync(rate)
 *
 * `highFrequencyUpdates`: DOM `timeupdate` only fires ~4Hz, too coarse for
 * a per-frame skeleton overlay to look smooth. When set, a
 * requestAnimationFrame loop pushes onStatusUpdate every frame while
 * playing instead of waiting on `timeupdate`.
 */
import React, { forwardRef, useImperativeHandle, useRef, useEffect } from 'react';

const PlatformVideo = forwardRef(function PlatformVideo(
  { uri, width, height, onStatusUpdate, highFrequencyUpdates, onVideoSize, onError },
  ref,
) {
  const elRef = useRef(null);
  const rafRef = useRef(null);

  // Expose expo-av-compatible async methods to parent via ref
  useImperativeHandle(ref, () => ({
    playAsync:        async () => elRef.current?.play().catch(() => {}),
    pauseAsync:       async () => elRef.current?.pause(),
    setPositionAsync: async (ms) => {
      if (elRef.current) elRef.current.currentTime = ms / 1000;
    },
    setRateAsync: async (rate) => {
      if (elRef.current) elRef.current.playbackRate = rate;
    },
  }), []);

  // Push status updates to parent the same shape expo-av uses
  useEffect(() => {
    const el = elRef.current;
    if (!el) return;

    const push = () => {
      onStatusUpdate?.({
        isLoaded:       true,
        isPlaying:      !el.paused && !el.ended,
        positionMillis: el.currentTime * 1000,
        durationMillis: (el.duration || 0) * 1000,
      });
    };

    const rafTick = () => {
      push();
      rafRef.current = requestAnimationFrame(rafTick);
    };
    const stopRaf = () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
    const handlePlay = () => {
      push();
      if (highFrequencyUpdates && rafRef.current == null) {
        rafRef.current = requestAnimationFrame(rafTick);
      }
    };
    const handleStop = () => {
      push();
      stopRaf();
    };
    const handleLoadedMetadata = () => {
      push();
      if (el.videoWidth && el.videoHeight) onVideoSize?.({ width: el.videoWidth, height: el.videoHeight });
    };
    const handleError = () => {
      onError?.(el.error?.message || 'Video failed to load');
    };

    el.addEventListener('timeupdate',    push);
    el.addEventListener('play',          handlePlay);
    el.addEventListener('pause',         handleStop);
    el.addEventListener('ended',         handleStop);
    el.addEventListener('loadedmetadata', handleLoadedMetadata);
    el.addEventListener('error',         handleError);

    return () => {
      stopRaf();
      el.removeEventListener('timeupdate',    push);
      el.removeEventListener('play',          handlePlay);
      el.removeEventListener('pause',         handleStop);
      el.removeEventListener('ended',         handleStop);
      el.removeEventListener('loadedmetadata', handleLoadedMetadata);
      el.removeEventListener('error',         handleError);
    };
  }, [onStatusUpdate, highFrequencyUpdates, onVideoSize, onError]);

  // When URI changes, update src and reload
  useEffect(() => {
    const el = elRef.current;
    if (!el || !uri) return;
    el.src = uri;
    el.load();
  }, [uri]);

  return React.createElement('video', {
    ref: elRef,
    playsInline: true,
    preload: 'auto',
    style: {
      display: 'block',
      width: width ? `${width}px` : '100%',
      height: height ? `${height}px` : '100%',
      objectFit: 'contain',
      backgroundColor: '#000',
    },
  });
});

export default PlatformVideo;
