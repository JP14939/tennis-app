/**
 * Native implementation — thin wrapper around expo-av Video.
 * Exposes the same ref interface as PlatformVideo.web.js so
 * ContactMarkingScreen doesn't need any platform checks.
 */
import React, { forwardRef } from 'react';
import { Video, ResizeMode } from 'expo-av';

const PlatformVideo = forwardRef(function PlatformVideo(
  { uri, width, height, onStatusUpdate },
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
    />
  );
});

export default PlatformVideo;
