import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { API_BASE } from '../config/api';

// Web push needs a completely different setup (VAPID keys, service worker)
// -- not worth building for a first version of one feature, so registration
// is native-only. Real device required either way; simulators/emulators
// can't receive real push notifications.
export async function registerForPushNotifications(authToken) {
  if (Platform.OS === 'web' || !authToken) return;

  try {
    const { status: existing } = await Notifications.getPermissionsAsync();
    let status = existing;
    if (existing !== 'granted') {
      ({ status } = await Notifications.requestPermissionsAsync());
    }
    if (status !== 'granted') return;

    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    const { data: expoPushToken } = await Notifications.getExpoPushTokenAsync({ projectId });

    await fetch(`${API_BASE}/api/push-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      body: JSON.stringify({ token: expoPushToken }),
    });
  } catch (err) {
    // Best-effort -- a user who never gets rally-ready pushes can still use
    // the app fully, just has to check the Archive screen manually.
    console.warn('[pushNotifications] registration failed:', err.message);
  }
}
