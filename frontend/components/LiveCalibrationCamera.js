import { useEffect, useRef, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView } from 'react-native';
import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import { API_BASE } from '../config/api';

const GREEN  = '#4ade80';
const YELLOW = '#facc15';
const RED    = '#f87171';
const DARK   = '#0d0d0d';

const LIVE_CHECK_INTERVAL_MS = 1500;

// Same ok/elevation_status branching ContactMarkingScreen's post-record
// banner uses (calibMsg/calibWarn styling) -- extracted here so both the
// live badge and that banner render the same signal the same way instead of
// duplicating the logic.
export function calibColor(calibration) {
  if (!calibration || calibration.status !== 'done') return null;
  const elevationWarn = calibration.elevation_status === 'possibly_elevated';
  if (calibration.ok === false) return RED;
  if (elevationWarn) return YELLOW;
  if (calibration.ok === true) return GREEN;
  return null;
}

async function checkLiveFrame(uri) {
  const formData = new FormData();
  formData.append('snapshot', { uri, name: 'snapshot.jpg', type: 'image/jpeg' });
  const response = await fetch(`${API_BASE}/api/check-setup-live`, {
    method: 'POST',
    body: formData,
  });
  return response.json();
}

export default function LiveCalibrationCamera({ shotType, onRecorded, onCancel }) {
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [micPermission, requestMicPermission] = useMicrophonePermissions();
  const [live, setLive] = useState(null); // latest live-check result, or null before the first one lands
  const [recording, setRecording] = useState(false);
  const cameraRef = useRef(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!cameraPermission?.granted) requestCameraPermission();
    if (!micPermission?.granted) requestMicPermission();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runLiveCheck = useCallback(async () => {
    if (!cameraRef.current || recording) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.3, skipProcessing: true });
      const result = await checkLiveFrame(photo.uri);
      setLive(result);
    } catch {
      // Non-fatal by design -- a live badge that goes quiet for a cycle
      // (e.g. calibration server briefly unavailable) isn't an error state.
    }
  }, [recording]);

  useEffect(() => {
    intervalRef.current = setInterval(runLiveCheck, LIVE_CHECK_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [runLiveCheck]);

  const startRecording = async () => {
    if (!cameraRef.current || recording) return;
    setRecording(true);
    try {
      const video = await cameraRef.current.recordAsync();
      if (video?.uri) onRecorded(video.uri);
    } catch (err) {
      setRecording(false);
    }
  };

  const stopRecording = () => {
    cameraRef.current?.stopRecording();
    setRecording(false);
  };

  if (!cameraPermission || !micPermission) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}><Text style={s.permText}>Checking permissions…</Text></View>
      </SafeAreaView>
    );
  }

  if (!cameraPermission.granted || !micPermission.granted) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <Text style={s.permText}>Camera and microphone access are needed to record your swing.</Text>
          <TouchableOpacity style={s.permBtn} onPress={() => { requestCameraPermission(); requestMicPermission(); }}>
            <Text style={s.permBtnText}>Grant access</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.cancelLink} onPress={onCancel}>
            <Text style={s.cancelLinkText}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const badgeColor = live ? calibColor({ status: 'done', ...live }) ?? '#888' : '#888';

  return (
    <SafeAreaView style={s.safe}>
      <CameraView ref={cameraRef} style={s.camera} facing="back" mode="video">
        <View style={s.overlay}>
          <View style={[s.badge, { borderColor: badgeColor }]}>
            <Text style={[s.badgeText, { color: badgeColor }]}>
              {live ? live.message : 'Positioning your camera…'}
            </Text>
          </View>

          <View style={s.controls}>
            <TouchableOpacity style={s.cancelBtn} onPress={onCancel} disabled={recording}>
              <Text style={s.cancelBtnText}>Cancel</Text>
            </TouchableOpacity>

            {recording ? (
              <TouchableOpacity style={s.stopBtn} onPress={stopRecording}>
                <View style={s.stopSquare} />
              </TouchableOpacity>
            ) : (
              <TouchableOpacity style={s.recordBtn} onPress={startRecording}>
                <View style={s.recordDot} />
              </TouchableOpacity>
            )}

            <View style={s.shotLabel}>
              <Text style={s.shotLabelText}>{shotType?.charAt(0).toUpperCase() + shotType?.slice(1)}</Text>
            </View>
          </View>
        </View>
      </CameraView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  camera: { flex: 1 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  permText: { color: '#fff', fontSize: 15, textAlign: 'center', lineHeight: 22, marginBottom: 20 },
  permBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 14, paddingHorizontal: 28 },
  permBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
  cancelLink: { marginTop: 16 },
  cancelLinkText: { color: '#888', fontSize: 14 },

  overlay: { flex: 1, justifyContent: 'space-between', padding: 20, paddingTop: 60, paddingBottom: 40 },
  badge: {
    alignSelf: 'center', backgroundColor: 'rgba(0,0,0,0.65)', borderWidth: 1.5,
    borderRadius: 14, paddingVertical: 10, paddingHorizontal: 16, maxWidth: '90%',
  },
  badgeText: { fontSize: 13, fontWeight: '600', textAlign: 'center' },

  controls: { alignItems: 'center', gap: 14 },
  shotLabel: { backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: 10, paddingVertical: 4, paddingHorizontal: 12 },
  shotLabelText: { color: '#fff', fontSize: 12, fontWeight: '600' },

  cancelBtn: { position: 'absolute', left: 0, top: -6, padding: 10 },
  cancelBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },

  recordBtn: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: 'rgba(255,255,255,0.15)',
    borderWidth: 4, borderColor: '#fff', alignItems: 'center', justifyContent: 'center',
  },
  recordDot: { width: 56, height: 56, borderRadius: 28, backgroundColor: RED },
  stopBtn: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: 'rgba(255,255,255,0.15)',
    borderWidth: 4, borderColor: '#fff', alignItems: 'center', justifyContent: 'center',
  },
  stopSquare: { width: 28, height: 28, borderRadius: 4, backgroundColor: RED },
});
