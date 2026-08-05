import { Alert } from 'react-native';
import { captureRef } from 'react-native-view-shot';
import * as Sharing from 'expo-sharing';

// Captures an off-screen card View (ResultShareCard / ProgressShareCard) to
// a PNG and hands it to the native share sheet. Native-only -- callers must
// not render the triggering button on web (expo-sharing's own docs: no
// local-file sharing on web at all, Web Share API only).
export async function captureAndShare(viewRef, dialogTitle) {
  try {
    const available = await Sharing.isAvailableAsync();
    if (!available) {
      Alert.alert('Sharing not available', 'Your device does not support sharing.');
      return;
    }
    const uri = await captureRef(viewRef, { format: 'png', quality: 1 });
    await Sharing.shareAsync(uri, {
      dialogTitle,
      UTI: 'public.png',
      mimeType: 'image/png',
    });
  } catch (err) {
    Alert.alert('Could not share', err.message || 'Something went wrong');
  }
}
