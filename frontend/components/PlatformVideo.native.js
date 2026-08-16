/**
 * Native implementation — thin wrapper around expo-av Video.
 * Exposes the same ref interface as PlatformVideo.web.js so
 * ContactMarkingScreen doesn't need any platform checks.
 *
 * `highFrequencyUpdates`: expo-av's onPlaybackStatusUpdate defaults to
 * firing roughly every 500ms, too coarse for a per-frame skeleton overlay
 * to look smooth. When set, tightens progressUpdateIntervalMillis to ~50ms.
 *
 * setRateAsync: expo-av's own Video ref exposes setRateAsync(rate,
 * shouldCorrectPitch, pitchCorrectionQuality?) -- a different signature
 * from web's single-arg version. Wrapping the ref here so callers can use
 * one setRateAsync(rate) signature on both platforms, same as playAsync/
 * pauseAsync/setPositionAsync already work identically without a wrapper.
 */
import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import { Video, ResizeMode } from 'expo-av';

const PlatformVideo = forwardRef(function PlatformVideo(
  { uri, width, height, onStatusUpdate, highFrequencyUpdates, onVideoSize, onError },
  ref,
) {
  const videoRef = useRef(null);

  useImperativeHandle(ref, () => ({
    playAsync:        (...args) => videoRef.current?.playAsync(...args),
    pauseAsync:        (...args) => videoRef.current?.pauseAsync(...args),
    setPositionAsync:  (...args) => videoRef.current?.setPositionAsync(...args),
    setRateAsync:      (rate) => videoRef.current?.setRateAsync(rate, true),
  }), []);

  return (
    <Video
      ref={videoRef}
      source={{ uri }}
      style={{ width: width ?? '100%', height: height ?? '100%', backgroundColor: '#000' }}
      resizeMode={ResizeMode.CONTAIN}
      shouldPlay={false}
      isLooping={false}
      useNativeControls={false}
      onPlaybackStatusUpdate={onStatusUpdate}
      progressUpdateIntervalMillis={highFrequencyUpdates ? 50 : undefined}
      onReadyForDisplay={(e) => {
        const size = e?.naturalSize;
        if (size?.width && size?.height) onVideoSize?.({ width: size.width, height: size.height });
      }}
      onError={(e) => onError?.(e?.nativeEvent?.error ?? 'Video failed to load')}
    />
  );
});

export default PlatformVideo;
