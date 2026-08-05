/**
 * Native implementation — thin wrapper around expo-av Video.
 * Exposes the same ref interface as PlatformVideo.web.js so
 * ContactMarkingScreen doesn't need any platform checks.
 *
 * `highFrequencyUpdates`: expo-av's onPlaybackStatusUpdate defaults to
 * firing roughly every 500ms, too coarse for a per-frame skeleton overlay
 * to look smooth. When set, tightens progressUpdateIntervalMillis to ~50ms.
 */
import React, { forwardRef } from 'react';
import { Video, ResizeMode } from 'expo-av';

const PlatformVideo = forwardRef(function PlatformVideo(
  { uri, width, height, onStatusUpdate, highFrequencyUpdates },
  ref,
) {
  return (
    <Video
      ref={ref}
      source={{ uri }}
      style={{ width: width ?? '100%', height: height ?? '100%', backgroundColor: '#000' }}
      resizeMode={ResizeMode.CONTAIN}
      shouldPlay={false}
      isLooping={false}
      useNativeControls={false}
      onPlaybackStatusUpdate={onStatusUpdate}
      progressUpdateIntervalMillis={highFrequencyUpdates ? 50 : undefined}
    />
  );
});

export default PlatformVideo;
